"""Ephemeral Auth boundary for isolated E2E only; never mount into the app API."""
from contextlib import asynccontextmanager
import secrets
import time
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, Header, HTTPException
import jwt
from psycopg import sql

from app.accounts import internal_email
from app.config import settings
from app.db import connect, initialize
from app.manage import seed_test_accounts


def isolated_database():
    from urllib.parse import urlsplit
    config = settings()
    target = urlsplit(config.database_url)
    if (target.path != '/studio_e2e' or target.hostname != 'db'
            or config.app_env != 'local' or config.supabase_service_role_key != 'e2e-service-role'):
        raise RuntimeError('Requires the isolated E2E database and fixture keys')


@asynccontextmanager
async def lifespan(app):
    isolated_database()
    initialize()
    yield


app = FastAPI(lifespan=lifespan)
key = ec.generate_private_key(ec.SECP256R1())
users = {}
sessions = {}
refreshes = {}
issuer = settings().supabase_url.rstrip('/') + '/auth/v1'


def admin_key(authorization):
    if authorization != 'Bearer ' + settings().supabase_service_role_key:
        raise HTTPException(401)


def tokens(uid, sid=None):
    sid = sid or str(uuid4())
    sessions[sid] = uid
    # Host clock adjustments can put a just-issued fixture token in the future.
    now = int(time.time()) - 5
    access = jwt.encode({'sub': uid, 'session_id': sid, 'iat': now, 'exp': now + 3600,
                         'iss': issuer, 'aud': 'authenticated', 'role': 'authenticated'},
                        key, algorithm='ES256', headers={'kid': 'e2e'})
    refresh = secrets.token_urlsafe(32)
    refreshes[refresh] = (uid, sid)
    return {'access_token': access, 'refresh_token': refresh, 'expires_in': 3600}


@app.get('/health')
def health():
    return {'ok': True}


@app.post('/reset')
def reset(authorization: str = Header(default='')):
    admin_key(authorization)
    isolated_database()
    initialize()
    with connect() as c:
        tables = [r['tablename'] for r in c.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND left(tablename,7)='studio_' AND tablename<>'studio_schema_migrations'")]
        c.execute(sql.SQL('TRUNCATE {} RESTART IDENTITY CASCADE').format(
            sql.SQL(',').join(sql.Identifier(t) for t in tables)))
    users.clear()
    sessions.clear()
    refreshes.clear()
    initialize()
    seed_test_accounts('a123456789!')
    return {'ok': True}


@app.get('/auth/v1/.well-known/jwks.json')
def jwks():
    public = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    return {'keys': [{**public, 'kid': 'e2e', 'alg': 'ES256', 'use': 'sig'}]}


@app.get('/auth/v1/admin/users/{uid}')
def get_user(uid: str, authorization: str = Header(default='')):
    admin_key(authorization)
    if uid not in users:
        raise HTTPException(404)
    return {'id': uid, 'email': internal_email(uid)}


@app.post('/auth/v1/admin/users')
def create_user(body: dict, authorization: str = Header(default='')):
    admin_key(authorization)
    uid = body['id']
    if uid in users:
        raise HTTPException(409)
    users[uid] = body['password']
    return {'id': uid, 'email': internal_email(uid)}


@app.put('/auth/v1/admin/users/{uid}')
def update_user(uid: str, body: dict, authorization: str = Header(default='')):
    admin_key(authorization)
    if uid not in users:
        raise HTTPException(404)
    users[uid] = body['password']
    return {'id': uid}


@app.post('/auth/v1/token')
def login(body: dict, grant_type: str):
    if grant_type == 'password':
        uid = body.get('email', '').split('@')[0]
        if uid not in users or users[uid] != body.get('password'):
            raise HTTPException(400)
        return tokens(uid)
    pair = refreshes.pop(body.get('refresh_token'), None)
    if grant_type != 'refresh_token' or not pair or pair[1] not in sessions:
        raise HTTPException(400)
    return tokens(*pair)


@app.post('/auth/v1/logout')
def logout(authorization: str = Header(default='')):
    try:
        claims = jwt.decode(authorization.removeprefix('Bearer '), key.public_key(),
                            algorithms=['ES256'], issuer=issuer, audience='authenticated')
    except jwt.PyJWTError:
        raise HTTPException(401) from None
    sessions.pop(claims['session_id'], None)
    return {}
