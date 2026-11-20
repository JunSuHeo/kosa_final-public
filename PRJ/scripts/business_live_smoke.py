"""Live evaluation against an isolated, synthetic repository. Never uses business sources."""
import argparse
import copy
import json
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

parser = argparse.ArgumentParser()
parser.add_argument("--base-url", default="http://localhost:8013")
parser.add_argument("--repository", default="business-live-fixture")
parser.add_argument("--output", default="docs/business-live-smoke.json")
args = parser.parse_args()
if not args.repository.startswith("business-live-fixture"):
    raise SystemExit("Only the synthetic business-live-fixture repository is allowed.")
output = Path(args.output)
if output.exists():
    raise SystemExit("Output already exists; choose a new --output to preserve evaluation evidence.")
report = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "runs": []}


def save():
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


def api(path, body=None):
    request = urllib.request.Request(args.base_url + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer local:hplan-live-evaluation"})
    with urllib.request.urlopen(request, timeout=40) as response:
        return json.load(response)


def observe(path, key, terminals, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = api(path)
        state = result[key]["status"] if key else result["status"]
        if state in terminals:
            return result
        time.sleep(1)
    raise TimeoutError("Observation timed out; the job remains stored in the isolated database.")


def finish_job(pid):
    result = observe(f"/api/projects/{pid}", "job", {"completed", "waiting_review", "failed", "cancelled", "awaiting_answers"})
    report["runs"].append({"job": result["job"], "brief": result["project"]["conversation_brief"],
                           "reply": result["messages"][-1]["content"], "issues": result["proposal"]["issues"] if result["proposal"] else []})
    save()
    if result["job"]["status"] in {"failed", "cancelled", "awaiting_answers"}:
        raise RuntimeError(result["job"]["error"] or result["job"]["status"])
    return result


def run_job(pid, kind, request, proposal=None, target=None):
    current = api(f"/api/projects/{pid}")
    api(f"/api/projects/{pid}/jobs", {"id": str(uuid4()), "kind": kind, "request": request,
        "base_version": current["project"]["current_version"], "base_proposal_id": proposal, "target_id": target})
    return finish_job(pid)


try:
    health = api("/health")
    if health["auth_mode"] != "mock" or health["ai_mode"] != "live":
        raise RuntimeError("Requires isolated local mock authentication and real AI.")
    report["health"] = health
    source = next((source for source in api("/api/sources") if source["repository"] == args.repository), None)
    if not source:
        source = api("/api/sources", {"name": "H-PlanIT live 검증용 발주업무", "description": "가상 발주 요청과 승인 업무. 운영 데이터와 무관한 검증용 코드입니다.",
            "kind": "local", "repository": args.repository, "ref": "HEAD"})
    snapshot = api(f"/api/sources/{source['id']}/analyze", {})
    if "id" not in snapshot:
        raise RuntimeError(snapshot.get("error", "Synthetic repository could not be resolved."))
    detail = observe(f"/api/sources/{source['id']}/snapshots/{snapshot['id']}", None, {"ready", "failed"})
    if detail["status"] != "ready":
        raise RuntimeError("Synthetic repository analysis failed.")
    preview = api(f"/api/sources/{source['id']}/snapshots/{snapshot['id']}/publication-preview", {})
    publication = api(f"/api/sources/{source['id']}/publish", {"snapshot_id": snapshot["id"], "fingerprint": preview["fingerprint"], "design_profile": preview["design_profile"]})
    project = api("/api/projects", {"id": str(uuid4()), "title": "H-PlanIT 실제 모델 발주 업무 검증",
        "idea": "발주를 반려할 때 사유를 반드시 입력하도록 개선하고 싶어요. 발주 담당자가 반려 이유를 보고 수정할 수 있으면 좋겠어요.",
        "start_mode": "conversation", "planning_intent": "improve", "source_id": source["id"], "code_snapshot_id": snapshot["id"], "source_publication_id": publication["id"]})
    pid = project["id"]
    report.update(project_id=pid, source_id=source["id"], code_snapshot_id=snapshot["id"])
    result = finish_job(pid)
    assert result["proposal"] is None
    result = run_job(pid, "discuss", "발주 담당자가 요청하고 팀장이 승인 또는 반려해요. 반려 사유는 공백을 제외한 10자 이상으로 정하고, 담당자가 내용을 수정해 재요청할 수 있게 해 주세요. 기존 승인 처리와 발주 내역 조회는 유지해 주세요.")
    assert result["proposal"] is None
    result = run_job(pid, "generate", "지금까지 정리한 발주 반려 사유와 재요청 업무로 초안을 만들어 주세요.")
    proposal = result["proposal"]
    report["initial_candidate"] = proposal["candidate"]
    if any(issue["severity"] == "blocking" for issue in proposal["issues"]):
        raise RuntimeError("The live draft has blocking validation issues; approval was not bypassed.")
    target = next(block for screen in proposal["candidate"]["screens"] for block in screen["blocks"] if block["type"] == "button")
    desired = target["label"] + " · 확인"
    request = f"선택한 버튼의 표시 문구(label)만 ‘{desired}’로 바꿔 주세요. 나머지 항목, 내용, 연결, 순서는 모두 유지해 주세요."
    result = run_job(pid, "discuss", request, proposal["id"], target["id"])
    assert result["proposal"]["id"] == proposal["id"]
    result = run_job(pid, "revise", request, proposal["id"], target["id"])
    expected = copy.deepcopy(proposal["candidate"])
    next(block for screen in expected["screens"] for block in screen["blocks"] if block["id"] == target["id"])["label"] = desired
    report["final_candidate"] = result["proposal"]["candidate"]
    report["checks"] = {"discussion_does_not_generate": True, "draft_blocking_count": sum(issue["severity"] == "blocking" for issue in result["proposal"]["issues"]),
        "only_selected_label_changed": expected == result["proposal"]["candidate"], "confirmed_version_unchanged": result["project"]["current_version"] == 0,
        "design_preserved": result["proposal"]["candidate"]["design_profile"] == preview["design_profile"],
        "business_terms_in_prd": "발주" in json.dumps(proposal["candidate"]["prd"], ensure_ascii=False)}
    report["status"] = "completed"
    save()
    print(json.dumps({"status": report["status"], "project_id": pid, "checks": report["checks"]}, ensure_ascii=False))
except Exception as error:
    report["status"] = "failed"
    report["error"] = str(error)[:500]
    save()
    raise
