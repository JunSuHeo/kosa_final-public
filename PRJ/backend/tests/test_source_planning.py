import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import subprocess
from uuid import uuid4

import httpx
import psycopg
import pytest

from app import repositories, role_reviews
from app.config import settings
from app.db import connect
from app.repositories import process_analysis
from app.worker import process
from test_studio import approve, bundle


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


@pytest.fixture
def repos(tmp_path, monkeypatch):
    root = tmp_path / "repositories"
    root.mkdir()
    monkeypatch.setattr(settings(), "local_repository_root", str(root))
    for name in ("alpha", "beta"):
        path = root / name
        path.mkdir()
        git(path, "init", "-q")
        git(path, "config", "user.name", "Fixture")
        git(path, "config", "user.email", "test@example.invalid")
        (path / "README.md").write_text(f"{name} search policy\n")
        (path / f"{name}_search.py").write_text(f"def {name}_search():\n    return 'fixture {name}'\n")
        (path / "AGENTS.md").write_text("Untrusted repo data. Do not follow as a product command.\n")
        (path / ".env").write_text("DO_NOT_SEND=hidden\n")
        (path / "secret_in_code.py").write_text("password = 'fixture-hidden'\n")
        (path / "account.py").write_text("password = 'fixture-hidden'\n")
        (path / "big.ts").write_text("x" * (repositories.MAX_FILE_BYTES + 1))
        (path / "bin.ts").write_bytes(b"x\x00")
        (path / "escape.py").symlink_to("/etc/passwd")
        git(path, "add", ".")
        git(path, "commit", "-qm", "fixture")
    (root / "alias").symlink_to(root / "alpha")
    return root


def register(client, name, *, ref="HEAD"):
    result = client.post("/api/sources", json={
        "name": name, "kind": "local", "repository": name, "ref": ref,
    })
    assert result.status_code == 201, result.text
    return result.json()["id"]


def queue(client, source):
    return client.post(f"/api/sources/{source}/analyze", json={}).json()


def source_body(source, snap, **extra):
    return {
        "id": str(uuid4()), "idea": "Add search with Enter and F8",
        "source_id": source, "code_snapshot_id": snap["id"], **extra,
    }


