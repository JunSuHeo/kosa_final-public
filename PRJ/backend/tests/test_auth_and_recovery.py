from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import copy
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from pydantic import ValidationError
from app.auth import current_user, verify_token
from app.config import Settings
from app.review import review
from app.worker import process
from test_studio import generated, bundle


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_signed_supabase_claims_and_invalid_tokens(monkeypatch, algorithm):
    private = (
        ec.generate_private_key(ec.SECP256R1())
        if algorithm == "ES256"
        else rsa.generate_private_key(public_exponent=65537, key_size=2048)
    )
    config = Settings(
        _env_file=None,
        auth_mode="supabase",
        supabase_url="https://example.supabase.co",
        ai_mode="mock",
        app_env="local",
    )
    monkeypatch.setattr("app.auth.settings", lambda: config)
    monkeypatch.setattr(
        "app.auth.jwks_client",
        lambda url: SimpleNamespace(
            get_signing_key_from_jwt=lambda token: SimpleNamespace(
                key=private.public_key()
            )
        ),
    )
    now = datetime.now(timezone.utc)
    claims = {
        "sub": "user-123",
        "iss": "https://example.supabase.co/auth/v1",
        "aud": "authenticated",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }

    def token(payload):
        return "Bearer " + jwt.encode(payload, private, algorithm=algorithm)

    assert verify_token(token(claims).removeprefix('Bearer '))["sub"] == "user-123"
    for patch in [
        {"exp": now - timedelta(seconds=1)},
        {"aud": "other"},
        {"iss": "https://wrong.example"},
        {"sub": 123},
        {"iat": now + timedelta(hours=1)},
    ]:
        with pytest.raises(HTTPException) as e:
            verify_token(token({**claims, **patch}).removeprefix('Bearer '))
        assert e.value.status_code == 401
    for removed in ["sub", "iat", "exp", "iss", "aud"]:
        payload = {k: v for k, v in claims.items() if k != removed}
        with pytest.raises(HTTPException):
            verify_token(token(payload).removeprefix('Bearer '))


def test_production_mock_is_rejected_without_leaking_secrets():
    with pytest.raises(ValidationError) as e:
        Settings(
            _env_file=None,
            app_env="production",
            auth_mode="mock",
            ai_mode="live",
            llm_api_key="secret-do-not-print",
        )
    assert "secret-do-not-print" not in str(e.value)


def test_commit_then_worker_error_preserves_pending_proposal(client, monkeypatch):
    pid, result = generated(client)

    def after_commit(job_id):
        raise RuntimeError("commit outcome could not be acknowledged")

    monkeypatch.setattr("app.worker._process", after_commit)
    process(result["job"]["id"])
    result = bundle(client, pid)
    assert result["proposal"] is not None
    assert result["job"]["status"] == "waiting_review"


def test_review_rejects_disconnected_nodes_and_requires_deletion_ack(client):
    _, result = generated(client)
    before = result["proposal"]["candidate"]
    candidate = copy.deepcopy(before)
    candidate["flow"]["nodes"].append(
        {
            "id": "node-unreachable",
            "type": "action",
            "title": "고립된 단계",
            "section": "검증",
            "feature_ids": [],
            "x": 0,
            "y": 500,
        }
    )
    issues, _ = review(before, candidate)
    assert any(
        i["severity"] == "blocking" and i["target"] == "node-unreachable"
        for i in issues
    )
    candidate = copy.deepcopy(before)
    candidate["screens"][0]["blocks"].pop()
    issues, _ = review(before, candidate)
    assert any(i["severity"] == "warning" and "삭제" in i["message"] for i in issues)
