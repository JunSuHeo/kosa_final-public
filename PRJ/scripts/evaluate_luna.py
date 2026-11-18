"""Run the fixed six-case live evaluation; retain failures and resumable evidence."""

import copy
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

ROOT = Path("docs/luna-evaluation")
CASES = {
    "reading": "개인 사용자가 읽은 책과 짧은 감상을 기록하고 월별 기록을 조회하는 모바일 웹. 책 등록, 기록 작성과 수정, 월별 조회가 핵심이며 커뮤니티와 결제는 제외한다.",
    "rooms": "소규모 회사 구성원이 회의실별 빈 시간을 조회하고 예약을 생성·취소하는 모바일 웹. 겹치는 예약 방지와 내 예약 조회가 핵심이며 결제와 외부 캘린더 연동은 제외한다.",
    "events": "주민이 동네 행사 일정을 날짜별로 조회하고 관심 행사를 저장·해제하는 모바일 웹. 행사 상세 조회와 관심 목록이 핵심이며 결제, 채팅, 외부 공유는 제외한다.",
}


def api(path, body=None):
    req = Request(
        "http://localhost:8010" + path,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={"Authorization": "Bearer local:demo-user", "Content-Type": "application/json"},
    )
    with urlopen(req, timeout=30) as response:
        return json.load(response)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def wait_job(path):
    start = time.monotonic()
    while time.monotonic() - start < 1000:
        state = api(path)
        job = state["job"]
        if job["status"] == "awaiting_answers":
            answers = {q["key"]: next((o for o in q["options"] if "모바일" in o), q["options"][0]) for q in job["questions"]}
            api(path + "/jobs/" + job["id"] + "/answers", {"base_version": job["base_version"], "answers": answers})
        if job["status"] in {"failed", "cancelled", "waiting_review"}:
            return state
        time.sleep(2)
    raise TimeoutError("Job observation timed out; inspect persisted job before resuming")


def usage(record):
    calls = []
    for stage in ("generation", "revision"):
        calls += record.get(stage, {}).get("job", {}).get("usage", [])
    calls += [a["usage"] for a in record.get("review", {}).get("agents", []) if a.get("usage")]
    return calls


def budget():
    records = [json.loads(p.read_text()) for p in ROOT.glob("*.json")]
    calls = [c for record in records for c in usage(record)]
    unknown = sum(c.get("tokens", {}).get("cost") is None for c in calls)
    unknown += sum(a["status"] == "failed" and not a.get("usage") for record in records for a in record.get("review", {}).get("agents", []))
    unknown += sum(record.get(stage, {}).get("job", {}).get("status") == "failed" for record in records for stage in ("generation", "revision"))
    if sum(c.get("tokens", {}).get("cost") or 0 for c in calls) + unknown * 0.25 >= 3:
        raise RuntimeError("US$3 evaluation budget reached")


def run(key, idea):
    output = ROOT / (key + ".json")
    record = json.loads(output.read_text()) if output.exists() else {"case": key, "idea": idea, "human_review": None}
    if record.get("finished"):
        return
    started = time.monotonic()
    if "project_id" not in record:
        budget()
        project = api("/api/projects", {"title": "Luna 평가 · " + key, "idea": idea})
        record["project_id"] = project["id"]
        save(output, record)
    path = "/api/projects/" + record["project_id"]
    if "generation" not in record:
        record["generation"] = wait_job(path)
        save(output, record)
    before = record["generation"]
    prop = before["proposal"]
    if not prop or any(i["severity"] == "blocking" for i in prop["issues"]):
        record.update(finished=True, structural_pass=False, failure="generation")
        save(output, record)
        return
    baseline = prop["candidate"]
    if "revision_job_id" not in record:
        budget()
        api(path + "/proposals/" + prop["id"] + "/approve", {"expected_version": 0, "acknowledge_warnings": True})
        block = next(b for w in baseline["screens"] for b in w["blocks"] if b["type"] == "button")
        label = block["label"] + " · 확인"
        record["edit"] = {"target": block["id"], "label": label}
        # Persist the client-generated id before POST so a resumed run is idempotent.
        from uuid import uuid4
        record["revision_job_id"] = str(uuid4())
        save(output, record)
    if "revision" not in record:
        edit = record["edit"]
        api(path + "/jobs", {"id": record["revision_job_id"], "base_version": 1, "target_id": edit["target"], "request": f"버튼 {edit['target']}의 label만 정확히 '{edit['label']}'로 변경해줘. 그 외 모든 필드, ID, 순서와 연결은 유지해줘."})
        record["revision"] = wait_job(path)
        save(output, record)
    after = record["revision"]
    candidate = after["proposal"]
    expected = copy.deepcopy(baseline)
    next(b for w in expected["screens"] for b in w["blocks"] if b["id"] == record["edit"]["target"])["label"] = record["edit"]["label"]
    record["checks"] = {
        "revision_unchanged": after["revision"]["snapshot"] == baseline,
        "version_unchanged": after["project"]["current_version"] == 1,
        "exact_edit": bool(candidate and candidate["candidate"] == expected),
        "no_blocking": bool(candidate and not any(i["severity"] == "blocking" for i in candidate["issues"])),
    }
    save(output, record)
    if not candidate:
        record.update(finished=True, structural_pass=False, failure="revision")
        save(output, record)
        return
    if "review" not in record:
        budget()
        report = api(path + "/reviews", {"proposal_id": candidate["id"]})
        record["review_id"] = report["id"]
        save(output, record)
        start = time.monotonic()
        while report["status"] in {"queued", "running"}:
            if time.monotonic() - start > 900:
                raise TimeoutError("Review observation timed out; inspect existing review")
            time.sleep(3)
            report = api(path + "/reviews?proposal_id=" + candidate["id"])
        record["review"] = report
        final = api(path)
        record["checks"]["review_preserves_planning"] = all(final[k] == after[k] for k in ("revision", "proposal")) and final["project"]["current_version"] == 1
        record["checks"]["five_roles_completed"] = report["status"] == "completed" and len(report["agents"]) == 5
    record.update(finished=True, structural_pass=all(record["checks"].values()), elapsed_seconds=round(time.monotonic() - started, 2))
    save(output, record)
    print(json.dumps({"case": key, "passed": record["structural_pass"], "seconds": record["elapsed_seconds"]}), flush=True)


def main():
    ROOT.mkdir(exist_ok=True)
    health = api("/health")
    assert (health["auth_mode"], health["ai_mode"], health["model"]) == ("mock", "live", "openai/gpt-6-luna")
    for domain, idea in CASES.items():
        for repeat in (1, 2):
            run(f"{domain}-{repeat}", idea)


if __name__ == "__main__":
    main()
