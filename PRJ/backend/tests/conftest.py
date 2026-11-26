import pytest
from fastapi.testclient import TestClient
from app.config import settings
from app.db import connect, initialize
from app.main import app


@pytest.fixture(autouse=True)
def isolated_database():
    assert "studio_test" in settings().database_url, (
        "Tests require the isolated studio_test PostgreSQL database"
    )
    assert settings().ai_mode == settings().auth_mode == "mock"
    initialize()
    with connect() as c:
        c.execute(
            "TRUNCATE studio_github_authorizations,studio_github_connections,studio_messages,studio_proposals,studio_jobs,studio_revisions,studio_projects,studio_sources,studio_code_snapshots RESTART IDENTITY CASCADE"
        )


@pytest.fixture
def client():
    with TestClient(app, headers={"Authorization": "Bearer local:alice"}) as c:
        yield c
