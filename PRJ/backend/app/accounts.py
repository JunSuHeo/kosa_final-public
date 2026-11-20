"""Server-owned accounts and policies. Supabase owns password verification only."""
from typing import Annotated, Literal
from uuid import UUID, uuid4
import hashlib
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb
from .config import settings
from .db import connect

ROLES = ('USER1', 'USER2', 'ADMINISTRATOR')
PERMISSIONS = ('plans.read', 'plans.create', 'plans.edit', 'plans.confirm', 'plans.export',
               'sources.manage', 'sources.assign', 'accounts.manage', 'roles.manage', 'audit.read')
FIXED = ('accounts.manage', 'roles.manage', 'audit.read')
Role = Literal['USER1', 'USER2', 'ADMINISTRATOR']


def seed_policy(c):
    for role in ROLES:
        for permission in PERMISSIONS:
            c.execute('INSERT INTO studio_role_permissions(role,permission,enabled) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                      (role, permission, role == 'ADMINISTRATOR' or permission.startswith('plans.')))


def internal_email(auth_id):
    return f'{auth_id}@accounts.hplanit.invalid'


def auth_request(method, path, body=None, *, admin=False, token=None):
    s = settings()
    key = s.supabase_service_role_key if admin else s.supabase_anon_key
    if not key:
        raise HTTPException(503, '인증 서버 설정을 확인해 주세요.')
    headers = {'apikey': key}
    if token or admin:
        headers['Authorization'] = 'Bearer ' + (token or key)
    try:
        response = httpx.request(method, s.supabase_url.rstrip('/') + '/auth/v1' + path,
                                 headers=headers, json=body, timeout=20)
    except httpx.HTTPError:
        raise HTTPException(503, '인증 서버에 연결할 수 없습니다.') from None
    if response.status_code >= 400:
        if response.status_code >= 500:
            raise HTTPException(503, '인증 서버에 연결할 수 없습니다.')
        if admin and response.status_code == 404:
            raise HTTPException(404, '인증 계정을 찾을 수 없습니다.')
        if admin:
            raise HTTPException(409, '인증 계정 처리를 완료하지 못했습니다. ID와 비밀번호 정책을 확인하고 다시 시도해 주세요.')
        raise HTTPException(401, 'ID 또는 비밀번호를 확인해 주세요')
    return response.json() if response.content else {}


def public_account(row):
    return {'id': row['id'], 'loginId': row['login_id'], 'name': row['name'], 'role': row['role'],
            'active': row['active'] and row['provisioning_status'] == 'ready',
            'sessionVersion': row['session_version'], 'createdAt': row['created_at'], 'lastLoginAt': row['last_login_at']}


def read_policy(c):
    policy = {role: {p: False for p in PERMISSIONS} for role in ROLES}
    for row in c.execute('SELECT * FROM studio_role_permissions').fetchall():
        if row['permission'] in PERMISSIONS:
            policy[row['role']][row['permission']] = row['enabled']
    for role in ROLES:
        for permission in FIXED:
            policy[role][permission] = role == 'ADMINISTRATOR'
    return policy


def identity(c, account):
    return {'account': public_account(account), 'policy': read_policy(c)}


def audit(c, actor, action, target, detail=''):
    c.execute('INSERT INTO studio_audit(actor,action,target,detail) VALUES (%s,%s,%s,%s)',
              (actor, action, target, detail))


def require(c, account_id, permission):
    row = c.execute('SELECT * FROM studio_accounts WHERE id=%s', (account_id,)).fetchone()
    if not row or not row['active'] or row['provisioning_status'] != 'ready':
        raise HTTPException(401, '다시 로그인해 주세요.')
    if not read_policy(c)[row['role']].get(permission, False):
        raise HTTPException(403, '이 기능을 사용할 권한이 없습니다. 관리자에게 문의해 주세요.')
    return row


def request_permission(path, method):
    if path.startswith('/api/projects'):
        if path.endswith('/export'):
            return 'plans.export'
        if method == 'GET':
            return 'plans.read'
        if path == '/api/projects' and method == 'POST':
            return 'plans.create'
        if path.endswith('/approve'):
            return 'plans.confirm'
        if path.endswith('/cancel'):
            return None
        return 'plans.edit'
    if path.startswith('/api/sources'):
        if '/assignments' in path:
            return 'sources.assign'
        if path == '/api/sources' and method == 'GET':
            return None
        return 'sources.manage'
    return None


def session_account(c, claims):
    try:
        sid, subject = UUID(claims['session_id']), UUID(claims['sub'])
    except (ValueError, KeyError, TypeError):
        raise HTTPException(401, '다시 로그인해 주세요.') from None
    row = c.execute('SELECT a.* FROM studio_accounts a JOIN studio_auth_sessions s ON s.account_id=a.id '
                    'WHERE s.id=%s AND a.auth_user_id=%s AND NOT s.revoked AND a.active '
                    "AND a.provisioning_status='ready' AND s.session_version=a.session_version", (sid, subject)).fetchone()
    if not row:
        raise HTTPException(401, '계정 설정이 변경되었거나 로그인이 만료되었습니다. 다시 로그인해 주세요.')
    return row


def revoke(c, account_id):
    c.execute('UPDATE studio_accounts SET session_version=session_version+1 WHERE id=%s', (account_id,))
    c.execute('UPDATE studio_auth_sessions SET revoked=true WHERE account_id=%s', (account_id,))


def rate_limit(identifier, address):
    # A DB-backed window works across API processes and never stores raw addresses/IDs.
    with connect() as c:
        c.execute("DELETE FROM studio_login_attempts WHERE started_at < now()-interval '15 minutes'")
        for text in ('id:' + identifier, 'ip:' + address):
            key = hashlib.sha256(text.encode()).hexdigest()
            row = c.execute('INSERT INTO studio_login_attempts(key,attempts) VALUES (%s,1) '
                            'ON CONFLICT(key) DO UPDATE SET attempts=studio_login_attempts.attempts+1 RETURNING attempts', (key,)).fetchone()
            if row['attempts'] > 30:
                raise HTTPException(429, '로그인 시도가 많습니다. 잠시 후 다시 시도해 주세요.')


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Input):
    identifier: str | None = Field(default=None, max_length=320)
    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class Refresh(Input):
    refresh_token: str = Field(min_length=1, max_length=4096)


