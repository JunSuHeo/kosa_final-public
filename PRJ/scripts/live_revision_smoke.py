"""Approve our named smoke fixture, request a narrow live edit, and keep it pending."""
import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def api(path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    with urlopen(Request("http://localhost:8010" + path, data=data, headers={
        "Content-Type": "application/json", "Authorization": "Bearer local:demo-user"}), timeout=30) as r:
        return json.load(r)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="docs/live-smoke.json")
    parser.add_argument("--output", default="docs/live-revision-smoke.json")
    args = parser.parse_args()
    report = json.loads(Path(args.input).read_text())
    path = "/api/projects/" + report["project_id"]
    state = api(path)
    assert state["project"]["title"] == "독서 기록 서비스 · 실제 AI 검증"
    assert state["project"]["current_version"] == 0 and state["proposal"]
    baseline = state["proposal"]["candidate"]
    screen = next(w for w in baseline["screens"] if "수정" in w["title"])
    block = next(b for b in screen["blocks"] if b["type"] == "button" and "저장" in b["label"])
    api(path + "/proposals/" + state["proposal"]["id"] + "/approve", {"expected_version": 0, "acknowledge_warnings": True})
    request = f"와이어프레임 '{screen['title']}'의 버튼 {block['id']} 표시 텍스트를 정확히 '변경 저장하기'로 바꿔줘. 다른 항목의 내용, ID, 연결, 위치, 순서는 그대로 유지해줘."
    job = api(path + "/jobs", {"base_version": 1, "request": request, "target_id": block["id"]})
    print(json.dumps({"job_id": job["id"], "target": block["id"]}), flush=True)
    started = time.monotonic()
    while time.monotonic() - started < 400:
        state = api(path)
        if state["job"]["status"] in {"failed", "waiting_review"}:
            proposal = state["proposal"]
            after = proposal["candidate"] if proposal else None
            after_block = next((b for w in after["screens"] for b in w["blocks"] if b["id"] == block["id"]), None) if after else None
            expected = json.loads(json.dumps(baseline))
            next(b for w in expected["screens"] for b in w["blocks"] if b["id"] == block["id"])["label"] = "변경 저장하기"
            checks = {"approved_snapshot_unchanged": state["revision"]["snapshot"] == baseline,
                      "current_version_still_one": state["project"]["current_version"] == 1,
                      "requested_label_applied": bool(after_block and after_block["label"] == "변경 저장하기"),
                      "only_requested_field_changed": after == expected,
                      "no_blocking_issues": bool(proposal and not any(i["severity"] == "blocking" for i in proposal["issues"]))}
            result = {"project_id": report["project_id"], "job_id": job["id"], "status": state["job"]["status"],
                      "elapsed_seconds": round(time.monotonic() - started, 2), "checks": checks,
                      "error": state["job"]["error"], "usage": state["job"]["usage"], "diff": proposal["diff"] if proposal else []}
            Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2))
            print(json.dumps({"status": result["status"], "elapsed_seconds": result["elapsed_seconds"], "checks": checks}, ensure_ascii=False), flush=True)
            if not all(checks.values()):
                raise SystemExit(1)
            return
        time.sleep(2)
    raise TimeoutError("Live revision did not complete")


if __name__ == "__main__":
    main()
