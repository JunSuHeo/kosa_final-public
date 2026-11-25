"""GitHub App user authorization shared by source registration and analysis."""

from base64 import urlsafe_b64encode
import hashlib
import json
from time import monotonic
from secrets import token_urlsafe
from typing import Annotated
from urllib.parse import urlencode

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
import httpx
from pydantic import Field

from .auth import current_user
from .config import settings
from .db import connect
from .schema import StrictModel

router = APIRouter(prefix="/api/sources/github")
User = Annotated[str, Depends(current_user)]
RECONNECT = "GitHub 권한이 만료되었거나 해제되었습니다. GitHub를 다시 연결해 주세요."


class GitHubStatus(StrictModel):
    enabled: bool
    connected: bool = False
    login: str | None = None
    install_url: str | None = None


class AuthorizationStart(StrictModel):
    url: str


class AuthorizationResult(StrictModel):
    state: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    code: str = Field(min_length=1, max_length=512)


class GitHubRepository(StrictModel):
    name: str
    branch: str
    private: bool


def github_response(client, method, path, **kwargs):
    try:
        response = client.request(method, path, **kwargs)
        if response.status_code == 401:
            raise HTTPException(409, RECONNECT)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError
        return data, response
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "GitHub 응답을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.") from None


def exchange(**grant):
    config = settings()
    with httpx.Client(timeout=8, trust_env=False) as client:
        data, _ = github_response(
            client, "POST", "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={"client_id": config.github_app_client_id, "client_secret": config.github_app_client_secret, **grant},
        )
    if data.get("error") in {"bad_verification_code", "bad_refresh_token", "expired_token", "invalid_grant"}:
        raise HTTPException(409, RECONNECT)
    if (not isinstance(data.get("access_token"), str) or not data["access_token"]
            or not isinstance(data.get("refresh_token"), str) or not data["refresh_token"]
            or type(data.get("expires_in")) is not int or not 60 < data["expires_in"] <= 86400):
        raise HTTPException(502, "GitHub App의 만료형 사용자 토큰을 발급받지 못했습니다.")
    return data


def github_api(token):
    return httpx.Client(
        base_url="https://api.github.com/", timeout=8, trust_env=False,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2026-03-10"},
    )


def cipher():
    return Fernet(settings().github_token_encryption_key)


def credentials(data):
    return cipher().encrypt(json.dumps({
        "access": data["access_token"], "refresh": data["refresh_token"],
    }).encode())


def read_credentials(row):
    try:
        return json.loads(cipher().decrypt(row["credentials"]))
    except InvalidToken:
        raise HTTPException(409, RECONNECT) from None


def connected_token(owner):
    if not settings().github_app_client_id:
        return None
    query = (
        "SELECT credentials, expires_at > clock_timestamp() + interval '1 minute' AS valid "
        "FROM studio_github_connections WHERE owner_id=%s"
    )
    with connect() as c:
        row = c.execute(query, (owner,)).fetchone()
        if not row or row["valid"]:
            return read_credentials(row)["access"] if row else None
        # GitHub rotates refresh tokens. Only one API/worker may refresh this account at a time.
        row = c.execute(query + " FOR UPDATE", (owner,)).fetchone()
        old = read_credentials(row)
        if row["valid"]:
            return old["access"]
        data = exchange(grant_type="refresh_token", refresh_token=old["refresh"])
        c.execute(
            "UPDATE studio_github_connections SET credentials=%s, "
            "expires_at=clock_timestamp()+%s*interval '1 second' WHERE owner_id=%s",
            (credentials(data), data["expires_in"], owner),
        )
        return data["access_token"]


@router.get("")
def github_status(owner: User) -> GitHubStatus:
    config = settings()
    if not config.github_app_client_id:
        return GitHubStatus(enabled=False)
    with connect() as c:
        row = c.execute("SELECT login FROM studio_github_connections WHERE owner_id=%s", (owner,)).fetchone()
    return GitHubStatus(
        enabled=True, connected=bool(row), login=row["login"] if row else None,
        install_url=f"https://github.com/apps/{config.github_app_slug}/installations/new",
    )


