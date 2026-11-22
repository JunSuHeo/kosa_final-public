import httpx
import jwt
import pytest
from fastapi import HTTPException
from app import accounts, auth
from app.config import settings


@pytest.mark.parametrize('status,expected', [(429, 429), (503, 503), (400, 401)])
def test_auth_request_preserves_rate_limit_and_service_errors(monkeypatch, status, expected):
    monkeypatch.setattr(settings(), 'supabase_anon_key', 'test-key')
    monkeypatch.setattr(settings(), 'supabase_url', 'https://auth.invalid')
    monkeypatch.setattr(accounts.httpx, 'request', lambda *args, **kwargs: httpx.Response(status, json={}))
    with pytest.raises(HTTPException) as error:
        accounts.auth_request('POST', '/token?grant_type=password', {})
    assert error.value.status_code == expected


@pytest.mark.parametrize('failure', ['timeout', 'connection', 'server'])
def test_admin_write_failure_explicitly_reports_uncertain_outcome(monkeypatch, failure):
    monkeypatch.setattr(settings(), 'supabase_service_role_key', 'test-key')
    monkeypatch.setattr(settings(), 'supabase_url', 'https://auth.invalid')

    def remote(*args, **kwargs):
        if failure == 'timeout':
            raise httpx.ReadTimeout('no response')
        if failure == 'connection':
            raise httpx.ConnectError('connection lost')
        return httpx.Response(503, json={})

    monkeypatch.setattr(accounts.httpx, 'request', remote)
    with pytest.raises(HTTPException) as error:
        accounts.auth_request('PUT', '/admin/users/test', {'password': 'test-password!'}, admin=True)
    assert error.value.status_code == 503
    assert error.value.detail['code'] == 'auth_write_uncertain'


@pytest.mark.parametrize('failure,expected', [(jwt.PyJWKClientConnectionError('offline'), 503), (jwt.InvalidTokenError('invalid'), 401)])
def test_jwks_connectivity_is_distinct_from_invalid_token(monkeypatch, failure, expected):
    class Client:
        def get_signing_key_from_jwt(self, token):
            raise failure
    monkeypatch.setattr(auth, 'jwks_client', lambda url: Client())
    with pytest.raises(HTTPException) as error:
        auth.verify_token('token')
    assert error.value.status_code == expected


def test_unreadable_auth_write_response_is_uncertain(monkeypatch):
    monkeypatch.setattr(settings(), 'supabase_service_role_key', 'test-key')
    monkeypatch.setattr(settings(), 'supabase_url', 'https://auth.invalid')
    monkeypatch.setattr(accounts.httpx, 'request', lambda *args, **kwargs: httpx.Response(200, text='truncated json'))
    with pytest.raises(HTTPException) as error:
        accounts.auth_request('PUT', '/admin/users/test', {'password': 'test-password!'}, admin=True)
    assert error.value.status_code == 503
    assert error.value.detail['code'] == 'auth_write_uncertain'
