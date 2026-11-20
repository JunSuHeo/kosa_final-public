from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from app.config import settings
from app.db import connect
from test_source_planning import repos


@pytest.fixture
def auth_server(client, monkeypatch):
    """Real SQL/session/permissions, with only the external Auth boundary replaced."""
    from app import accounts, auth
    config = settings()
    monkeypatch.setattr(config, "auth_mode", "supabase")
    users = {}
    tokens = {}
    admin_auth = str(uuid4())
    with connect() as c:
        c.execute("TRUNCATE studio_accounts CASCADE")
        c.execute("DELETE FROM studio_role_permissions")
        c.execute("DELETE FROM studio_login_attempts")
        accounts.seed_policy(c)
        c.execute("INSERT INTO studio_accounts(id,auth_user_id,login_id,name,role,active,provisioning_status) VALUES ('demo-user',%s,'admin','관리자','ADMINISTRATOR',true,'ready')", (admin_auth,))
    users[admin_auth] = "initial-password!"

    def external(method, path, body=None, *, admin=False, token=None):
        if path == "/admin/users" and method == "POST":
            uid = body["id"]
            users[uid] = body["password"]
            return {"id": uid}
        if path.startswith("/admin/users/"):
            uid = path.split("/")[-1]
            if method == "GET":
                if uid not in users:
                    raise HTTPException(404, "not found")
                return {"id": uid, "email": accounts.internal_email(uid)}
            users[uid] = body["password"]
            return {"id": uid}
        if path.startswith("/logout"):
            return {}
        if "grant_type=password" in path:
            uid = body["email"].split("@")[0]
            if users.get(uid) != body["password"]:
                raise HTTPException(401, "ID 또는 비밀번호를 확인해 주세요")
            sid = str(uuid4())
        elif "grant_type=refresh_token" in path:
            old = tokens.get(body["refresh_token"])
            if not old:
                raise HTTPException(401, "expired")
            uid, sid = old["sub"], old["session_id"]
        else:
            raise AssertionError(path)
        access, refresh = str(uuid4()), str(uuid4())
        tokens[access] = tokens[refresh] = {"sub": uid, "session_id": sid, "exp": (datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()}
        return {"access_token": access, "refresh_token": refresh, "expires_in": 3600}

    def decode(token):
        if token not in tokens:
            raise HTTPException(401, "invalid")
        return tokens[token]

    monkeypatch.setattr(accounts, "auth_request", external)
    monkeypatch.setattr(auth, "verify_token", decode)
    client.headers.pop("Authorization", None)

    def login(identifier="admin", password="initial-password!"):
        response = client.post("/api/auth/login", json={"identifier": identifier, "password": password})
        assert response.status_code == 200, response.text
        data = response.json()
        client.headers["Authorization"] = "Bearer " + data["access_token"]
        return data

    return client, login, users, tokens


def create(client, login_id="worker", role="USER1", operation_id=None):
    return client.post("/api/accounts", json={"operation_id": operation_id or str(uuid4()), "loginId": login_id, "name": "업무 담당자", "role": role, "password": "new-password!"})


def test_id_login_refresh_logout_and_unregistered_session(auth_server):
    client, login, _, tokens = auth_server
    data = login(" admin ")
    assert data["identity"]["account"]["id"] == "demo-user"
    assert client.get("/api/auth/me").json()["account"]["role"] == "ADMINISTRATOR"
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
    assert refreshed.status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/projects").status_code == 401
    assert client.post("/api/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}).status_code == 401
    fake = str(uuid4())
    tokens[fake] = {**tokens[data["access_token"]], "session_id": str(uuid4())}
    client.headers["Authorization"] = "Bearer " + fake
    assert client.get("/api/projects").status_code == 401


def test_server_accounts_permissions_revoke_sessions_and_audit(auth_server):
    client, login, _, _ = auth_server
    login()
    response = create(client)
    assert response.status_code == 201, response.text
    account = response.json()
    assert "password" not in account
    login("worker", "new-password!")
    assert client.get("/api/accounts").status_code == 403
    assert client.get("/api/roles").status_code == 403
    assert client.post("/api/sources", json={"name": "업무", "description": "설명", "kind": "local", "repository": "x", "ref": "HEAD"}).status_code == 403
    worker_token = client.headers["Authorization"]
    login()
    assert client.patch(f"/api/accounts/{account['id']}", json={"name": "담당자", "role": "USER2", "active": True}).status_code == 200
    client.headers["Authorization"] = worker_token
    assert client.get("/api/projects").status_code == 401
    login("worker", "new-password!")
    login()
    assert client.put("/api/roles/USER2/plans.create", json={"enabled": False}).status_code == 200
    login("worker", "new-password!")
    assert client.post("/api/projects", json={"idea": "새 업무"}).status_code == 403
    assert client.get("/api/projects").status_code == 200
    login()
    assert client.post(f"/api/accounts/{account['id']}/reset-password", json={"operation_id": str(uuid4()), "password": "reset-password!"}).status_code == 200
    assert client.post("/api/auth/login", json={"identifier": "worker", "password": "new-password!"}).status_code == 401
    login("worker", "reset-password!")
    worker_token = client.headers["Authorization"]
    login()
    assert client.patch(f"/api/accounts/{account['id']}", json={"name": "담당자", "role": "USER2", "active": False}).status_code == 200
    client.headers["Authorization"] = worker_token
    assert client.get("/api/projects").status_code == 401
    login()
    history = client.get("/api/audit").json()
    assert any(row["action"] == "비밀번호 재설정" for row in history["items"])
    assert "reset-password!" not in str(history)


def test_last_admin_and_idempotent_registration(auth_server):
    client, login, users, _ = auth_server
    login()
    assert client.patch("/api/accounts/demo-user", json={"name": "관리자", "role": "USER1", "active": True}).status_code == 409
    assert client.patch("/api/accounts/demo-user", json={"name": "관리자", "role": "ADMINISTRATOR", "active": False}).status_code == 409
    assert client.put("/api/roles/USER1/accounts.manage", json={"enabled": True}).status_code == 403
    operation = str(uuid4())
    one = create(client, operation_id=operation)
    two = create(client, operation_id=operation)
    assert one.status_code == two.status_code == 201
    assert one.json()["id"] == two.json()["id"]
    assert len(users) == 2
    assert create(client).status_code == 409
    assert create(client, login_id="different", operation_id=operation).status_code == 409


def test_failed_provisioning_is_retryable_and_cannot_login(auth_server, monkeypatch):
    from app import accounts
    client, login, users, _ = auth_server
    login()
    external = accounts.auth_request
    operation = str(uuid4())

    def interrupted(method, path, body=None, *, admin=False):
        result = external(method, path, body, admin=admin)
        if path == "/admin/users":
            raise HTTPException(503, "인증 서버에 연결할 수 없습니다.")
        return result

    monkeypatch.setattr(accounts, "auth_request", interrupted)
    assert create(client, operation_id=operation).status_code == 503
    assert client.post("/api/auth/login", json={"identifier": "worker", "password": "new-password!"}).status_code == 401
    monkeypatch.setattr(accounts, "auth_request", external)
    assert create(client, operation_id=operation).status_code == 201
    assert len(users) == 2
    login("worker", "new-password!")


def test_assignment_scope_and_other_owners_are_enforced_on_server(auth_server, repos):
    from test_business_planning import setup_business
    client, login, _, _ = auth_server
    login()
    pid, source, snapshot, body = setup_business(client, repos)
    account = create(client).json()
    login('worker', 'new-password!')
    assert client.get(f'/api/projects/{pid}').status_code == 404
    assert client.get('/api/sources').json() == []
    assert client.post('/api/projects', json={**body, 'id': str(uuid4())}).status_code == 404
    login()
    assert client.put(f"/api/sources/{source}/assignments/{account['id']}").status_code == 200
    assert client.put(f'/api/sources/{source}/assignments/not-an-account').status_code == 404
    login('worker', 'new-password!')
    assert len(client.get('/api/sources').json()) == 1
    result = client.post('/api/projects', json={**body, 'id': str(uuid4())})
    assert result.status_code == 201, result.text
    own = result.json()['id']
    assert client.get(f'/api/projects/{own}').status_code == 200
    login()
    assert client.get(f'/api/projects/{own}').status_code == 404
    assert client.delete(f"/api/sources/{source}/assignments/{account['id']}").status_code == 200
    history = client.get('/api/audit').json()['items']
    assert any(x['action'] == '업무 배정 해제' for x in history)
    login('worker', 'new-password!')
    assert client.get(f'/api/projects/{own}').status_code == 200
    assert client.post('/api/projects', json={**body, 'id': str(uuid4())}).status_code == 404


def test_concurrent_last_administrator_changes_keep_one_active(auth_server):
    from concurrent.futures import ThreadPoolExecutor
    from app.accounts import update_account, AccountUpdate
    client, login, _, _ = auth_server
    login()
    other = create(client, login_id='second-admin', role='ADMINISTRATOR').json()

    def disable(target):
        try:
            update_account(target, AccountUpdate(name='관리자', role='USER1', active=True), 'demo-user')
            return 200
        except HTTPException as error:
            return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(disable, ['demo-user', other['id']]))
    assert 200 in results
    with connect() as c:
        assert c.execute("SELECT count(*) AS n FROM studio_accounts WHERE active AND role='ADMINISTRATOR'").fetchone()['n'] == 1


def test_login_rate_limit_and_disabled_response_do_not_reveal_accounts(auth_server):
    client, _, _, _ = auth_server
    errors = []
    for identifier in ['does-not-exist', 'admin']:
        errors.append(client.post('/api/auth/login', json={'identifier': identifier, 'password': 'wrong'}).json()['detail'])
    assert errors[0] == errors[1]
    with connect() as c:
        c.execute('UPDATE studio_login_attempts SET attempts=31')
    assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'initial-password!'}).status_code == 429