def require_config():
    config = settings()
    if not config.github_app_client_id:
        raise HTTPException(503, "관리자에게 GitHub App 연결 설정을 요청해 주세요.")
    return config


@router.post("/start")
def start_authorization(owner: User) -> AuthorizationStart:
    config = require_config()
    state, verifier = token_urlsafe(32), token_urlsafe(32)
    state_hash = hashlib.sha256(state.encode()).hexdigest()
    challenge = urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    with connect() as c:
        c.execute(
            "INSERT INTO studio_github_authorizations(owner_id,state_hash,verifier,expires_at) "
            "VALUES (%s,%s,%s,clock_timestamp()+interval '10 minutes') ON CONFLICT (owner_id) "
            "DO UPDATE SET state_hash=excluded.state_hash,verifier=excluded.verifier,"
            "expires_at=excluded.expires_at,claimed=false",
            (owner, state_hash, verifier),
        )
    params = urlencode({
        "client_id": config.github_app_client_id, "redirect_uri": config.github_app_callback_url,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "scope": "offline_access",
    })
    return AuthorizationStart(url=f"https://github.com/login/oauth/authorize?{params}")


@router.post("/complete")
def complete_authorization(inp: AuthorizationResult, owner: User) -> GitHubStatus:
    config = require_config()
    state_hash = hashlib.sha256(inp.state.encode()).hexdigest()
    params = (owner, state_hash)
    invalid_state = "GitHub 연결 요청이 만료되었거나 이미 사용되었습니다. 다시 연결해 주세요."
    with connect() as c:
        attempt = c.execute(
            "UPDATE studio_github_authorizations SET claimed=true "
            "WHERE owner_id=%s AND state_hash=%s AND NOT claimed AND expires_at>clock_timestamp() RETURNING verifier",
            params,
        ).fetchone()
    if not attempt:
        raise HTTPException(400, invalid_state)
    data = exchange(code=inp.code, redirect_uri=config.github_app_callback_url, code_verifier=attempt["verifier"])
    with github_api(data["access_token"]) as client:
        identity, _ = github_response(client, "GET", "user")
    login = identity.get("login")
    if not isinstance(login, str) or not login:
        raise HTTPException(502, "GitHub 계정을 확인할 수 없습니다.")
    with connect() as c:
        if not c.execute(
            "DELETE FROM studio_github_authorizations WHERE owner_id=%s AND state_hash=%s RETURNING owner_id",
            params,
        ).fetchone():
            raise HTTPException(400, invalid_state)
        c.execute(
            "INSERT INTO studio_github_connections(owner_id,login,credentials,expires_at) "
            "VALUES (%s,%s,%s,clock_timestamp()+%s*interval '1 second') "
            "ON CONFLICT (owner_id) DO UPDATE SET login=excluded.login,credentials=excluded.credentials,"
            "expires_at=excluded.expires_at",
            (owner, login, credentials(data), data["expires_in"]),
        )
    return github_status(owner)


def pages(client, path, key, deadline):
    for page in range(1, 6):
        remaining = deadline - monotonic()
        if remaining <= 0:
            return
        data, response = github_response(
            client, "GET", path, params={"per_page": 100, "page": page}, timeout=min(8, remaining),
        )
        yield from data[key]
        if "next" not in response.links:
            break


@router.get("/repositories")
def list_repositories(owner: User) -> list[GitHubRepository]:
    require_config()
    token = connected_token(owner)
    if not token:
        raise HTTPException(409, "먼저 GitHub를 연결해 주세요.")
    repositories = {}
    deadline = monotonic() + 15
    with github_api(token) as client:
        installations = pages(client, "user/installations", "installations", deadline)
        for item in installations:
            if len(repositories) >= 500 or monotonic() >= deadline:
                break
            installation_id = int(item["id"])
            path = f"user/installations/{installation_id}/repositories"
            for repo in pages(client, path, "repositories", deadline):
                if len(repositories) >= 500:
                    break
                repositories[repo["full_name"]] = GitHubRepository(
                    name=repo["full_name"], branch=repo.get("default_branch") or "main", private=repo["private"],
                )
    return sorted(repositories.values(), key=lambda repo: repo.name.lower())
