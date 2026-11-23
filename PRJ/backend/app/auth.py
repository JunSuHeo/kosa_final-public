from functools import lru_cache
import jwt
from fastapi import Header, HTTPException, Request
from .config import settings


@lru_cache
def jwks_client(url):
    return jwt.PyJWKClient(url, cache_keys=True)


def current_user(authorization: str = Header(default=""), request: Request = None) -> str:
    s = settings()
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "로그인이 필요합니다.")
    token = authorization.removeprefix("Bearer ")
    if s.auth_mode == "mock":
        if token.startswith("local:") and 1 <= len(token[6:]) <= 100:
            return token[6:]
        raise HTTPException(401, "로컬 인증 정보가 올바르지 않습니다.")
    claims = verify_token(token)
    from .accounts import request_permission, require, session_account
    from .db import connect
    with connect() as c:
        account = session_account(c, claims)
        permission = request_permission(request.url.path.rstrip('/'), request.method) if request else None
        if permission:
            require(c, account['id'], permission)
        return account['id']


def verify_token(token):
    s = settings()
    try:
        issuer = s.supabase_url.rstrip("/") + "/auth/v1"
        key = jwks_client(issuer + "/.well-known/jwks.json").get_signing_key_from_jwt(
            token
        )
        payload = jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256"],
            audience=s.supabase_jwt_audience,
            issuer=issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
        if not isinstance(payload["sub"], str) or not payload["sub"]:
            raise ValueError("missing subject")
        return payload
    except (jwt.PyJWKClientConnectionError, OSError):
        raise HTTPException(503, "인증 서버에 연결할 수 없습니다.") from None
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "로그인이 만료되었거나 유효하지 않습니다.") from None
