from uuid import uuid4

from app.worker import process
from test_business_planning import setup_business, job
from test_source_planning import repos


def auth(subject):
    return {"Authorization": f"Bearer local:{subject}"}


def test_assigned_businesses_separate_ownership_and_safe_metadata(client, repos):
    admin_plan, source, snapshot, body = setup_business(client, repos)
    endpoint = f"/api/sources/{source}/assignments"
    assert client.get("/api/sources", headers=auth("user1")).json() == []
    assert client.post("/api/projects", json={**body, "id": str(uuid4())}, headers=auth("user1")).status_code == 404
    for user in ["user1", "user2"]:
        assert client.put(f"{endpoint}/{user}").status_code == 200
        assert client.put(f"{endpoint}/{user}").status_code == 200
    assert len(client.get(endpoint).json()) == 2
    assert client.put(f"{endpoint}/bob", headers=auth("user1")).status_code == 404
    assert client.delete(f"{endpoint}/user2", headers=auth("user1")).status_code == 404
    assert client.get(endpoint, headers=auth("user1")).status_code == 404
    summary = client.get("/api/sources", headers=auth("user1")).json()[0]
    assert summary["name"] and summary["publication_id"] and not summary["can_manage"]
    assert not {"repository", "ref", "owner_id", "design_profile", "current_snapshot_id", "error"} & summary.keys()
    assert client.get(f"/api/sources/{source}/snapshots/{snapshot['id']}", headers=auth("user1")).status_code == 404
    assert client.post(f"/api/sources/{source}/analyze", headers=auth("user1")).status_code == 404
    assert client.post(f"/api/sources/{source}/check", headers=auth("user1")).json() == {"scheduled": False}
    plans = {}
    for user in ["user1", "user2"]:
        result = client.post("/api/projects", json={**body, "id": str(uuid4())}, headers=auth(user))
        assert result.status_code == 201, result.text
        plans[user] = result.json()["id"]
    for user in ["user1", "user2"]:
        listed = client.get("/api/projects", headers=auth(user)).json()
        assert [p["id"] for p in listed] == [plans[user]]
        assert client.get(f"/api/projects/{admin_plan}", headers=auth(user)).status_code == 404
        other = plans["user2" if user == "user1" else "user1"]
        assert client.get(f"/api/projects/{other}", headers=auth(user)).status_code == 404
        assert client.patch(f"/api/projects/{other}", json={"title": "forbidden"}, headers=auth(user)).status_code == 404
        assert client.post(f"/api/projects/{other}/jobs", json={"id": str(uuid4()), "base_version": 0, "kind": "discuss", "request": "접근 차단 확인"}, headers=auth(user)).status_code == 404
        assert client.get(f"/api/projects/{plans[user]}").status_code == 404


def test_revocation_preserves_documents_export_and_started_work(client, repos):
    _, source, _, body = setup_business(client, repos)
    endpoint = f"/api/sources/{source}/assignments/user1"
    client.put(endpoint)
    client.headers.update(auth("user1"))
    result = client.post("/api/projects", json={**body, "id": str(uuid4())})
    assert result.status_code == 201, result.text
    pid = result.json()["id"]
    first = client.get(f"/api/projects/{pid}").json()["job"]
    process(first["id"])
    draft = job(client, pid, "generate")
    proposal = draft["proposal"]
    saved = client.post(f"/api/projects/{pid}/proposals/{proposal['id']}/approve", json={"expected_version": 0, "acknowledge_warnings": True})
    assert saved.status_code == 200, saved.text
    next_job = {"id": str(uuid4()), "base_version": 1, "kind": "discuss", "request": "이전에 시작한 업무 대화를 계속해 주세요"}
    assert client.post(f"/api/projects/{pid}/jobs", json=next_job).status_code == 201
    assert client.delete(endpoint, headers=auth("alice")).status_code == 200
    process(next_job["id"])
    bundle = client.get(f"/api/projects/{pid}").json()
    assert bundle["job"]["status"] == "completed"
    assert bundle["source_access"] == {"can_use": False, "can_manage": False}
    assert bundle["project"]["current_version"] == 1
    assert client.get(f"/api/projects/{pid}/revisions/1/export?format=json").status_code == 200
    assert client.get("/api/sources").json() == []
    assert client.post("/api/projects", json={**body, "id": str(uuid4())}).status_code == 404
    for kind in ["discuss", "revise"]:
        assert client.post(f"/api/projects/{pid}/jobs", json={**next_job, "id": str(uuid4()), "kind": kind}).status_code == 404
    assert client.post(f"/api/projects/{pid}/reviews", json={"version": 1}).status_code == 404
    assert client.post(f"/api/projects/{pid}/jobs", json=next_job).status_code == 201
    assert client.put(endpoint, headers=auth("alice")).status_code == 200
    assert client.post(f"/api/projects/{pid}/jobs", json={**next_job, "id": str(uuid4())}).status_code == 201


def test_unpublished_assignment_and_owner_only_management(client, repos):
    from test_source_planning import register
    source = register(client, "alpha")
    endpoint = f"/api/sources/{source}/assignments/user1"
    assert client.put(endpoint).status_code == 409
    assert client.put(endpoint, headers=auth("bob")).status_code == 404
    assert client.delete(endpoint).status_code == 200
    assert client.get(f"/api/sources/{source}/assignments").json() == []
    assert client.get("/api/sources", headers=auth("user1")).json() == []
