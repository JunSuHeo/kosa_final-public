"""Local mock load, persisted-stage restart and isolated PostgreSQL restore rehearsal."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ENV = {**os.environ, "STUDIO_COMPOSE_PROJECT": "planning-studio-ops", "STUDIO_DB_PORT": "54333", "STUDIO_API_PORT": "8012", "STUDIO_WEB_PORT": "5176", "AUTH_MODE": "mock", "AI_MODE": "mock"}
OUT = Path("docs/operations-verification.json")
RESULT = {"mode": "mock", "users": 10, "projects_per_user": 2, "requests": [], "checks": {}}


def compose(*args, data=None):
    return subprocess.run(["docker", "compose", *args], env=ENV, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True).stdout


def db(code, database="studio"):
    program = "import json\nfrom app.db import connect\nfrom psycopg.types.json import Jsonb\n" + code
    return json.loads(compose("exec", "-T", "-e", f"DATABASE_URL=postgresql://studio:studio@db:5432/{database}", "api", "python", "-c", program))


def api(owner, path, body=None, expected=200):
    start = time.monotonic()
    req = Request("http://localhost:8012" + path, data=json.dumps(body).encode() if body is not None else None, headers={"Authorization": "Bearer local:" + owner, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=30) as response:
            status, value = response.status, json.load(response)
    except HTTPError as exc:
        status, value = exc.code, json.load(exc)
    RESULT["requests"].append({"status": status, "expected": expected, "seconds": round(time.monotonic() - start, 4)})
    assert status == expected, (path, status, value)
    return value


def wait(owner, path):
    start = time.monotonic()
    while time.monotonic() - start < 120:
        state = api(owner, path)
        job = state["job"]
        if job["status"] == "awaiting_answers":
            api(owner, path + "/jobs/" + job["id"] + "/answers", {"base_version": 0, "answers": {q["key"]: q["options"][0] for q in job["questions"]}})
        if job["status"] == "waiting_review":
            return state
        assert job["status"] not in {"failed", "cancelled"}, job
        time.sleep(0.5)
    raise TimeoutError(path)


def create(index):
    owner = "ops-user-" + str(index % 10)
    start = time.monotonic()
    project = api(owner, "/api/projects", {"title": f"운영 격리 검증 {index}", "idea": "팀 업무를 등록하고 상태를 변경하는 웹"}, 201)
    path = "/api/projects/" + project["id"]
    api("ops-other", path, expected=404)
    state = wait(owner, path)
    return {"owner": owner, "path": path, "state": state, "seconds": round(time.monotonic() - start, 3)}


def fingerprint(database="studio"):
    return db("""import hashlib
