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
        c.execute("TRUNCATE studio_audit RESTART IDENTITY")
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


def test_reset_failure_keeps_account_ready_and_resumes_after_reauthentication(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    login()
    operation = str(uuid4())
    external = accounts.auth_request

    def unavailable(method, path, body=None, **kwargs):
        if method == 'PUT' and path.startswith('/admin/users/'):
            raise HTTPException(503, 'remote unavailable')
        return external(method, path, body, **kwargs)

    monkeypatch.setattr(accounts, 'auth_request', unavailable)
    body = {'operation_id': operation, 'password': 'reset-password!'}
    assert client.post('/api/accounts/demo-user/reset-password', json=body).status_code == 503
    assert client.get('/api/auth/me').status_code == 401
    with connect() as c:
        row = c.execute("SELECT * FROM studio_accounts WHERE id='demo-user'").fetchone()
        assert row['active'] and row['provisioning_status'] == 'ready'
        assert row['session_version'] == 2
        assert not c.execute('SELECT completed FROM studio_account_operations WHERE id=%s', (operation,)).fetchone()['completed']
    login()
    monkeypatch.setattr(accounts, 'auth_request', external)
    response = client.post('/api/accounts/demo-user/reset-password', json=body)
    assert response.status_code == 200, response.text
    assert client.get('/api/auth/me').status_code == 401
    login(password='reset-password!')
    with connect() as c:
        version = c.execute("SELECT session_version FROM studio_accounts WHERE id='demo-user'").fetchone()['session_version']
        assert version == 4
        assert 'reset-password!' not in str(c.execute('SELECT * FROM studio_account_operations').fetchall())
    assert client.post('/api/accounts/demo-user/reset-password', json=body).status_code == 200
    assert client.get('/api/auth/me').status_code == 200
    with connect() as c:
        assert c.execute("SELECT session_version FROM studio_accounts WHERE id='demo-user'").fetchone()['session_version'] == version
        assert c.execute("SELECT count(*) AS n FROM studio_audit WHERE action='비밀번호 재설정'").fetchone()['n'] == 1


def test_reset_revokes_sessions_created_during_remote_call(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    login()
    account = create(client).json()
    external = accounts.auth_request
    concurrent_session = None

    def password_write(method, path, body=None, **kwargs):
        nonlocal concurrent_session
        if method == 'PUT' and path.startswith('/admin/users/'):
            response = client.post('/api/auth/login', json={'identifier': 'worker', 'password': 'new-password!'})
            assert response.status_code == 200, response.text
            concurrent_session = response.json()['access_token']
        return external(method, path, body, **kwargs)

    monkeypatch.setattr(accounts, 'auth_request', password_write)
    response = client.post(f"/api/accounts/{account['id']}/reset-password", json={'operation_id': str(uuid4()), 'password': 'reset-password!'})
    assert response.status_code == 200, response.text
    assert client.get('/api/auth/me', headers={'Authorization': 'Bearer ' + concurrent_session}).status_code == 401


def test_successful_logins_and_external_failures_do_not_consume_credential_quota(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    for _ in range(35):
        login()
    external = accounts.auth_request

    def unavailable(*args, **kwargs):
        raise HTTPException(503, 'unavailable')

    monkeypatch.setattr(accounts, 'auth_request', unavailable)
    for _ in range(35):
        assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'initial-password!'}).status_code == 503
    monkeypatch.setattr(accounts, 'auth_request', external)
    login()


def test_failed_account_quota_is_separate_from_ip_request_quota(auth_server):
    client, login, _, _ = auth_server
    for _ in range(30):
        assert client.post('/api/auth/login', json={'identifier': 'unknown', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'identifier': 'unknown', 'password': 'wrong'}).status_code == 429
    login()


def test_concurrent_credential_failures_stop_at_account_limit(auth_server):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app
    client, _, _, _ = auth_server
    for _ in range(28):
        assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'wrong'}).status_code == 401

    def attempt(_):
        with TestClient(app) as other:
            return other.post('/api/auth/login', json={'identifier': 'admin', 'password': 'wrong'}).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(attempt, range(5)))
    assert sorted(results) == [401, 401, 429, 429, 429]