class AccountInput(Input):
    operation_id: UUID
    loginId: str = Field(pattern=r'^[a-zA-Z0-9._-]{3,40}$')
    name: str = Field(min_length=1, max_length=80)
    role: Role
    password: str = Field(min_length=10, max_length=128)


class AccountUpdate(Input):
    name: str = Field(min_length=1, max_length=80)
    role: Role
    active: bool


class Reset(Input):
    operation_id: UUID
    password: str = Field(min_length=10, max_length=128)


class PermissionUpdate(Input):
    enabled: bool


router = APIRouter()


def server_mode():
    if settings().auth_mode != 'supabase':
        raise HTTPException(404, '실제 계정 관리 환경이 아닙니다.')


def user(authorization: str = Header(default='')):
    from .auth import current_user
    server_mode()
    return current_user(authorization)


User = Annotated[str, Depends(user)]


@router.post('/api/auth/login')
def login(inp: Login, request: Request):
    from .auth import verify_token
    server_mode()
    identifier = (inp.identifier or inp.email or '').strip()
    rate_limit(identifier, request.client.host if request.client else '')
    with connect() as c:
        account = c.execute(
            "SELECT * FROM studio_accounts WHERE (login_id=%s OR (auth_user_id::text || '@accounts.hplanit.invalid')=%s) AND active AND provisioning_status='ready'", (identifier, identifier)).fetchone()
    if not account:
        raise HTTPException(401, 'ID 또는 비밀번호를 확인해 주세요')
    result = auth_request('POST', '/token?grant_type=password', {'email': internal_email(account['auth_user_id']), 'password': inp.password})
    claims = verify_token(result['access_token'])
    if claims.get('sub') != str(account['auth_user_id']):
        raise HTTPException(401, 'ID 또는 비밀번호를 확인해 주세요')
    with connect() as c:
        current = c.execute('SELECT * FROM studio_accounts WHERE id=%s FOR UPDATE', (account['id'],)).fetchone()
        if not current['active'] or current['provisioning_status'] != 'ready' or current['session_version'] != account['session_version']:
            raise HTTPException(401, '계정 설정이 변경되었습니다. 다시 로그인해 주세요.')
        c.execute('INSERT INTO studio_auth_sessions(id,account_id,session_version) VALUES (%s,%s,%s)',
                  (UUID(claims['session_id']), current['id'], current['session_version']))
        current = c.execute('UPDATE studio_accounts SET last_login_at=now() WHERE id=%s RETURNING *', (current['id'],)).fetchone()
        audit(c, current['login_id'], '로그인', current['login_id'])
        result['identity'] = identity(c, current)
    return {k: result[k] for k in ('access_token', 'refresh_token', 'expires_in', 'identity')}


@router.post('/api/auth/refresh')
def refresh(inp: Refresh):
    from .auth import verify_token
    server_mode()
    result = auth_request('POST', '/token?grant_type=refresh_token', inp.model_dump())
    with connect() as c:
        account = session_account(c, verify_token(result['access_token']))
        result['identity'] = identity(c, account)
    return {k: result[k] for k in ('access_token', 'refresh_token', 'expires_in', 'identity')}