with connect() as c:
    tables = [r['tablename'] for r in c.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
    result = {}
    for table in tables:
        rows = c.execute('SELECT to_jsonb(t) AS row FROM "' + table + '" t ORDER BY to_jsonb(t)::text').fetchall()
        result[table] = {'count': len(rows), 'sha256': hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest()}
print(json.dumps(result))
""", database)


def main():
    health = api("ops-user-0", "/health")
    assert health["auth_mode"] == health["ai_mode"] == "mock"
    # This script must never operate on the product Compose project.
    assert ENV["STUDIO_COMPOSE_PROJECT"] == "planning-studio-ops"
    start = time.monotonic()
    with ThreadPoolExecutor(10) as pool:
        runs = list(pool.map(create, range(20)))
    RESULT["generation_seconds"] = [r["seconds"] for r in runs]
    RESULT["load_elapsed_seconds"] = round(time.monotonic() - start, 3)
    fixture = runs[0]
    path, owner = fixture["path"], fixture["owner"]
    proposal = fixture["state"]["proposal"]
    with ThreadPoolExecutor(10) as pool:
        approvals = list(pool.map(lambda _: api(owner, path + "/proposals/" + proposal["id"] + "/approve", {"expected_version": 0, "acknowledge_warnings": True}), range(10)))
    RESULT["checks"]["concurrent_approval_once"] = all(a["version"] == 1 for a in approvals) and api(owner, path)["project"]["current_version"] == 1
    with ThreadPoolExecutor(10) as pool:
        reports = list(pool.map(lambda _: api(owner, path + "/reviews", {"version": 1}, 201), range(10)))
    RESULT["checks"]["one_review"] = len({r["id"] for r in reports}) == 1
    start = time.monotonic()
    while time.monotonic() - start < 120:
        report = api(owner, path + "/reviews?version=1")
        if report["status"] == "completed":
            break
        time.sleep(0.5)
    assert report["status"] == "completed"
    compose("stop", "worker")
    pending = api(owner, "/api/projects", {"title": "복구용 저장 단계", "idea": "팀 업무를 등록하고 상태를 변경하는 웹"}, 201)
    pending_path = "/api/projects/" + pending["id"]
    pending_state = api(owner, pending_path)
    jid = pending_state["job"]["id"]
    partial = {"prd": fixture["state"]["job"]["partial"]["prd"]}
    initial_usage = fixture["state"]["job"]["usage"][:2]
    answers = fixture["state"]["job"]["answers"]
    db(f"""with connect() as c:
    c.execute("UPDATE studio_jobs SET status='running',stage='features',partial=%s,usage=%s,answers=%s WHERE id=%s", (Jsonb({partial!r}), Jsonb({initial_usage!r}), Jsonb({answers!r}), {jid!r}))
print('true')
""")
    before = fingerprint()
    dump = compose("exec", "-T", "db", "pg_dump", "-U", "studio", "-d", "studio", "-Fc")
    backup = Path(".research/operations")
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "studio-mock.dump").write_bytes(dump)
    # Unique database name prevents accidental replacement of any earlier restore.
    restore_db = "studio_restore_" + str(int(time.time()))
    compose("exec", "-T", "db", "createdb", "-U", "studio", restore_db)
    start = time.monotonic()
    compose("exec", "-T", "db", "pg_restore", "-U", "studio", "-d", restore_db, "--exit-on-error", data=dump)
    RESULT["restore_seconds"] = round(time.monotonic() - start, 3)
    RESULT["restored_database"] = restore_db
    RESULT["checks"]["all_tables_exact_restore"] = before == fingerprint(restore_db)
    RESULT["table_fingerprints"] = before
    RESULT["checks"]["immutable_revision_trigger"] = db("""import psycopg
blocked = False
try:
    with connect() as c:
        c.execute("UPDATE studio_revisions SET summary='invalid change' WHERE version=1")
except psycopg.Error as exc:
    blocked = 'Approved revisions are immutable' in str(exc)
print(json.dumps(blocked))
""", restore_db)
    start = time.monotonic()
    db(f"from app.worker import process\nprocess({jid!r})\nprint('true')", restore_db)
    restored = db(f"""with connect() as c:
    job = c.execute('SELECT status,partial,usage FROM studio_jobs WHERE id=%s', ({jid!r},)).fetchone()
    count = c.execute('SELECT count(*) AS n FROM studio_proposals WHERE job_id=%s', ({jid!r},)).fetchone()['n']
print(json.dumps({{'job':job,'proposal_count':count}}))
""", restore_db)
    RESULT["restored_job_seconds"] = round(time.monotonic() - start, 3)
    RESULT["restored_job"] = restored
    RESULT["checks"]["restored_pending_job_resumes"] = restored["job"]["status"] == "waiting_review" and restored["proposal_count"] == 1 and restored["job"]["partial"]["prd"] == partial["prd"] and restored["job"]["usage"][:2] == initial_usage and len(restored["job"]["usage"]) == 5
    compose("start", "worker")
    resumed = wait(owner, pending_path)
    RESULT["resumed_job"] = resumed["job"]
    RESULT["checks"]["worker_process_restart_resumes_saved_stage"] = resumed["job"]["partial"]["prd"] == partial["prd"] and resumed["job"]["usage"][:2] == initial_usage and len(resumed["job"]["usage"]) == 5
    counts = db("""with connect() as c:
    duplicates = c.execute('SELECT count(*) AS n FROM (SELECT job_id FROM studio_proposals WHERE job_id IS NOT NULL GROUP BY job_id HAVING count(*)>1) t').fetchone()['n']
print(json.dumps({'duplicate_job_proposals':duplicates}))
""")
    RESULT["checks"]["no_duplicate_proposals"] = counts["duplicate_job_proposals"] == 0
    RESULT["checks"]["no_unexpected_http_errors"] = all(r["status"] == r["expected"] for r in RESULT["requests"])
    RESULT["checks"]["time_limits"] = max(RESULT["generation_seconds"]) < 120 and RESULT["restore_seconds"] < 120
    RESULT["passed"] = all(RESULT["checks"].values())
    print(json.dumps({"passed": RESULT["passed"], "checks": RESULT["checks"]}), flush=True)
    assert RESULT["passed"]


if __name__ == "__main__":
    try:
        main()
    finally:
        OUT.write_text(json.dumps(RESULT, ensure_ascii=False, indent=2))
