"""Run only against dedicated test infrastructure; never a production database."""
import os
import uuid
import pytest
from fastapi.testclient import TestClient
from app import worker, provider
from app.config import settings
from app.db import database
from app.main import app
from app.migrate import main as migrate
from app.storage import storage

pytestmark=[pytest.mark.integration,pytest.mark.skipif(not os.environ.get('TEST_DATABASE_URL'),reason='Dedicated Postgres/MinIO integration environment not configured')]


@pytest.fixture
def infrastructure(monkeypatch):
    monkeypatch.setenv('DATABASE_URL',os.environ['TEST_DATABASE_URL'])
    monkeypatch.setenv('MODEL_API_KEY','fake-test-key')
    settings.cache_clear()
    migrate()
    monkeypatch.setattr(provider,'embed',lambda texts:[[1.0]+[0.0]*1535 for _ in texts])
    monkeypatch.setattr(worker,'embed',provider.embed)
    monkeypatch.setattr(provider,'generate',lambda question,sources:{'answerable':True,'claims':[{
        'text':'Employees may work remotely three days per week.',
        'evidence':[{'source_id':sources[0]['source_id'],'quote':'Employees may work remotely three days per week.'}]}]})
    monkeypatch.setattr(provider,'verify',lambda *a:True)
    workspaces=[]
    yield workspaces
    with database() as db:
        for workspace in workspaces:
            docs=db.execute('SELECT object_key FROM documents WHERE workspace_id=%s',(workspace,)).fetchall()
            for doc in docs: storage().delete_object(Bucket=settings().s3_bucket,Key=doc['object_key'])
            db.execute('DELETE FROM questions WHERE workspace_id=%s',(workspace,))
            db.execute('DELETE FROM documents WHERE workspace_id=%s',(workspace,))
            db.execute('DELETE FROM users WHERE workspace_id=%s',(workspace,))
            db.execute('DELETE FROM workspaces WHERE id=%s',(workspace,))
    settings.cache_clear()


def create_user(client,workspaces):
    response=client.post('/api/register',json={'email':f'{uuid.uuid4()}@test.example','password':'test-password-123','workspace':'Integration test'})
    assert response.status_code==201,response.text
    user=client.get('/api/me').json()
    workspaces.append(user['workspace_id'])


def test_upload_worker_vector_answer_isolation_and_deletion(infrastructure):
    with TestClient(app,headers={'X-Sourceboard':'1'}) as alice,TestClient(app,headers={'X-Sourceboard':'1'}) as bob:
        create_user(alice,infrastructure)
        create_user(bob,infrastructure)
        uploaded=alice.post('/api/documents',files={'file':('policy.txt',b'Employees may work remotely three days per week. Manager approval is required.','text/plain')})
        assert uploaded.status_code==202,uploaded.text
        doc_id=uploaded.json()['id']
        job=worker.claim()
        assert str(job['id'])==doc_id
        worker.process(job)
        assert alice.get('/api/documents').json()[0]['status']=='ready'
        result=alice.post('/api/ask',json={'question':'What is the remote work policy?'}).json()
        assert result['status']=='answered'
        assert result['sources'][0]['document_id']==doc_id
        assert bob.get('/api/documents').json()==[]
        assert bob.get(f'/api/documents/{doc_id}/download').status_code==404
        assert bob.delete(f'/api/documents/{doc_id}').status_code==404
        assert bob.post('/api/ask',json={'question':'What is the remote work policy?'}).json()['status']=='insufficient_evidence'
        assert alice.delete(f'/api/documents/{doc_id}').status_code==202
        assert alice.get('/api/history').json()==[]
        assert alice.post('/api/ask',json={'question':'What is the remote work policy?'}).json()['sources']==[]
        job=worker.claim()
        assert job['status']=='deleting'
        worker.process(job)
        assert alice.get('/api/documents').json()==[]


def test_worker_fencing_prevents_deleted_source_from_reappearing(infrastructure):
    with TestClient(app,headers={'X-Sourceboard':'1'}) as client:
        create_user(client,infrastructure)
        result=client.post('/api/documents',files={'file':('policy.txt',b'Employees may work remotely three days per week.','text/plain')}).json()
        job=worker.claim()
        client.delete(f'/api/documents/{result["id"]}')
        worker.process(job)
        with database() as db:
            assert db.execute('SELECT count(*) AS n FROM chunks WHERE document_id=%s',(result['id'],)).fetchone()['n']==0
        worker.process(worker.claim())
