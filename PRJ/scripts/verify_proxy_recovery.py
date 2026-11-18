"""Force an API IP change in the isolated ops network; keep nginx running."""

import json
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from verify_operations import compose


def docker(*args):
    return subprocess.check_output(["docker", *args]).decode().strip()


def ip():
    cid = compose("ps", "-q", "api").decode().strip()
    return docker("inspect", "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", cid)


compose("up", "--build", "-d", "web")
old = ip()
web_before = compose("ps", "-q", "web").decode().strip()
compose("exec", "-T", "web", "nginx", "-t")
holder = "planning-studio-ops-dns-holder"
result = {"old_api_ip": old}
try:
    compose("stop", "api")
    compose("rm", "-f", "api")
    docker("run", "-d", "--rm", "--name", holder, "--network", "planning-studio-ops_default", "--ip", old, "--entrypoint", "sleep", "postgres:17-alpine", "120")
    compose("up", "-d", "--no-deps", "api")
    result["new_api_ip"] = ip()
    start = time.monotonic()
    while time.monotonic() - start < 40:
        try:
            with urlopen("http://localhost:5176/health", timeout=3) as response:
                result["health"] = json.load(response)
            with urlopen(Request("http://localhost:5176/api/projects", headers={"Authorization": "Bearer local:ops-user-0"}), timeout=3) as response:
                result["project_list_status"] = response.status
            break
        except OSError:
            time.sleep(1)
    result["recovery_seconds"] = round(time.monotonic() - start, 3)
    result["web_container_unchanged"] = web_before == compose("ps", "-q", "web").decode().strip()
    result["passed"] = old != result["new_api_ip"] and result["web_container_unchanged"] and result.get("health", {}).get("database") == "ready" and result.get("project_list_status") == 200
    print(json.dumps(result), flush=True)
    assert result["passed"]
finally:
    subprocess.run(["docker", "rm", "-f", holder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path("docs/proxy-recovery-verification.json").write_text(json.dumps(result, indent=2))
