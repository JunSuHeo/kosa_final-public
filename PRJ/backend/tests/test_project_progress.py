from uuid import uuid4
import pytest
from app.db import connect
from test_studio import make_project, generated, approve


def progress(client, pid):
    rows = client.get('/api/projects').json()
    return next(row for row in rows if row['id'] == pid).get('progress_status')


@pytest.mark.parametrize('status,expected', [
    ('queued', 'generating'), ('running', 'generating'),
    ('awaiting_answers', 'awaiting_answers'), ('failed', 'failed'),
    ('cancelled', 'conversation'), ('completed', 'conversation'),
])
def test_project_list_uses_persisted_generation_status(client, status, expected):
    pid, _ = make_project(client)
    with connect() as c:
        c.execute('UPDATE studio_jobs SET status=%s WHERE project_id=%s', (status, pid))
    assert progress(client, pid) == expected
    assert client.get('/api/projects', headers={'Authorization': 'Bearer local:bob'}).json() == []


def test_pending_proposal_and_confirmed_revision_progress(client):
    pid, result = generated(client)
    assert progress(client, pid) == 'review_ready'
    assert approve(client, pid, result['proposal']).status_code == 200
    assert progress(client, pid) == 'confirmed'
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,1,'discuss','completed','대화','openrouter','mock','mock')", (uuid4(), pid))
    assert progress(client, pid) == 'confirmed'


def test_cancelled_job_does_not_hide_previous_failure(client):
    pid, _ = make_project(client)
    with connect() as c:
        c.execute("UPDATE studio_jobs SET status='failed' WHERE project_id=%s", (pid,))
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,0,'revise','cancelled','재시도','openrouter','mock','mock')", (uuid4(), pid))
    assert progress(client, pid) == 'failed'


@pytest.mark.parametrize('status', ['queued', 'running', 'completed'])
def test_discussion_job_keeps_conversation_progress(client, status):
    pid, _ = make_project(client)
    with connect() as c:
        c.execute('UPDATE studio_jobs SET kind=%s,status=%s WHERE project_id=%s', ('discuss', status, pid))
    assert progress(client, pid) == 'conversation'


@pytest.mark.parametrize('kind', ['discuss', 'revise'])
def test_latest_failed_action_precedes_pending_proposal_progress(client, kind):
    pid, result = generated(client)
    proposal_id = result['proposal']['id']
    assert progress(client, pid) == 'review_ready'
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,0,%s,'failed','다음 작업','openrouter','mock','mock')", (uuid4(), pid, kind))
    assert progress(client, pid) == 'failed'
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,0,'revise','cancelled','취소한 재시도','openrouter','mock','mock')", (uuid4(), pid))
    assert progress(client, pid) == 'failed'
    response = client.get(f'/api/projects/{pid}').json()
    assert response['proposal']['id'] == proposal_id
    assert response['proposal']['status'] == 'pending'


@pytest.mark.parametrize('expected', ['conversation', 'review_ready', 'confirmed'])
def test_successful_discussion_retry_resolves_previous_discussion_failure(client, expected):
    version = 1 if expected == 'confirmed' else 0
    if expected == 'conversation':
        pid, _ = make_project(client)
        with connect() as c:
            c.execute("UPDATE studio_jobs SET kind='discuss',status='failed' WHERE project_id=%s", (pid,))
    else:
        pid, result = generated(client)
        if expected == 'confirmed':
            assert approve(client, pid, result['proposal']).status_code == 200
        with connect() as c:
            c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,%s,'discuss','failed','실패한 대화','openrouter','mock','mock')", (uuid4(), pid, version))
    assert progress(client, pid) == 'failed'
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,%s,'discuss','cancelled','취소한 대화 재시도','openrouter','mock','mock')", (uuid4(), pid, version))
    assert progress(client, pid) == 'failed'
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,%s,'discuss','completed','성공한 대화 재시도','openrouter','mock','mock')", (uuid4(), pid, version))
    assert progress(client, pid) == expected
    if expected == 'review_ready':
        assert client.get(f'/api/projects/{pid}').json()['proposal']['id'] == result['proposal']['id']
    with connect() as c:
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,%s,'discuss','failed','다시 실패한 새 대화','openrouter','mock','mock')", (uuid4(), pid, version))
    assert progress(client, pid) == 'failed'


def test_successful_discussion_does_not_resolve_generation_failure(client):
    pid, _ = make_project(client)
    with connect() as c:
        c.execute("UPDATE studio_jobs SET status='failed' WHERE project_id=%s", (pid,))
        c.execute("INSERT INTO studio_jobs(id,project_id,base_version,kind,status,request,provider,model,ai_mode) VALUES (%s,%s,0,'discuss','completed','성공한 대화','openrouter','mock','mock')", (uuid4(), pid))
    assert progress(client, pid) == 'failed'
