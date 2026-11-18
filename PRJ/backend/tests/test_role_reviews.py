from concurrent.futures import ThreadPoolExecutor
import copy
from uuid import uuid4
import pytest
from app.db import connect
from app.role_reviews import (
    ROLES,
    AgentResult,
    evidence_items,
    process_review,
    snapshot_hash,
    validate_evidence,
)
from app.generation import strict_schema
from test_studio import generated, bundle, approve


def start(client, pid, proposal):
    r = client.post(
        f"/api/projects/{pid}/reviews", json={"proposal_id": proposal["id"]}
    )
    assert r.status_code == 201, r.text
    return r.json()


def get_review(client, pid, proposal):
    return client.get(
        f"/api/projects/{pid}/reviews?proposal_id={proposal['id']}"
    ).json()


def test_five_independent_reviews_are_idempotent_and_do_not_mutate_planning(client):
    pid, before = generated(client)
    prop = before["proposal"]
    with ThreadPoolExecutor(2) as pool:
        reports = list(pool.map(lambda _: start(client, pid, prop), range(2)))
    assert reports[0]["id"] == reports[1]["id"]
    report = reports[0]
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda _: process_review(report["id"]), range(2)))
    report = get_review(client, pid, prop)
    assert report["status"] == "completed"
    assert report["snapshot_hash"] == snapshot_hash(prop["candidate"])
    assert {a["role"] for a in report["agents"]} == set(ROLES)
    assert all(
        a["status"] == "completed" and a["result"]["findings"] for a in report["agents"]
    )
    after = bundle(client, pid)
    assert after["revision"] == before["revision"]
    assert after["proposal"] == before["proposal"]
    assert after["project"]["current_version"] == 0
    assert approve(client, pid, prop).status_code == 200
    r = client.post(f"/api/projects/{pid}/reviews", json={"version": 1})
    assert r.status_code == 201
    assert r.json()["id"] != report["id"]
    assert r.json()["snapshot_hash"] == report["snapshot_hash"]


def test_review_target_ownership_and_bad_target_boundaries(client):
    pid, result = generated(client)
    prop = result["proposal"]
    path = f"/api/projects/{pid}/reviews"
    for body in [
        {},
        {"version": 0},
        {"version": 99},
        {"version": 1, "proposal_id": prop["id"]},
    ]:
        assert client.post(path, json=body).status_code in (404, 422)
    assert client.post(path, json={"proposal_id": str(uuid4())}).status_code == 404
    other_pid, other = generated(client)
    assert (
        client.post(path, json={"proposal_id": other["proposal"]["id"]}).status_code
        == 404
    )
    report = start(client, pid, prop)
    for method, url, body in [
        ("get", path + f"?proposal_id={prop['id']}", None),
        ("post", path, {"proposal_id": prop["id"]}),
        ("post", path + f"/{report['id']}/retry", {"role": "qa"}),
    ]:
        assert (
            client.request(
                method, url, json=body, headers={"Authorization": "Bearer local:bob"}
            ).status_code
            == 404
        )
        assert (
            client.request(
                method, url, json=body, headers={"Authorization": ""}
            ).status_code
            == 401
        )
    assert (
        client.post(
            f"/api/projects/{other_pid}/reviews/{report['id']}/retry",
            json={"role": "qa"},
        ).status_code
        == 404
    )


def test_partial_failure_retries_only_failed_role_and_retains_completed_results(
    client, monkeypatch
):
    from app import role_reviews as module

    pid, result = generated(client)
    prop = result["proposal"]
    report = start(client, pid, prop)
    original = module.run_agent
    calls = []

    def fake(role, report):
        calls.append(role)
        if role == "security":
            raise ValueError("private-provider-body-secret")
        return original(role, report)

    monkeypatch.setattr(module, "run_agent", fake)
    process_review(report["id"])
    partial = get_review(client, pid, prop)
    assert partial["status"] == "partial"
    assert len(calls) == 5
    failed = next(a for a in partial["agents"] if a["role"] == "security")
    assert failed["status"] == "failed"
    assert "private-provider-body-secret" not in str(partial)
    retry_url = f"/api/projects/{pid}/reviews/{report['id']}/retry"
    assert client.post(retry_url, json={"role": "qa"}).status_code == 409
    assert client.post(retry_url, json={"role": "security"}).status_code == 200
    assert client.post(retry_url, json={"role": "security"}).status_code == 409
    monkeypatch.setattr(module, "run_agent", original)
    process_review(report["id"])
    final = get_review(client, pid, prop)
    assert final["status"] == "completed"
    for agent in partial["agents"]:
        if agent["role"] != "security":
            assert agent == next(
                a for a in final["agents"] if a["role"] == agent["role"]
            )


