import copy
from uuid import uuid4

import psycopg
import pytest

from app import source_api, worker
from app.config import settings
from app.db import connect
from app.generation import ModelError
from app.repositories import process_analysis
from app.schema import Block, DesignProfile
from app.worker import process
from test_source_planning import repos, register, queue, source_body, git
from test_studio import bundle, approve


def publish(client, source, snapshot):
    preview = client.post(f"/api/sources/{source}/snapshots/{snapshot}/publication-preview", json={})
    assert preview.status_code == 200, preview.text
    preview = preview.json()
    body = {"snapshot_id": snapshot, "fingerprint": preview["fingerprint"], "design_profile": preview["design_profile"]}
    result = client.post(f"/api/sources/{source}/publish", json=body)
    assert result.status_code == 200, result.text
    return result.json(), body


def setup_business(client, repos):
    theme = repos / "alpha" / "theme.css"
    theme.write_text(":root { --brand-primary: #0c7a6b; --background: #ffffff; --surface: #f5faf8; --text: #172033; }\n.sidebar { border-radius: 4px; gap: 12px; font-family: Arial, sans-serif; }")
    git(repos / "alpha", "add", "theme.css")
    git(repos / "alpha", "commit", "-qm", "design fixture")
    source = register(client, "alpha")
    snapshot = queue(client, source)
    process_analysis(snapshot["id"])
    publication, _ = publish(client, source, snapshot["id"])
    body = source_body(source, snapshot, start_mode="conversation", source_publication_id=publication["id"],
                       idea="발주 담당자가 주문을 확인한 뒤 승인하도록 업무를 개선하고 싶어요.")
    result = client.post("/api/projects", json=body)
    assert result.status_code == 201, result.text
    pid = result.json()["id"]
    return pid, source, snapshot, body


def job(client, pid, kind, request="정리한 업무로 기획해 주세요", proposal=None, **fields):
    body = {"id": str(uuid4()), "base_version": bundle(client, pid)["project"]["current_version"],
            "kind": kind, "request": request, "base_proposal_id": proposal, **fields}
    result = client.post(f"/api/projects/{pid}/jobs", json=body)
    assert result.status_code == 201, result.text
    process(result.json()["id"])
    return bundle(client, pid)


def test_publication_scope_design_idempotency_and_owner(client, repos):
    pid, source, snapshot, body = setup_business(client, repos)
    publication, pub_body = publish(client, source, snapshot["id"])
    assert publication["id"] == body["source_publication_id"]
    result = client.get("/api/sources").json()[0]
    assert result["design_profile"]["primary"] == "#0c7a6b"
    assert result["design_profile"]["shell"] == "sidebar"
    assert result["design_profile"]["spacing"] == 12
    assert result["design_profile"]["font"] == "sans"
    changed = copy.deepcopy(pub_body)
    changed["design_profile"]["primary"] = "#112233"
    assert client.post(f"/api/sources/{source}/publish", json=changed).status_code == 409
    for endpoint in [f"/api/sources/{source}/publish", f"/api/sources/{source}/snapshots/{snapshot['id']}/publication-preview"]:
        assert client.post(endpoint, json=pub_body if endpoint.endswith("publish") else {}, headers={"Authorization": "Bearer local:bob"}).status_code == 404
    assert client.get(f"/api/projects/{pid}", headers={"Authorization": "Bearer local:bob"}).status_code == 404
    assert client.post("/api/projects", json=body).json()["id"] == pid
    with pytest.raises(psycopg.Error), connect() as c:
        c.execute("UPDATE studio_source_publications SET design_profile='{}' WHERE id=%s", (publication["id"],))


