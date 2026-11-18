"""Create one clearly named live verification project; never approve its output."""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8010")
    parser.add_argument("--output", default="docs/live-smoke.json")
    args = parser.parse_args()

    def api(path, body=None):
        data = (
            json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        )
        req = Request(
            args.base_url + path,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer local:demo-user",
            },
        )
        with urlopen(req, timeout=30) as response:
            return json.load(response)

    health = api("/health")
    assert health["ai_mode"] == "live" and health["auth_mode"] == "mock", (
        "Requires explicit local authentication and live AI"
    )
    project = api(
        "/api/projects",
        {
            "title": "독서 기록 서비스 · 실제 AI 검증",
            "idea": "개인 사용자가 읽은 책, 인상 깊은 문장, 짧은 감상을 기록하고 월별 독서 습관을 돌아보는 모바일 웹 서비스를 기획해줘. 핵심 범위는 책 등록, 독서 기록 작성과 수정, 월별 기록 조회이며 커뮤니티와 결제는 제외해줘.",
        },
    )
    path = "/api/projects/" + project["id"]
    print(
        json.dumps(
            {
                "project_id": project["id"],
                "provider": health["provider"],
                "model": health["model"],
            }
        ),
        flush=True,
    )
    started = time.monotonic()
    previous = None
    observations = []
    answered = False
    while time.monotonic() - started < 1000:
        state = api(path)
        job = state["job"]
        key = (job["status"], job["stage"])
        if key != previous:
            observation = {
                "status": key[0],
                "stage": key[1],
                "elapsed_seconds": round(time.monotonic() - started, 2),
            }
            observations.append(observation)
            print(json.dumps(observation), flush=True)
            previous = key
        if job["status"] == "awaiting_answers" and not answered:
            answers = {
                q["key"]: next(
                    (o for o in q["options"] if "모바일" in o), q["options"][0]
                )
                for q in job["questions"]
            }
            api(
                path + "/jobs/" + job["id"] + "/answers",
                {"base_version": job["base_version"], "answers": answers},
            )
            answered = True
        if job["status"] in {"waiting_review", "failed", "cancelled"}:
            proposal = state["proposal"]
            snapshot = proposal["candidate"] if proposal else None
            report = {
                "health": health,
                "project_id": project["id"],
                "job_id": job["id"],
                "status": job["status"],
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "observations": observations,
                "error": job["error"],
                "model_calls": len(job["usage"]),
                "usage": job["usage"],
                "current_version": state["project"]["current_version"],
                "issues": proposal["issues"] if proposal else [],
                "counts": {
                    "prd_sections": len(snapshot["prd"]["sections"]),
                    "requirements": len(snapshot["requirements"]),
                    "features": len(snapshot["features"]),
                    "nodes": len(snapshot["flow"]["nodes"]),
                    "edges": len(snapshot["flow"]["edges"]),
                    "screens": len(snapshot["screens"]),
                }
                if snapshot
                else None,
            }
            Path(args.output).write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            print(
                json.dumps(
                    {
                        "status": report["status"],
                        "counts": report["counts"],
                        "issues": report["issues"],
                        "calls": report["model_calls"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if job["status"] != "waiting_review" or any(
                i["severity"] == "blocking" for i in report["issues"]
            ):
                raise SystemExit(1)
            return
        time.sleep(2)
    raise TimeoutError("Live verification did not reach a terminal/review state")


if __name__ == "__main__":
    main()