@router.get('/api/auth/me')
def me(owner: User):
    with connect() as c:
        return identity(c, c.execute('SELECT * FROM studio_accounts WHERE id=%s', (owner,)).fetchone())


@router.post('/api/auth/logout')
def logout(owner: User, request: Request):
    from .auth import verify_token
    token = request.headers['authorization'].removeprefix('Bearer ')
    claims = verify_token(token)
    with connect() as c:
        c.execute('UPDATE studio_auth_sessions SET revoked=true WHERE id=%s AND account_id=%s', (UUID(claims['session_id']), owner))
        audit(c, owner, '로그아웃', owner)
    # Local revocation is authoritative even when the remote service is unavailable.
    try:
        auth_request('POST', '/logout?scope=local', token=token)
    except HTTPException:
        pass
    return {'ok': True}


@router.get('/api/accounts')
def list_accounts(owner: User):
    with connect() as c:
        require(c, owner, 'accounts.manage')
        return [public_account(row) for row in c.execute('SELECT * FROM studio_accounts ORDER BY created_at,id').fetchall()]


@router.get('/api/accounts/assignment-options')
def assignment_options(owner: User):
    with connect() as c:
        require(c, owner, 'sources.assign')
        return [{k: public_account(row)[k] for k in ('id', 'loginId', 'name', 'active')} for row in c.execute(
            "SELECT * FROM studio_accounts WHERE active AND provisioning_status='ready' ORDER BY login_id").fetchall()]


def provision(inp, actor, *, account_id=None, bootstrap=False):
    from psycopg.errors import UniqueViolation
    action = 'reset' if account_id else 'create'
    payload = {'loginId': inp.loginId, 'name': inp.name.strip(), 'role': inp.role} if action == 'create' else {'id': account_id}
    if action == 'create' and not payload['name']:
        raise HTTPException(422, '이름을 입력해 주세요.')
    # Serialize operations on the same account, including remote calls. Other accounts can proceed.
    lock_key = 'account:' + (account_id or inp.loginId)
    with connect() as lock:
        if not lock.execute('SELECT pg_try_advisory_lock(hashtextextended(%s,0)) AS ok', (lock_key,)).fetchone()['ok']:
            raise HTTPException(409, '계정 변경 작업이 진행 중입니다. 잠시 후 다시 시도해 주세요.')
        try:
            with connect() as c:
                if not bootstrap:
                    require(c, actor, 'accounts.manage')
                op = c.execute('SELECT * FROM studio_account_operations WHERE id=%s', (inp.operation_id,)).fetchone()
                if op:
                    if (op['actor_id'], op['action'], op['input']) != (actor, action, payload):
                        raise HTTPException(409, '같은 작업 ID가 다른 요청에 사용되었습니다.')
                    account = c.execute('SELECT * FROM studio_accounts WHERE id=%s', (op['account_id'],)).fetchone()
                    if op['completed']:
                        return public_account(account)
                else:
                    if action == 'create':
                        if bootstrap and c.execute('SELECT 1 FROM studio_accounts LIMIT 1').fetchone():
                            raise HTTPException(409, '초기 관리자가 이미 구성되어 있습니다.')
                        if c.execute('SELECT 1 FROM studio_accounts WHERE login_id=%s', (inp.loginId,)).fetchone():
                            raise HTTPException(409, '이미 사용 중인 ID입니다.')
                        uid = uuid4()
                        account = c.execute('INSERT INTO studio_accounts(id,auth_user_id,login_id,name,role) VALUES (%s,%s,%s,%s,%s) RETURNING *',
                                            ('demo-user' if bootstrap else str(uuid4()), uid, inp.loginId, payload['name'], inp.role)).fetchone()
                    else:
                        account = c.execute('SELECT * FROM studio_accounts WHERE id=%s FOR UPDATE', (account_id,)).fetchone()
                        if not account:
                            raise HTTPException(404, '계정을 찾을 수 없습니다.')
                        if account['provisioning_status'] != 'ready':
                            raise HTTPException(409, '이전 계정 작업을 먼저 재시도해 주세요.')
                        revoke(c, account_id)
                        c.execute("UPDATE studio_accounts SET provisioning_status='pending' WHERE id=%s", (account_id,))
                    c.execute('INSERT INTO studio_account_operations(id,actor_id,account_id,action,input) VALUES (%s,%s,%s,%s,%s)',
                              (inp.operation_id, actor, account['id'], action, Jsonb(payload)))
            uid = str(account['auth_user_id'])
            if action == 'create':
                try:
                    existing = auth_request('GET', f'/admin/users/{uid}', admin=True)
                except HTTPException as e:
                    if e.status_code != 404:
                        raise
                    existing = None
                if existing:
                    if existing.get('id') != uid or existing.get('email') != internal_email(uid):
                        raise HTTPException(409, '인증 계정 연결을 확인해 주세요.')
                    auth_request('PUT', f'/admin/users/{uid}', {'password': inp.password}, admin=True)
                else:
                    auth_request('POST', '/admin/users', {'id': uid, 'email': internal_email(uid), 'password': inp.password, 'email_confirm': True}, admin=True)
            else:
                auth_request('PUT', f'/admin/users/{uid}', {'password': inp.password}, admin=True)
            with connect() as c:
                account = c.execute("UPDATE studio_accounts SET provisioning_status='ready',active=CASE WHEN %s='create' THEN true ELSE active END WHERE id=%s RETURNING *", (action, account['id'])).fetchone()
                c.execute('UPDATE studio_account_operations SET completed=true WHERE id=%s', (inp.operation_id,))
                audit(c, actor, '계정 등록' if action == 'create' else '비밀번호 재설정', account['login_id'], '기존 세션 종료' if action == 'reset' else account['role'])
                return public_account(account)
        except UniqueViolation:
            raise HTTPException(409, '이미 사용 중인 ID 또는 작업 ID입니다.') from None
        finally:
            lock.execute('SELECT pg_advisory_unlock(hashtextextended(%s,0))', (lock_key,))


