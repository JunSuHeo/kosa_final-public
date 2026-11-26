from hashlib import sha1
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet
import httpx

from app.config import settings
from app.db import connect
from app.repositories import process_analysis


def test_github_connection_is_owner_bound_and_used_for_source_analysis(client, monkeypatch):
    for name, value in {
        "github_app_client_id": "test-app",
        "github_app_client_secret": "test-secret",
        "github_app_callback_url": "http://localhost:5178/github/callback",
        "github_app_slug": "hplanit-test",
        "github_token_encryption_key": Fernet.generate_key().decode(),
        "github_user_tokens": '{"alice":"legacy-token"}',
    }.items():
        monkeypatch.setenv(name.upper(), value)
    settings.cache_clear()
    try:
        assert client.get("/api/sources/github").json()["connected"] is False
        start = client.post("/api/sources/github/start").json()
        query = parse_qs(urlsplit(start["url"]).query)
        assert query["code_challenge_method"] == ["S256"]
        data = {"state": query["state"][0], "code": "example-code"}
        assert client.post("/api/sources/github/complete", json=data, headers={
            "Authorization": "Bearer local:bob"
        }).status_code == 400

        content = b"# Private fixture\n"
        oid = sha1(f"blob {len(content)}\0".encode() + content).hexdigest()

        def github(request):
            if request.url.path == "/login/oauth/access_token":
                refresh = b"grant_type=refresh_token" in request.content
                if refresh:
                    assert b"refresh_token=refresh-token" in request.content
                else:
                    assert b"code_verifier=" in request.content
                return httpx.Response(200, json={
                    "access_token": "rotated-token" if refresh else "private-token", "expires_in": 28800,
                    "refresh_token": "refresh-token", "refresh_token_expires_in": 15811200,
                })
            path = request.url.path
            if path == "/repos/octo/legacy/branches/main":
                if request.headers["Authorization"] == "Bearer legacy-token":
                    return httpx.Response(200, json={"commit": {"sha": "c" * 40}})
                assert request.headers["Authorization"] == "Bearer rotated-token"
                return httpx.Response(404)
            token = "rotated-token" if "/git/" in path else "private-token"
            assert request.headers["Authorization"] == f"Bearer {token}"
            if path == f"/repos/octo/private/git/blobs/{oid}":
                return httpx.Response(200, content=content)
            payloads = {
                "/user": {"login": "octo"},
                "/user/installations": {"installations": [{"id": 10}]},
                "/user/installations/10/repositories": {"repositories": [
                    {"full_name": "octo/private", "default_branch": "trunk", "private": True}
                ]},
                "/repos/octo/private/branches/trunk": {"commit": {"sha": "a" * 40}},
                f"/repos/octo/private/git/commits/{'a' * 40}": {"tree": {"sha": "b" * 40}},
                f"/repos/octo/private/git/trees/{'b' * 40}": {"tree": [
                    {"path": "README.md", "size": len(content), "type": "blob", "sha": oid, "mode": "100644"},
                ]},
            }
            return httpx.Response(200, json=payloads[request.url.path])

        original = httpx.Client

        def make_client(*args, **kwargs):
            return original(*args, **kwargs, transport=httpx.MockTransport(github))

        monkeypatch.setattr(httpx, "Client", make_client)
        completed = client.post("/api/sources/github/complete", json=data)
        assert completed.status_code == 200
        assert "private-token" not in completed.text
        assert client.post("/api/sources/github/complete", json=data).status_code == 400
        assert client.get("/api/sources/github").json()["login"] == "octo"
        assert client.get("/api/sources/github/repositories").json() == [
            {"name": "octo/private", "branch": "trunk", "private": True}
        ]
        source = client.post("/api/sources", json={
            "name": "private", "kind": "github", "repository": "https://github.com/octo/private",
            "ref": "trunk",
        }).json()
        assert not client.get("/api/sources/github", headers={"Authorization": "Bearer local:bob"}).json()["connected"]
        snapshot = client.post(f"/api/sources/{source['id']}/analyze", json={}).json()
        assert snapshot["commit_sha"] == "a" * 40
        with connect() as connection:
            connection.execute("UPDATE studio_github_connections SET expires_at=now() WHERE owner_id='alice'")
        process_analysis(snapshot["id"])
        detail = client.get(f"/api/sources/{source['id']}/snapshots/{snapshot['id']}").json()
        assert detail["status"] == "ready", detail.get("error")
        legacy = client.post("/api/sources", json={
            "name": "legacy", "kind": "github", "repository": "https://github.com/octo/legacy", "ref": "main",
        }).json()
        assert client.post(f"/api/sources/{legacy['id']}/analyze", json={}).json().get("commit_sha") == "c" * 40
        with connect() as connection:
            stored = connection.execute("SELECT credentials FROM studio_github_connections WHERE owner_id='alice'").fetchone()
        assert b"rotated-token" not in stored["credentials"]
        assert b"refresh-token" not in stored["credentials"]
    finally:
        settings.cache_clear()


def test_github_analysis_keeps_files_when_a_blob_read_reaches_deadline(monkeypatch):
    from types import SimpleNamespace

    from app import repositories

    timestamps = iter([100.0, 100.1, 101.0])
    monkeypatch.setattr(repositories, "time", SimpleNamespace(monotonic=lambda: next(timestamps)))

    def github(request):
        raise httpx.ReadTimeout("deadline reached", request=request)

    with httpx.Client(base_url="https://api.github.com/", transport=httpx.MockTransport(github)) as gh_client:
        def read_blob(oid):
            if oid == "first":
                return b"# Readme"
            return repositories.github_get(gh_client, "git/blobs/second", deadline=101.0, raw=True)

        result = repositories.inspect_tree([
            ("README.md", "100644", "first", 8),
            ("example.py", "100644", "second", 20),
        ], read_blob)

    assert list(result["files"]) == ["README.md"]
    assert result["excluded"] == {"analysis_limit": 1}


def test_github_analysis_continues_past_sixty_seconds(monkeypatch):
    from types import SimpleNamespace

    from app import repositories

    elapsed = 0.0
    monkeypatch.setattr(repositories, "time", SimpleNamespace(monotonic=lambda: elapsed))
    content = b"# Private fixture\n"
    oid = sha1(f"blob {len(content)}\0".encode() + content).hexdigest()

    def github(request):
        nonlocal elapsed
        elapsed += 31
        assert request.extensions["timeout"]["read"] == 10
        if "/git/commits/" in request.url.path:
            return httpx.Response(200, json={"tree": {"sha": "b" * 40}})
        if "/git/trees/" in request.url.path:
            return httpx.Response(200, json={"tree": [
                {"path": "README.md", "size": len(content), "type": "blob", "sha": oid, "mode": "100644"},
            ]})
        assert request.url.path.endswith(f"/git/blobs/{oid}")
        return httpx.Response(200, content=content)

    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: original(
        *args, **kwargs, transport=httpx.MockTransport(github)
    ))
    analysis = repositories.analyze(
        {"kind": "github", "owner_id": "alice", "repository": "https://github.com/octo/private"},
        {"commit_sha": "a" * 40},
    )

    assert elapsed > 60
    assert analysis["files"] == {"README.md": content.decode()}
    assert analysis["excluded"] == {}