def test_audit_cursor_is_lossless_string_and_pages_all_history(auth_server):
    from app.accounts import audit
    client, login, _, _ = auth_server
    login()
    with connect() as c:
        c.execute('ALTER TABLE studio_audit ALTER COLUMN id RESTART WITH 9007199254740993')
        for i in range(405):
            audit(c, 'admin', 'test', str(i))
    page = client.get('/api/audit', params={'limit': 200}).json()
    assert isinstance(page['next'], str)
    seen = [row['id'] for row in page['items']]
    while page['next'] is not None:
        page = client.get('/api/audit', params={'before': page['next'], 'limit': 200}).json()
        seen.extend(row['id'] for row in page['items'])
    assert len(seen) == len(set(seen)) == 406
    assert max(map(int, seen)) > 9007199254740992


def test_ip_request_cap_blocks_distributed_identifier_attack(auth_server):
    from app.accounts import attempt_key
    client, _, _, _ = auth_server
    with connect() as c:
        c.execute('INSERT INTO studio_login_attempts(key,attempts) VALUES (%s,600)', (attempt_key('ip:testclient'),))
    assert client.post('/api/auth/login', json={'identifier': 'new-unknown', 'password': 'wrong'}).status_code == 429
    with connect() as c:
        assert c.execute('SELECT attempts FROM studio_login_attempts WHERE key=%s', (attempt_key('ip:testclient'),)).fetchone()['attempts'] == 601


def test_external_rate_limit_does_not_consume_account_failure_quota(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    external = accounts.auth_request

    def limited(*args, **kwargs):
        raise HTTPException(429, 'remote request limit')

    monkeypatch.setattr(accounts, 'auth_request', limited)
    for _ in range(35):
        assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'initial-password!'}).status_code == 429
    monkeypatch.setattr(accounts, 'auth_request', external)
    login()


def test_internal_email_alias_shares_failed_credential_quota(auth_server):
    from app.accounts import internal_email
    client, _, _, _ = auth_server
    with connect() as c:
        uid = c.execute("SELECT auth_user_id FROM studio_accounts WHERE login_id='admin'").fetchone()['auth_user_id']
    for _ in range(30):
        assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'wrong'}).status_code == 401
    assert client.post('/api/auth/login', json={'email': internal_email(uid), 'password': 'initial-password!'}).status_code == 429


def test_expired_account_failure_window_allows_login(auth_server):
    from app.accounts import attempt_key
    client, login, _, _ = auth_server
    with connect() as c:
        c.execute("INSERT INTO studio_login_attempts(key,attempts,started_at) VALUES (%s,30,now()-interval '16 minutes')", (attempt_key('id:demo-user'),))
    login()


def test_completed_new_reset_supersedes_older_incomplete_operation(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    login()
    account = create(client).json()
    external = accounts.auth_request
    old = {'operation_id': str(uuid4()), 'password': 'older-password!'}

    def unavailable(method, path, body=None, **kwargs):
        if method == 'PUT':
            raise HTTPException(503, 'unavailable')
        return external(method, path, body, **kwargs)

    monkeypatch.setattr(accounts, 'auth_request', unavailable)
    path = f"/api/accounts/{account['id']}/reset-password"
    assert client.post(path, json=old).status_code == 503
    monkeypatch.setattr(accounts, 'auth_request', external)
    assert client.post(path, json={'operation_id': str(uuid4()), 'password': 'latest-password!'}).status_code == 200
    superseded = client.post(path, json=old)
    assert superseded.status_code == 409
    assert superseded.json()['detail']['code'] == 'account_operation_superseded'
    login('worker', 'latest-password!')


@pytest.mark.parametrize('session_id', [None, 42, [], 'not-a-uuid'])
def test_invalid_auth_session_claim_returns_401(auth_server, monkeypatch, session_id):
    from app import auth
    client, _, _, _ = auth_server
    decode = auth.verify_token
    monkeypatch.setattr(auth, 'verify_token', lambda token: {**decode(token), 'session_id': session_id})
    assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'initial-password!'}).status_code == 401


