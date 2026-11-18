from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import copy
import pytest
import psycopg
from app.db import connect
from app.worker import process
from app.generation import strict_schema
from app.schema import Snapshot


def make_project(client):
    body = {"id": str(uuid4()), "idea": "작은 팀의 할 일을 관리하는 웹 서비스"}
    response = client.post("/api/projects", json=body)
    assert response.status_code == 201, response.text
    return response.json()["id"], body


def bundle(client, pid):
    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def generated(client):
    pid, _ = make_project(client)
    job = bundle(client, pid)["job"]
    process(job["id"])
    job = bundle(client, pid)["job"]
    assert job["status"] == "awaiting_answers"
    r = client.post(
        f"/api/projects/{pid}/jobs/{job['id']}/answers",
        json={
            "base_version": 0,
            "answers": {q["key"]: q["options"][0] for q in job["questions"]},
        },
    )
    assert r.status_code == 200, r.text
    process(job["id"])
    result = bundle(client, pid)
    assert result["proposal"], result["job"]
    return pid, result


def approve(client, pid, proposal, version=0):
    return client.post(
        f"/api/projects/{pid}/proposals/{proposal['id']}/approve",
        json={"expected_version": version, "acknowledge_warnings": True},
    )


def test_project_and_revision_zero_and_idempotency(client):
    pid, body = make_project(client)
    before = bundle(client, pid)
    assert before["revision"]["version"] == 0
    assert before["revision"]["snapshot"]["screens"] == []
    assert client.post("/api/projects", json=body).status_code == 201
    assert len(client.get("/api/projects").json()) == 1
    assert (
        client.post("/api/projects", json={**body, "idea": "다른 아이디어"}).status_code
        == 409
    )
    assert len(bundle(client, pid)["messages"]) == 1


def test_auth_and_resource_ownership(client):
    pid, _ = make_project(client)
    for path in [
        f"/api/projects/{pid}",
        f"/api/projects/{pid}/revisions/0",
        f"/api/projects/{pid}/revisions/0/export",
    ]:
        assert (
            client.get(path, headers={"Authorization": "Bearer local:bob"}).status_code
            == 404
        )
        assert client.get(path, headers={"Authorization": ""}).status_code == 401
    assert client.get(f"/api/projects/{uuid4()}").status_code == 404
    assert (
        client.patch(
            f"/api/projects/{pid}",
            json={"title": "가로채기"},
            headers={"Authorization": "Bearer local:bob"},
        ).status_code
        == 404
    )


def test_questions_require_exact_keys_version_and_idempotent_answers(client):
    pid, _ = make_project(client)
    job = bundle(client, pid)["job"]
    process(job["id"])
    job = bundle(client, pid)["job"]
    url = f"/api/projects/{pid}/jobs/{job['id']}/answers"
    assert client.post(url, json={"base_version": 0, "answers": {}}).status_code == 422
    answers = {q["key"]: "" for q in job["questions"]}
    assert (
        client.post(url, json={"base_version": 1, "answers": answers}).status_code
        == 409
    )
    body = {"base_version": 0, "answers": answers}
    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 200
    assert len(bundle(client, pid)["messages"]) == 3


def test_generation_stays_proposal_until_approved(client):
    pid, result = generated(client)
    assert result["project"]["current_version"] == 0
    assert len(result["proposal"]["candidate"]["screens"]) == 3
    assert not any(i["severity"] == "blocking" for i in result["proposal"]["issues"])
    assert client.get(f"/api/projects/{pid}/revisions/1").status_code == 404
    assert client.get(f"/api/projects/{pid}/revisions/0/export").status_code == 409
    assert approve(client, pid, result["proposal"]).status_code == 200
    approved = bundle(client, pid)
    assert approved["project"]["current_version"] == 1
    assert approved["proposal"] is None
    assert approved["revision"]["snapshot"] == result["proposal"]["candidate"]
    assert approved["job"]["status"] == "completed"


