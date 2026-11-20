from uuid import uuid4
import psycopg
import pytest
from app.config import settings
from app.db import connect, initialize
from test_business_planning import setup_business, job
from test_studio import bundle
from test_source_planning import repos
from app.worker import process


@pytest.fixture
def target(monkeypatch):
    source = settings().database_url
    name = 'studio_test_transfer_' + uuid4().hex[:8]
    assert 'studio_test' in source
    with psycopg.connect(source, autocommit=True) as c:
        c.execute(psycopg.sql.SQL('CREATE DATABASE {}').format(psycopg.sql.Identifier(name)))
    info = psycopg.conninfo.conninfo_to_dict(source)
    info['dbname'] = name
    url = psycopg.conninfo.make_conninfo(**info)
    try:
        with monkeypatch.context() as m:
            m.setattr(settings(), 'database_url', url)
            initialize()
        yield source, url
    finally:
        with psycopg.connect(source, autocommit=True) as c:
            c.execute(psycopg.sql.SQL('DROP DATABASE {} WITH (FORCE)').format(psycopg.sql.Identifier(name)))


def test_transfer_dry_run_atomic_ownership_and_immutable_history(client, repos, target):
    from app.transfer import transfer
    pid, source_id, snapshot, body = setup_business(client, repos)
    process(bundle(client, pid)['job']['id'])
    initial = job(client, pid, 'generate')
    approved = client.post(f"/api/projects/{pid}/proposals/{initial['proposal']['id']}/approve", json={'expected_version': 0, 'acknowledge_warnings': True})
    assert approved.status_code == 200
    with connect() as c:
        c.execute("UPDATE studio_projects SET owner_id='old-user' WHERE id=%s", (pid,))
        c.execute("UPDATE studio_sources SET owner_id='old-user' WHERE id=%s", (source_id,))
        c.execute("INSERT INTO studio_source_assignments(source_id,account_id,assigned_by) VALUES (%s,'old-user','alice')", (source_id,))
    source_url, target_url = target
    tid = str(uuid4())
    dry = transfer(source_url, target_url, tid, apply=False)
    assert dry['tables']['studio_projects']['count'] == 1
    with psycopg.connect(target_url) as c:
        assert c.execute('SELECT count(*) FROM studio_projects').fetchone()[0] == 0
    result = transfer(source_url, target_url, tid, apply=True)
    assert result['verified']
    assert transfer(source_url, target_url, tid, apply=True)['already_applied']
    with psycopg.connect(target_url) as c:
        assert c.execute('SELECT owner_id FROM studio_projects').fetchone()[0] == 'demo-user'
        assert c.execute('SELECT owner_id FROM studio_sources').fetchone()[0] == 'demo-user'
        assert c.execute('SELECT count(*) FROM studio_source_assignments').fetchone()[0] == 0
        assert c.execute('SELECT current_version FROM studio_projects').fetchone()[0] == 1
        assert c.execute('SELECT count(*) FROM studio_revisions').fetchone()[0] == 2
    with pytest.raises(psycopg.Error), psycopg.connect(target_url) as c:
        c.execute("UPDATE studio_revisions SET summary='changed' WHERE version=1")
    with pytest.raises(psycopg.Error), psycopg.connect(target_url) as c:
        c.execute("UPDATE studio_source_publications SET owner_id='demo-user'")


def test_transfer_blocks_nonempty_destination_and_running_work(client, target):
    from app.transfer import transfer
    source_url, target_url = target
    response = client.post('/api/projects', json={'idea': '테스트 업무'})
    assert response.status_code == 201
    with pytest.raises(ValueError, match='진행 중'):
        transfer(source_url, target_url, str(uuid4()), apply=True)
    with connect() as c:
        c.execute("UPDATE studio_jobs SET status='cancelled'")
    with psycopg.connect(target_url) as c:
        c.execute("INSERT INTO studio_projects(id,owner_id,title,idea) VALUES (%s,'other','기존','업무')", (uuid4(),))
    with pytest.raises(ValueError, match='비어'):
        transfer(source_url, target_url, str(uuid4()), apply=True)