def test_reset_commit_then_lost_response_resumes_with_new_password(auth_server, monkeypatch):
    from app import accounts
    client, login, _, _ = auth_server
    login()
    external = accounts.auth_request
    operation = {'operation_id': str(uuid4()), 'password': 'reset-password!'}

    def lost_response(method, path, body=None, **kwargs):
        result = external(method, path, body, **kwargs)
        if method == 'PUT':
            raise HTTPException(503, {'code': 'auth_write_uncertain', 'message': 'unknown outcome'})
        return result

    monkeypatch.setattr(accounts, 'auth_request', lost_response)
    path = '/api/accounts/demo-user/reset-password'
    assert client.post(path, json=operation).status_code == 503
    login(password='reset-password!')
    monkeypatch.setattr(accounts, 'auth_request', external)
    assert client.post(path, json=operation).status_code == 200
    assert client.get('/api/auth/me').status_code == 401
    login(password='reset-password!')


@pytest.mark.parametrize('remote_created', [False, True])
def test_new_create_operation_adopts_matching_pending_account(auth_server, monkeypatch, remote_created):
    from app import accounts
    client, login, users, _ = auth_server
    login()
    external = accounts.auth_request
    original = {'operation_id': str(uuid4()), 'loginId': 'worker', 'name': ' 업무 담당자 ', 'role': 'USER1', 'password': 'first-password!'}

    def unavailable(method, path, body=None, **kwargs):
        if method == 'POST' and path == '/admin/users':
            if remote_created:
                external(method, path, body, **kwargs)
            raise HTTPException(503, 'unavailable')
        return external(method, path, body, **kwargs)

    monkeypatch.setattr(accounts, 'auth_request', unavailable)
    assert client.post('/api/accounts', json=original).status_code == 503
    with connect() as c:
        pending = c.execute("SELECT * FROM studio_accounts WHERE login_id='worker'").fetchone()
    assert pending['provisioning_status'] == 'pending'
    uid = str(pending['auth_user_id'])
    assert (uid in users) is remote_created
    replacement = {**original, 'operation_id': str(uuid4()), 'name': '업무 담당자', 'password': 'replacement-password!'}
    monkeypatch.setattr(accounts, 'auth_request', external)
    adopted = client.post('/api/accounts', json=replacement)
    assert adopted.status_code == 201, adopted.text
    assert adopted.json()['id'] == pending['id']
    with connect() as c:
        ready = c.execute("SELECT * FROM studio_accounts WHERE login_id='worker'").fetchone()
        assert ready['auth_user_id'] == pending['auth_user_id']
        assert ready['provisioning_status'] == 'ready'
        assert c.execute("SELECT count(*) AS n FROM studio_accounts WHERE login_id='worker'").fetchone()['n'] == 1
    assert users[uid] == 'replacement-password!'
    assert len(users) == 2
    superseded = client.post('/api/accounts', json=original)
    assert superseded.status_code == 409
    assert superseded.json()['detail']['code'] == 'account_operation_superseded'
    assert users[uid] == 'replacement-password!'
    assert client.post('/api/accounts', json={**replacement, 'operation_id': str(uuid4())}).status_code == 409
    assert client.post('/api/accounts', json={**replacement, 'password': 'ignored-on-completed-id!'}).status_code == 201
    assert users[uid] == 'replacement-password!'
    login('worker', 'replacement-password!')


@pytest.mark.parametrize('field,value', [('name', '다른 담당자'), ('role', 'USER2')])
def test_new_create_operation_rejects_changed_pending_metadata(auth_server, monkeypatch, field, value):
    from app import accounts
    client, login, users, _ = auth_server
    login()
    external = accounts.auth_request

    def unavailable(method, path, body=None, **kwargs):
        if method == 'POST' and path == '/admin/users':
            raise HTTPException(503, 'unavailable')
        return external(method, path, body, **kwargs)

    monkeypatch.setattr(accounts, 'auth_request', unavailable)
    original = {'operation_id': str(uuid4()), 'loginId': 'worker', 'name': '업무 담당자', 'role': 'USER1', 'password': 'first-password!'}
    assert client.post('/api/accounts', json=original).status_code == 503
    monkeypatch.setattr(accounts, 'auth_request', external)
    assert client.post('/api/accounts', json={**original, 'operation_id': str(uuid4()), field: value}).status_code == 409
    assert len(users) == 1
    with connect() as c:
        pending = c.execute("SELECT * FROM studio_accounts WHERE login_id='worker'").fetchone()
        assert pending['name'] == '업무 담당자'
        assert pending['role'] == 'USER1'
        assert pending['provisioning_status'] == 'pending'
