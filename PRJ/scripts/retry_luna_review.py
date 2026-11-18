"""Retry failed roles only, preserving the initial failure artifact."""

import json
from pathlib import Path
import time
from urllib.request import Request, urlopen


def api(path, body=None):
    with urlopen(Request("http://localhost:8010" + path, data=json.dumps(body).encode() if body is not None else None, headers={"Authorization": "Bearer local:demo-user", "Content-Type": "application/json"}), timeout=30) as response:
        return json.load(response)


before = json.loads(Path("docs/luna-live-review-smoke.json").read_text())
report = before["report"]
path = "/api/projects/" + before["project_id"]
planning = api(path)
failed = [a["role"] for a in report["agents"] if a["status"] == "failed"]
for role in failed:
    api(path + "/reviews/" + report["id"] + "/retry", {"role": role})
start = time.monotonic()
while True:
    after = api(path + "/reviews?proposal_id=" + report["proposal_id"])
    if after["status"] not in {"queued", "running"}:
        break
    if time.monotonic() - start > 900:
        raise TimeoutError("Existing retry still active; inspect before further action")
    time.sleep(3)
final = api(path)
checks = {
    "all_completed": after["status"] == "completed",
    "completed_roles_unchanged": all(a == next(b for b in after["agents"] if b["role"] == a["role"]) for a in report["agents"] if a["status"] == "completed"),
    "planning_unchanged": all(planning[k] == final[k] for k in ("revision", "proposal")) and planning["project"]["current_version"] == final["project"]["current_version"],
}
Path("docs/luna-live-review-retry.json").write_text(json.dumps({"retried_roles": failed, "elapsed_seconds": round(time.monotonic() - start, 2), "checks": checks, "report": after}, ensure_ascii=False, indent=2))
print(json.dumps(checks), flush=True)
assert all(checks.values())
