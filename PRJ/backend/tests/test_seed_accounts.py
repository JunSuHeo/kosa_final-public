from uuid import uuid4
import pytest
from test_accounts import auth_server
from app.config import settings
from app.db import connect
from app.manage import seed_test_accounts


def test_seed_empty_database_and_preserve_existing_state(auth_server):
    client, login, _, _ = auth_server
    with connect() as c:
        c.execute('TRUNCATE studio_accounts CASCADE')
    first = seed_test_accounts('seed-password!')
    assert [(a['loginId'], a['role']) for a in first] == [
        ('admin', 'ADMINISTRATOR'), ('user1', 'USER1'), ('user2', 'USER2')]
    login('admin', 'seed-password!')
    assert client.post('/api/projects', json={'id': str(uuid4()), 'idea': 'seed 이후에도 유지할 기획'}).status_code == 201
    assert client.put('/api/roles/USER1/plans.create', json={'enabled': False}).status_code == 200
    with connect() as c:
        c.execute("UPDATE studio_accounts SET name='기존 사용자' WHERE login_id='user1'")
    second = seed_test_accounts('different-password!')
    assert [a['id'] for a in second] == [a['id'] for a in first]
    assert second[1]['name'] == '기존 사용자'
    assert len(client.get('/api/projects').json()) == 1
    login('user1', 'seed-password!')
    assert client.post('/api/projects', json={'id': str(uuid4()), 'idea': '권한 없는 기획'}).status_code == 403
    assert client.post('/api/auth/login', json={'identifier': 'user1', 'password': 'different-password!'}).status_code == 401


def test_explicit_password_reset_revokes_sessions(auth_server):
    client, login, _, _ = auth_server
    first = seed_test_accounts('seed-password!')
    login('user1', 'seed-password!')
    second = seed_test_accounts('changed-password!', reset_passwords=True)
    assert [a['id'] for a in first] == [a['id'] for a in second]
    assert client.get('/api/projects').status_code == 401
    for identifier in ['admin', 'user1', 'user2']:
        login(identifier, 'changed-password!')
    assert client.post('/api/auth/login', json={'identifier': 'admin', 'password': 'initial-password!'}).status_code == 401


def test_seed_refuses_conflicts_and_nonlocal_mode(auth_server, monkeypatch):
    _, _, users, _ = auth_server
    seed_test_accounts('seed-password!')
    with connect() as c:
        c.execute("UPDATE studio_accounts SET role='USER2' WHERE login_id='user1'")
    before = dict(users)
    with pytest.raises(ValueError, match='역할 또는 활성 상태'):
        seed_test_accounts('changed-password!', reset_passwords=True)
    assert users == before
    monkeypatch.setattr(settings(), 'app_env', 'production')
    with pytest.raises(ValueError, match='APP_ENV=local'):
        seed_test_accounts('seed-password!')