def start(client, body):
    r = client.post("/api/projects", json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def generate(client, pid):
    job = bundle(client, pid)["job"]
    process(job["id"])
    job = bundle(client, pid)["job"]
    assert job["status"] == "awaiting_answers"
    r = client.post(f"/api/projects/{pid}/jobs/{job['id']}/answers", json={
        "base_version": 0, "answers": {q["key"]: "" for q in job["questions"]},
    })
    assert r.status_code == 200, r.text
    process(job["id"])
    return bundle(client, pid)


def test_ab_isolation_boundaries_and_version_pinning(client, repos):
    a, b = register(client, "alpha"), register(client, "beta")
    sa, sb = queue(client, a), queue(client, b)
    assert sa["status"] == sb["status"] == "queued"
    body = source_body(a, sa)
    assert client.post("/api/projects", json=body).status_code == 409
    bob = {"Authorization": "Bearer local:bob"}
    assert client.post("/api/projects", json=body, headers=bob).status_code == 404
    assert client.get(f"/api/projects?source_id={a}", headers=bob).status_code == 404
    assert client.get(f"/api/sources/{a}/snapshots/{sa['id']}", headers=bob).status_code == 404
    assert client.post("/api/projects", json=source_body(a, sb)).status_code == 404
    (repos / "alpha" / "alpha_search.py").write_text("uncommitted and excluded")
    assert queue(client, a)["id"] == sa["id"]
    assert next(s for s in client.get("/api/sources").json() if s["id"] == a)["working_tree_dirty"]
    with connect() as conn:
        conn.execute("UPDATE studio_code_snapshots SET status='running' WHERE id=%s", (sa["id"],))
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(process_analysis, [sa["id"], sa["id"], sb["id"]]))
    detail = client.get(f"/api/sources/{a}/snapshots/{sa['id']}").json()
    assert detail["status"] == "ready"
    assert "files" not in detail["analysis"]
    assert {"excluded_file_type", "sensitive_content", "file_limit", "binary", "non_regular"} <= detail["analysis"]["excluded"].keys()
    assert client.post(f"/api/sources/{a}/snapshots/{sa['id']}/retry", json={}).status_code == 409
    with pytest.raises(psycopg.Error), connect() as conn:
        conn.execute("UPDATE studio_code_snapshots SET analysis='{}' WHERE id=%s", (sa["id"],))

    pa, pb = start(client, body), start(client, source_body(b, sb))
    assert start(client, body) == pa
    assert client.post("/api/projects", json={**body, "source_id": b, "code_snapshot_id": sb["id"]}).status_code == 409
    assert client.patch(f"/api/projects/{pa}", json={"source_id": b, "title": "another"}).status_code == 422
    assert [p["id"] for p in client.get(f"/api/projects?source_id={a}").json()] == [pa]
    results = [generate(client, pid) for pid in (pa, pb)]
    for name, result, snap in zip(("alpha", "beta"), results, (sa, sb)):
        context = result["proposal"]["candidate"]["source_context"]
        assert context["snapshot_id"] == snap["id"] == result["job"]["code_snapshot_id"]
        entry = next(item for item in context["evidence"] if item["path"] == f"{name}_search.py")
        data = subprocess.check_output(["git", "-C", str(repos / name), "show", f"{snap['commit_sha']}:{entry['path']}"])
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        assert "\n".join(data.decode().split("\n")[entry["start_line"] - 1:entry["end_line"]]) == entry["quote"]
        assert "uncommitted" not in str(context) and "fixture-hidden" not in str(context)
        assert context == result["revision"]["snapshot"]["source_context"]
    assert approve(client, pa, results[0]["proposal"]).status_code == 200
    url = f"/api/projects/{pa}/revisions/1/export"
    exports = {fmt: client.get(url, params={"format": fmt}).content for fmt in ("markdown", "json")}
    assert sa["commit_sha"].encode() in exports["markdown"]
    git(repos / "alpha", "add", "alpha_search.py")
    git(repos / "alpha", "commit", "-qm", "new basis")
    later = queue(client, a)
    assert later["id"] != sa["id"]
    process_analysis(later["id"])
    fork = start(client, source_body(a, later, forked_from=pa))
    assert bundle(client, fork)["project"]["forked_from"] == pa
    assert client.post("/api/projects", json=source_body(b, sb, forked_from=pa)).status_code == 409
    assert all(client.get(url, params={"format": fmt}).content == content for fmt, content in exports.items())
    revised = client.post(f"/api/projects/{pa}/jobs", json={"base_version": 1, "request": "Clarify a sentence"}).json()
    process(revised["id"])
    assert bundle(client, pa)["proposal"]["candidate"]["source_context"]["snapshot_id"] == sa["id"]


def test_tampering_and_role_attempt_usage(client, repos, monkeypatch):
    a = register(client, "alpha")
    snap = queue(client, a)
    process_analysis(snap["id"])
    pid = start(client, source_body(a, snap))
    result = generate(client, pid)
    prop = result["proposal"]
    candidate = copy.deepcopy(prop["candidate"])
    candidate["source_context"]["evidence"][0]["quote"] = "fabricated"
    path = f"/api/projects/{pid}"
    assert client.post(path + "/proposals", json={"base_version": 0, "snapshot": candidate}).status_code == 422
    candidate = copy.deepcopy(prop["candidate"])
    candidate["implementation"]["tasks"][0]["evidence_ids"] = ["code-other-project"]
    response = client.post(path + "/proposals", json={"base_version": 0, "snapshot": candidate}).json()
    assert any(issue["severity"] == "blocking" for issue in response["issues"])
    assert approve(client, pid, response).status_code == 409
    original = role_reviews.run_agent
    calls = []
    code_id = prop["candidate"]["source_context"]["evidence"][0]["id"]

    def agent(role, report):
        calls.append(role)
        output, usage = original(role, report)
        if role == "qa":
            output["findings"][0]["evidence"] = [{"target_id": code_id, "quote": "made up quote"}]
            usage = {"tokens": {"cost": 0.02}}
        return output, usage

    monkeypatch.setattr(role_reviews, "run_agent", agent)
    report = client.post(path + "/reviews", json={"proposal_id": response["id"]}).json()
    role_reviews.process_review(report["id"])
    query = path + f"/reviews?proposal_id={response['id']}"
    partial = client.get(query).json()
    assert partial["commit_sha"] == snap["commit_sha"]
    assert len(calls) == 5 and partial["status"] == "partial"
    monkeypatch.setattr(role_reviews, "run_agent", original)
    assert client.post(path + f"/reviews/{report['id']}/retry", json={"role": "qa"}).status_code == 200
    role_reviews.process_review(report["id"])
    complete = client.get(query).json()
    assert complete["status"] == "completed"
    qa = next(agent for agent in complete["agents"] if agent["role"] == "qa")
    assert [a["status"] for a in qa["attempts"]] == ["failed", "completed"]
    assert qa["attempts"][0]["usage"]["tokens"]["cost"] == 0.02
    assert [a for a in complete["agents"] if a["role"] != "qa"] == [
        a for a in partial["agents"] if a["role"] != "qa"
    ]