def test_discussion_explicit_generation_and_draft_targeted_revision(client, repos):
    pid, _, _, _ = setup_business(client, repos)
    initial = bundle(client, pid)
    assert initial["job"]["kind"] == "discuss" and initial["job"]["prompt_version"] == "business.v2"
    process(initial["job"]["id"])
    result = bundle(client, pid)
    assert result["proposal"] is None and result["project"]["current_version"] == 0
    assert result["project"]["conversation_brief"]["user_statements"]
    question = result["job"]["partial"]["discussion"]["questions"][0]
    assert len(question["options"]) >= 2
    assert question["title"] in result["messages"][-1]["content"]
    restored = bundle(client, pid)
    assert restored["job"]["partial"]["discussion"]["questions"] == [question]
    result = job(client, pid, "generate")
    assert result["job"]["status"] == "waiting_review", result["job"]
    proposal = result["proposal"]
    assert proposal["candidate"]["design_profile"]["primary"] == "#0c7a6b"
    assert result["project"]["current_version"] == 0
    result = job(client, pid, "discuss", "버튼 문구를 더 명확하게 바꾸고 싶어요", proposal["id"])
    assert result["proposal"]["id"] == proposal["id"]
    target = proposal["candidate"]["screens"][0]["blocks"][-1]["id"]
    result = job(client, pid, "revise", "발주 승인 요청", proposal["id"], target_id=target)
    assert result["job"]["status"] == "waiting_review", result["job"]
    candidate = result["proposal"]["candidate"]
    expected = copy.deepcopy(proposal["candidate"])
    next(b for s in expected["screens"] for b in s["blocks"] if b["id"] == target)["label"] = "발주 승인 요청"
    assert candidate == expected
    assert result["changed_block_ids"] == [target]
    assert client.post(f"/api/projects/{pid}/jobs", json={"kind": "revise", "request": "오래된 초안 수정", "base_version": 0, "base_proposal_id": proposal["id"]}).status_code == 409
    assert approve(client, pid, result["proposal"]).status_code == 200
    confirmed = bundle(client, pid)
    assert confirmed["project"]["current_version"] == 1
    assert client.get(f"/api/projects/{pid}/revisions/1/export?format=json").status_code == 200
    assert job(client, pid, "discuss", "확인본에 대해 질문할게요")["revision"] == confirmed["revision"]


def test_first_draft_rejection_can_discuss_and_regenerate(client, repos):
    pid, _, _, _ = setup_business(client, repos)
    process(bundle(client, pid)["job"]["id"])
    proposal = job(client, pid, "generate")["proposal"]
    assert client.post(f"/api/projects/{pid}/proposals/{proposal['id']}/reject", json={"expected_version": 0}).status_code == 200
    result = job(client, pid, "discuss", "예외 처리부터 다시 정리할게요")
    assert result["job"]["status"] == "completed" and result["proposal"] is None
    result = job(client, pid, "generate")
    assert result["proposal"]["id"] != proposal["id"] and result["project"]["current_version"] == 0


def test_failed_and_cancelled_revisions_keep_previous_draft(client, repos, monkeypatch):
    pid, _, _, _ = setup_business(client, repos)
    process(bundle(client, pid)["job"]["id"])
    proposal = job(client, pid, "generate")["proposal"]
    original = worker.generate
    def fail(*args, **kwargs):
        raise ModelError("검증용 모델 실패")
    monkeypatch.setattr(worker, "generate", fail)
    result = job(client, pid, "revise", "일부 수정", proposal["id"])
    assert result["job"]["status"] == "failed" and result["proposal"] == proposal
    monkeypatch.setattr(worker, "generate", original)
    body = {"kind": "revise", "request": "취소할 수정", "base_version": 0, "base_proposal_id": proposal["id"]}
    queued = client.post(f"/api/projects/{pid}/jobs", json=body).json()
    client.post(f"/api/projects/{pid}/jobs/{queued['id']}/cancel", json={})
    process(queued["id"])
    assert bundle(client, pid)["proposal"] == proposal
    assert job(client, pid, "discuss", "대화를 계속할게요", proposal["id"])["job"]["status"] == "completed"


def test_repair_does_not_bypass_validation_or_change_confirmed_revision(client, repos):
    pid, _, _, _ = setup_business(client, repos)
    process(bundle(client, pid)["job"]["id"])
    proposal = job(client, pid, "generate")["proposal"]
    candidate = copy.deepcopy(proposal["candidate"])
    candidate["screens"][0]["blocks"][-1]["target_screen_id"] = "screen-missing"
    response = client.post(f"/api/projects/{pid}/proposals", json={"base_version": 0, "base_proposal_id": proposal["id"], "snapshot": candidate})
    assert response.status_code == 201, response.text
    broken = response.json()
    assert approve(client, pid, broken).status_code == 409
    result = job(client, pid, "repair", "연결 오류만 정리", broken["id"])
    assert not any(issue["severity"] == "blocking" for issue in result["proposal"]["issues"])
    assert result["project"]["current_version"] == 0
    assert client.post(f"/api/projects/{pid}/proposals", json={"base_version": 0, "base_proposal_id": broken["id"], "snapshot": candidate}).status_code == 409


def test_background_check_throttles_and_keeps_project_basis(client, repos, monkeypatch):
    pid, source, snapshot, _ = setup_business(client, repos)
    original = source_api.resolve
    calls = []
    def resolve(source):
        calls.append(source["id"])
        return original(source)
    monkeypatch.setattr(source_api, "resolve", resolve)
    assert client.post(f"/api/sources/{source}/check", json={}).json() == {"scheduled": True}
    assert client.post(f"/api/sources/{source}/check", json={}).json() == {"scheduled": False}
    assert len(calls) == 1
    assert bundle(client, pid)["project"]["code_snapshot_id"] == snapshot["id"]
    with connect() as c:
        c.execute("UPDATE studio_sources SET last_checked_at=now()-interval '6 minutes' WHERE id=%s", (source,))
    assert client.post(f"/api/sources/{source}/check", json={}).json()["scheduled"]
    assert len(calls) == 2