def test_warning_requires_ack_and_double_approval_is_idempotent(client):
    pid, result = generated(client)
    prop = result["proposal"]
    url = f"/api/projects/{pid}/proposals/{prop['id']}"
    assert (
        client.post(url + "/approve", json={"expected_version": 0}).status_code == 409
    )
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda _: approve(client, pid, prop), range(2)))
    assert all(r.status_code == 200 for r in responses)
    assert [r.json()["version"] for r in responses] == [1, 1]
    assert len(bundle(client, pid)["revisions"]) == 2
    assert client.post(url + "/reject", json={"expected_version": 1}).status_code == 409


def test_reject_does_not_change_revision(client):
    pid, result = generated(client)
    r = client.post(
        f"/api/projects/{pid}/proposals/{result['proposal']['id']}/reject",
        json={"expected_version": 0},
    )
    assert r.status_code == 200
    result = bundle(client, pid)
    assert result["project"]["current_version"] == 0
    assert len(result["revisions"]) == 1


def test_manual_edits_create_new_proposal_and_preserve_old_candidate(client):
    pid, result = generated(client)
    old = result["proposal"]
    candidate = copy.deepcopy(old["candidate"])
    candidate["screens"][0]["blocks"][1]["label"] = "달라진 화면 제목"
    r = client.post(
        f"/api/projects/{pid}/proposals",
        json={"base_version": 0, "snapshot": candidate},
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] != old["id"]
    with connect() as c:
        prior = c.execute(
            "SELECT candidate,status FROM studio_proposals WHERE id=%s", (old["id"],)
        ).fetchone()
        assert prior["candidate"] == old["candidate"]
        assert prior["status"] == "superseded"
    assert bundle(client, pid)["project"]["current_version"] == 0
    assert approve(client, pid, r.json()).status_code == 200
    immutable = client.get(f"/api/projects/{pid}/revisions/1").json()["snapshot"]
    candidate["screens"][0]["blocks"][1]["label"] = "아직 확정하지 않은 화면"
    assert (
        client.post(
            f"/api/projects/{pid}/proposals",
            json={"base_version": 0, "snapshot": candidate},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/projects/{pid}/proposals",
            json={"base_version": 1, "snapshot": candidate},
        ).status_code
        == 201
    )
    assert (
        client.get(f"/api/projects/{pid}/revisions/1").json()["snapshot"] == immutable
    )


def test_invalid_cross_references_block_approval(client):
    pid, result = generated(client)
    candidate = result["proposal"]["candidate"]
    candidate["screens"][0]["node_id"] = "missing"
    r = client.post(
        f"/api/projects/{pid}/proposals",
        json={"base_version": 0, "snapshot": candidate},
    )
    assert r.status_code == 201
    assert any(i["severity"] == "blocking" for i in r.json()["issues"])
    assert approve(client, pid, r.json()).status_code == 409


def test_database_enforces_revision_immutability(client):
    pid, _ = make_project(client)
    with pytest.raises(psycopg.errors.RaiseException):
        with connect() as c:
            c.execute(
                "UPDATE studio_revisions SET summary='changed' WHERE project_id=%s",
                (pid,),
            )
    with pytest.raises(psycopg.errors.RaiseException):
        with connect() as c:
            c.execute("DELETE FROM studio_revisions WHERE project_id=%s", (pid,))


def test_worker_recovery_and_cancelled_jobs(client):
    pid, _ = make_project(client)
    job = bundle(client, pid)["job"]
    assert (
        client.post(f"/api/projects/{pid}/jobs/{job['id']}/cancel", json={}).status_code
        == 200
    )
    process(job["id"])
    assert bundle(client, pid)["job"]["status"] == "cancelled"
    assert bundle(client, pid)["proposal"] is None
    r = client.post(
        f"/api/projects/{pid}/jobs",
        json={"base_version": 0, "kind": "generate", "request": "다시 생성"},
    )
    assert r.status_code == 201
    new = r.json()
    process(new["id"])
    waiting = bundle(client, pid)["job"]
    client.post(
        f"/api/projects/{pid}/jobs/{new['id']}/answers",
        json={
            "base_version": 0,
            "answers": {q["key"]: "" for q in waiting["questions"]},
        },
    )
    with connect() as c:
        c.execute("UPDATE studio_jobs SET status='running' WHERE id=%s", (new["id"],))
    process(new["id"])
    process(new["id"])
    assert bundle(client, pid)["job"]["status"] == "waiting_review"
    with connect() as c:
        assert (
            c.execute(
                "SELECT count(*) AS n FROM studio_proposals WHERE job_id=%s",
                (new["id"],),
            ).fetchone()["n"]
            == 1
        )


