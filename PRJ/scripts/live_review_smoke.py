"""Review an existing project without approving or changing its planning snapshot."""

import argparse
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("project_id")
parser.add_argument("--output", default="docs/live-review-smoke.json")
args = parser.parse_args()
base = "http://localhost:8010"
headers = {
    "Authorization": "Bearer local:demo-user",
    "Content-Type": "application/json",
}


def api(path, body=None):
    req = Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    with urlopen(req, timeout=30) as r:
        return json.load(r)


health = api("/health")
assert health["auth_mode"] == "mock" and health["ai_mode"] == "live", health
path = f"/api/projects/{args.project_id}"
before = api(path)
target = (
    {"proposal_id": before["proposal"]["id"]}
    if before["proposal"]
    else {"version": before["project"]["current_version"]}
)
assert target.get("proposal_id") or target.get("version", 0) > 0
started = time.monotonic()
report = api(path + "/reviews", target)
query = "&".join(f"{k}={v}" for k, v in target.items())
last = None
while report["status"] in ("queued", "running"):
    progress = [(a["role"], a["status"]) for a in report["agents"]]
    if progress != last:
        print(json.dumps(progress, ensure_ascii=False), flush=True)
        last = progress
    assert time.monotonic() - started < 900, (
        "Review timed out; worker retains durable state"
    )
    time.sleep(3)
    report = api(path + "/reviews?" + query)
after = api(path)
checks = {
    "revision_unchanged": before["revision"] == after["revision"],
    "proposal_unchanged": before["proposal"] == after["proposal"],
    "current_version_unchanged": before["project"]["current_version"]
    == after["project"]["current_version"],
}
assert all(checks.values()), checks
artifact = {
    "project_id": args.project_id,
    "elapsed_seconds": round(time.monotonic() - started, 2),
    "checks": checks,
    "report": report,
}
Path(args.output).write_text(
    json.dumps(artifact, ensure_ascii=False, indent=2)
)
print(
    json.dumps(
        {
            "status": report["status"],
            "elapsed_seconds": artifact["elapsed_seconds"],
            **checks,
            "roles": [
                {
                    "role": a["role"],
                    "status": a["status"],
                    "findings": len((a["result"] or {}).get("findings", [])),
                    "error": a["error"],
                }
                for a in report["agents"]
            ],
        },
        ensure_ascii=False,
    ),
    flush=True,
)
assert report["status"] == "completed", (
    "Some role reviews failed; inspect artifact and retry failed roles"
)