def test_fabricated_evidence_fails_role_and_superseded_review_is_not_reused(
    client, monkeypatch
):
    from app import role_reviews as module

    pid, result = generated(client)
    prop = result["proposal"]
    report = start(client, pid, prop)
    original = module.run_agent

    def bad(role, report):
        result, usage = original(role, report)
        result["findings"][0]["evidence"][0]["quote"] = "원문에는 존재하지 않는 근거"
        return result, usage

    monkeypatch.setattr(module, "run_agent", bad)
    process_review(report["id"])
    assert get_review(client, pid, prop)["status"] == "failed"
    candidate = copy.deepcopy(prop["candidate"])
    candidate["prd"]["sections"][0]["content"] += " 새 결정"
    new = client.post(
        f"/api/projects/{pid}/proposals",
        json={"base_version": 0, "snapshot": candidate},
    ).json()
    assert get_review(client, pid, new) is None
    assert (
        client.post(
            f"/api/projects/{pid}/reviews", json={"proposal_id": prop["id"]}
        ).status_code
        == 409
    )
    assert start(client, pid, new)["snapshot_hash"] != report["snapshot_hash"]


def test_review_restart_skips_completed_roles(client, monkeypatch):
    from app import role_reviews as module

    pid, result = generated(client)
    report = start(client, pid, result["proposal"])
    process_review(report["id"])
    with connect() as c:
        c.execute(
            "UPDATE studio_reviews SET status='running' WHERE id=%s", (report["id"],)
        )
        c.execute(
            "UPDATE studio_review_agents SET status='running',result=NULL WHERE review_id=%s AND role='qa'",
            (report["id"],),
        )
    original = module.run_agent
    seen = []

    def record(role, report):
        seen.append(role)
        return original(role, report)

    monkeypatch.setattr(module, "run_agent", record)
    process_review(report["id"])
    assert seen == ["qa"]
    assert get_review(client, pid, result["proposal"])["status"] == "completed"


def test_role_schema_is_strict_and_nonexistent_target_is_rejected(client):
    schema = strict_schema(AgentResult)
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Finding"]["additionalProperties"] is False
    _, result = generated(client)
    with pytest.raises(RuntimeError):
        validate_evidence(
            {"findings": [{"evidence": [{"target_id": "absent", "quote": "abc"}]}]},
            evidence_items(result["proposal"]["candidate"]),
        )


def test_changed_provider_fails_without_fallback(client):
    pid, result = generated(client)
    report = start(client, pid, result["proposal"])
    with connect() as c:
        c.execute(
            "UPDATE studio_reviews SET provider='openai' WHERE id=%s", (report["id"],)
        )
    process_review(report["id"])
    final = get_review(client, pid, result["proposal"])
    assert final["status"] == "failed"
    assert all(
        a["result"] is None and "모델 설정" in a["error"] for a in final["agents"]
    )


def test_live_roles_use_distinct_calls_and_prompts_with_same_snapshot(
    client, monkeypatch
):
    from types import SimpleNamespace
    from app import role_reviews as module
    from app.config import settings

    _, result = generated(client)
    s = settings()
    report = {
        "provider": s.llm_provider,
        "model": s.model,
        "ai_mode": "mock",
        "snapshot": result["proposal"]["candidate"],
    }
    valid, _ = module.run_agent("developer", report)
    report["ai_mode"] = "live"
    monkeypatch.setattr(
        module,
        "settings",
        lambda: SimpleNamespace(
            llm_provider=s.llm_provider, model=s.model, ai_mode="live"
        ),
    )
    calls = []

    def capture(stage, context, pinned, system, schema, prompt_version, **kwargs):
        calls.append((stage, copy.deepcopy(context), system))
        assert pinned["ai_mode"] == "live"
        assert prompt_version == module.REVIEW_PROMPT_VERSION
        return valid, {}

    monkeypatch.setattr(module, "structured_completion", capture)
    for role in ROLES:
        module.run_agent(role, report)
    assert {c[0] for c in calls} == {"review_" + r for r in ROLES}
    assert len({c[2] for c in calls}) == 5
    assert all(c[1] == calls[0][1] for c in calls)
    assert all("findings" not in c[1] for c in calls)