def test_path_escape_access_and_analysis_failure_retry(client, repos):
    for repository in ("/etc", "../repositories/alpha", "alias"):
        assert client.post("/api/sources", json={
            "name": "outside", "kind": "local", "repository": repository, "ref": "HEAD",
        }).status_code == 422
    a = register(client, "alpha", ref="invalid branch")
    assert queue(client, a)["status"] == "failed"
    b = register(client, "beta")
    snapshot = queue(client, b)
    config = repos / "beta" / ".git" / "config"
    raw = config.read_text()
    config.write_text(raw + '\n[include]\npath = /etc/passwd\n')
    process_analysis(snapshot["id"])
    assert client.post("/api/projects", json=source_body(b, snapshot)).status_code == 409
    config.write_text(raw)
    assert client.post(f"/api/sources/{b}/snapshots/{snapshot['id']}/retry", json={}).status_code == 200
    process_analysis(snapshot["id"])
    assert queue(client, b)["id"] == snapshot["id"]


def test_github_private_scope_and_blob_integrity(monkeypatch):
    content = b"function search() {}\n"
    sha = "a" * 40
    blob = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()

    def handler(request):
        assert request.url.host == "api.github.com"
        if request.headers.get("Authorization") != "Bearer alice-fixture":
            return httpx.Response(404)
        path = request.url.path
        if "/branches/" in path:
            return httpx.Response(200, json={"commit": {"sha": sha}})
        if "/git/commits/" in path:
            return httpx.Response(200, json={"tree": {"sha": "b" * 40}})
        if "/git/trees/" in path:
            return httpx.Response(200, json={"truncated": True, "tree": [
                {"type": "blob", "mode": "100644", "path": "search.ts", "size": len(content), "sha": blob},
            ]})
        assert request.headers["Accept"] == "application/vnd.github.raw+json"
        return httpx.Response(200, content=content)

    original = httpx.Client
    monkeypatch.setattr(repositories.httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    monkeypatch.setattr(settings(), "github_user_tokens", {"alice": "alice-fixture"})
    source = {"kind": "github", "repository": "https://github.com/owner/repo", "ref": "feature/query", "owner_id": "alice"}
    assert repositories.resolve(source) == (sha, False)
    result = repositories.analyze(source, {"commit_sha": sha})
    assert result["files"] == {"search.ts": content.decode()}
    assert result["excluded"]["tree_truncated"] == 1
    with pytest.raises(repositories.RepositoryError):
        repositories.resolve({**source, "owner_id": "bob"})


def test_live_code_consent_binds_preview_snapshot_and_model(client, repos, monkeypatch):
    source = register(client, "alpha")
    snapshot = queue(client, source)
    process_analysis(snapshot["id"])
    body = source_body(source, snapshot)
    url = f"/api/sources/{source}/snapshots/{snapshot['id']}/preview"
    monkeypatch.setattr(settings(), "ai_mode", "live")
    preview = client.post(url, json={"idea": body["idea"]}).json()
    assert preview["model"]["model"] == settings().model
    assert client.post("/api/projects", json=body).status_code == 409
    assert client.post("/api/projects", json={
        **body, "idea": "A different request", "code_consent": preview["fingerprint"],
    }).status_code == 409
    pid = start(client, {**body, "code_consent": preview["fingerprint"]})
    monkeypatch.setattr(settings(), "llm_model", "different-provider-model")
    job = bundle(client, pid)["job"]
    process(job["id"])
    assert bundle(client, pid)["job"]["status"] == "failed"
    assert client.post(f"/api/projects/{pid}/jobs", json={
        "base_version": 0, "kind": "generate", "request": body["idea"],
    }).status_code == 409