def test_provider_failure_never_falls_back_to_mock(client, monkeypatch):
    pid, _ = make_project(client)
    job = bundle(client, pid)["job"]

    def fail(*args):
        raise RuntimeError("모델 공급자 응답 오류 (HTTP 503).")

    monkeypatch.setattr("app.worker.generate", fail)
    process(job["id"])
    result = bundle(client, pid)
    assert result["job"]["status"] == "failed"
    assert not result["proposal"]
    assert result["project"]["current_version"] == 0


def test_completed_decision_is_not_overwritten_by_worker(client):
    pid, result = generated(client)
    approve(client, pid, result["proposal"])
    process(result["job"]["id"])
    assert bundle(client, pid)["job"]["status"] == "completed"
    assert bundle(client, pid)["project"]["current_version"] == 1


def test_exports_use_selected_approved_revision_and_include_wireframes(client):
    pid, result = generated(client)
    approve(client, pid, result["proposal"])
    first = client.get(f"/api/projects/{pid}/revisions/1/export?format=json")
    assert first.status_code == 200
    snapshot = first.json()["snapshot"]
    candidate = copy.deepcopy(snapshot)
    candidate["prd"]["sections"][0]["content"] = "미승인 변경"
    client.post(
        f"/api/projects/{pid}/proposals",
        json={"base_version": 1, "snapshot": candidate},
    )
    exported = client.get(f"/api/projects/{pid}/revisions/1/export?format=json")
    assert exported.json()["snapshot"] == snapshot
    assert len(exported.json()["snapshot"]["screens"]) == 3
    md = client.get(f"/api/projects/{pid}/revisions/1/export?format=markdown")
    assert "# 와이어프레임" in md.text
    assert "screen-home" in md.text
    assert "미승인 변경" not in md.text


def test_revise_and_pinned_provider_identity(client):
    pid, result = generated(client)
    approve(client, pid, result["proposal"])
    r = client.post(
        f"/api/projects/{pid}/jobs",
        json={"base_version": 1, "request": "목표를 보강해줘", "target_id": "prd-goal"},
    )
    assert r.status_code == 201
    process(r.json()["id"])
    result = bundle(client, pid)
    assert result["project"]["current_version"] == 1
    assert len(result["proposal"]["diff"]) == 1
    assert result["proposal"]["diff"][0]["key"] == "prd:prd-goal"


def test_schema_rejects_executable_wireframe_types(client):
    pid, result = generated(client)
    snapshot = result["proposal"]["candidate"]
    snapshot["screens"][0]["blocks"][0]["type"] = "script"
    assert (
        client.post(
            f"/api/projects/{pid}/proposals",
            json={"base_version": 0, "snapshot": snapshot},
        ).status_code
        == 422
    )


def test_strict_output_schema_requires_all_properties():
    schema = strict_schema(Snapshot)

    def walk(value):
        if isinstance(value, dict):
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value["properties"])
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(schema)


def test_repair_keeps_original_when_it_drops_generated_artifacts(client, monkeypatch):
    from app import worker
    from app.schema import empty_snapshot

    generate = worker.generate
    stages = []

    def generate_with_incomplete_repair(stage, context, job):
        stages.append(stage)
        if stage == "repair":
            return empty_snapshot("불완전한 보정"), {"stage": stage}
        result, usage = generate(stage, context, job)
        if stage == "features":
            result["features"][0]["requirement_id"] = "missing"
        return result, usage

    monkeypatch.setattr(worker, "generate", generate_with_incomplete_repair)
    pid, result = generated(client)
    proposal = result["proposal"]
    assert stages.count("repair") == 1
    assert result["job"]["usage"][-1]["stage"] == "repair"
    assert len(proposal["candidate"]["screens"]) == 3
    assert proposal["candidate"]["prd"]["sections"]
    assert proposal["candidate"]["features"][0]["requirement_id"] == "missing"
    assert any(issue["severity"] == "blocking" for issue in proposal["issues"])
    assert approve(client, pid, proposal).status_code == 409