@router.post('/api/accounts', status_code=201)
def create_account(inp: AccountInput, owner: User):
    return provision(inp, owner)


@router.post('/api/accounts/{account_id}/reset-password')
def reset_password(account_id: str, inp: Reset, owner: User):
    return provision(inp, owner, account_id=account_id)


@router.patch('/api/accounts/{account_id}')
def update_account(account_id: str, inp: AccountUpdate, owner: User):
    name = inp.name.strip()
    if not name:
        raise HTTPException(422, '이름을 입력해 주세요.')
    with connect() as c:
        # Global lock prevents two concurrent requests from each removing the other last administrator.
        c.execute('SELECT pg_advisory_xact_lock(247316)')
        actor = require(c, owner, 'accounts.manage')
        account = c.execute('SELECT * FROM studio_accounts WHERE id=%s FOR UPDATE', (account_id,)).fetchone()
        if not account:
            raise HTTPException(404, '계정을 찾을 수 없습니다.')
        if account['provisioning_status'] != 'ready':
            raise HTTPException(409, '계정 등록·재설정 작업을 먼저 완료해 주세요.')
        if account['role'] == 'ADMINISTRATOR' and account['active'] and (inp.role != 'ADMINISTRATOR' or not inp.active):
            count = c.execute("SELECT count(*) AS n FROM studio_accounts WHERE role='ADMINISTRATOR' AND active AND provisioning_status='ready'").fetchone()['n']
            if count <= 1:
                raise HTTPException(409, '마지막 활성 ADMINISTRATOR는 사용 중지하거나 역할을 변경할 수 없습니다.')
        for field, new, label in (('name', name, '정보 변경'), ('role', inp.role, '역할 변경'), ('active', inp.active, '사용 상태 변경')):
            if account[field] != new:
                audit(c, actor['login_id'], label, account['login_id'], f'{account[field]} → {new}')
        if account['role'] != inp.role or account['active'] != inp.active:
            revoke(c, account_id)
        row = c.execute('UPDATE studio_accounts SET name=%s,role=%s,active=%s WHERE id=%s RETURNING *', (name, inp.role, inp.active, account_id)).fetchone()
        return public_account(row)


@router.get('/api/roles')
def roles(owner: User):
    with connect() as c:
        require(c, owner, 'roles.manage')
        return read_policy(c)


@router.put('/api/roles/{role}/{permission}')
def update_permission(role: Role, permission: str, inp: PermissionUpdate, owner: User):
    with connect() as c:
        actor = require(c, owner, 'roles.manage')
        if role == 'ADMINISTRATOR' or permission in FIXED or permission not in PERMISSIONS:
            raise HTTPException(403, '관리자 전용 권한은 고정되어 있습니다.')
        c.execute('INSERT INTO studio_role_permissions(role,permission,enabled) VALUES (%s,%s,%s) ON CONFLICT(role,permission) DO UPDATE SET enabled=excluded.enabled', (role, permission, inp.enabled))
        audit(c, actor['login_id'], '권한 변경', role, f'{permission}: {inp.enabled}')
        return read_policy(c)


@router.get('/api/audit')
def history(owner: User, before: int | None = None, limit: int = 100):
    limit = max(1, min(limit, 200))
    with connect() as c:
        require(c, owner, 'audit.read')
        rows = c.execute('SELECT * FROM studio_audit WHERE (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s', (before, before, limit + 1)).fetchall()
        return {'items': [{**row, 'id': str(row['id'])} for row in rows[:limit]], 'next': rows[limit-1]['id'] if len(rows) > limit else None}