def test_model_scope_must_be_republished_and_safe_design_contract(client, repos, monkeypatch):
    pid, source, snapshot, body = setup_business(client, repos)
    monkeypatch.setattr(settings(), "ai_mode", "live")
    assert client.post("/api/projects", json={**body, "id": str(uuid4())}).status_code == 409
    assert client.post(f"/api/projects/{pid}/jobs", json={"base_version": 0, "kind": "discuss", "request": "추가 설명"}).status_code == 409
    with pytest.raises(ValueError):
        DesignProfile(primary="url(https://invalid.example)")
    with pytest.raises(ValueError):
        Block(id="b", type="table", label="표", content="", target_screen_id=None, columns=["하나"], rows=[["둘", "셋"]])
    assert Block(id="b", type="text", label="구형 시안", content="내용", target_screen_id=None).region == "content"


def test_table_content_and_design_survive_markdown_export(client, repos):
    pid, _, _, _ = setup_business(client, repos)
    process(bundle(client, pid)["job"]["id"])
    proposal = job(client, pid, "generate")["proposal"]
    candidate = copy.deepcopy(proposal["candidate"])
    candidate["screens"][0]["blocks"].append({"id": "block-order-table", "type": "table", "label": "발주 내역", "content": "", "target_screen_id": None,
                                             "columns": ["발주번호", "처리 상태"], "rows": [["PO-001", "반려 | 수정 필요"]]})
    response = client.post(f"/api/projects/{pid}/proposals", json={"base_version": 0, "base_proposal_id": proposal["id"], "snapshot": candidate})
    assert response.status_code == 201, response.text
    assert approve(client, pid, response.json()).status_code == 200
    result = client.get(f"/api/projects/{pid}/revisions/1/export?format=markdown")
    assert "| 발주번호 | 처리 상태 |" in result.text
    assert "반려 \\| 수정 필요" in result.text
    assert "#0c7a6b" in result.text


def test_legacy_project_can_resume_with_business_discussion(client):
    response = client.post("/api/projects", json={"idea": "기존 프로젝트의 업무 개선"})
    pid = response.json()["id"]
    initial = bundle(client, pid)["job"]
    assert initial["prompt_version"] == "studio.v1"
    client.post(f"/api/projects/{pid}/jobs/{initial['id']}/cancel", json={})
    result = job(client, pid, "discuss", "기존 기획의 예외 처리부터 설명할게요")
    assert result["job"]["prompt_version"] == "business.v2"
    assert result["job"]["status"] == "completed"
    assert result["proposal"] is None and result["project"]["current_version"] == 0


def test_pinned_v1_discussion_keeps_previous_contract():
    from app.generation import generate
    context = {"request": "발주 승인 업무를 정리해 주세요"}
    old, _ = generate("discuss", context, {"ai_mode": "mock", "prompt_version": "business.v1"})
    new, _ = generate("discuss", context, {"ai_mode": "mock", "prompt_version": "business.v2"})
    assert "questions" not in old
    assert new["questions"][0]["options"]


def test_bundle_is_consistent_when_worker_finishes_between_reads(client, repos, monkeypatch):
    from contextlib import contextmanager
    from app import main

    pid, _, _, _ = setup_business(client, repos)
    process(bundle(client, pid)["job"]["id"])
    response = client.post(f"/api/projects/{pid}/jobs", json={
        "kind": "generate", "request": "대화한 내용으로 초안을 만들어 주세요", "base_version": 0,
    })
    assert response.status_code == 201
    job_id = response.json()["id"]
    finished = False

    class InterleavedRead:
        def __init__(self, connection):
            self.connection = connection

        def execute(self, query, params=None):
            nonlocal finished
            if "SELECT * FROM studio_jobs WHERE project_id=%s ORDER BY" in query and not finished:
                # The proposal has already been read; commit the worker now.
                finished = True
                process(job_id)
            return self.connection.execute(query, params)

    @contextmanager
    def interleaved_connection():
        with connect() as connection:
            yield InterleavedRead(connection)

    monkeypatch.setattr(main, "connect", interleaved_connection)
    during = bundle(client, pid)
    assert finished
    assert during["proposal"] is None
    assert during["job"]["status"] == "queued"
    after = bundle(client, pid)
    assert after["job"]["status"] == "waiting_review"
    assert after["proposal"] is not None
    assert len(after["messages"]) == len(during["messages"]) + 1
