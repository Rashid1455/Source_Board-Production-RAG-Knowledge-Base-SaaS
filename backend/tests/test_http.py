import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as client: yield client


def test_liveness_and_unauthenticated_tenant_routes(client):
    assert client.get('/health/live').status_code==200
    for path in ('/api/me','/api/documents','/api/history'):
        assert client.get(path).status_code==401


def test_csrf_protection(client):
    assert client.post('/api/login',json={}).status_code==403
    assert client.post('/api/login',json={},headers={'X-Sourceboard':'1','Origin':'https://attacker.example'}).status_code==403


def test_invalid_credentials_and_oversized_requests(client):
    assert client.post('/api/register',json={'email':'no','password':'short'},headers={'X-Sourceboard':'1'}).status_code==422
    assert client.post('/api/ask',content='a'*33000,headers={'X-Sourceboard':'1'}).status_code==413


def test_api_schema_has_real_upload_and_question_routes(client):
    schema=client.get('/openapi.json').json()
    assert 'multipart/form-data' in schema['paths']['/api/documents']['post']['requestBody']['content']
    assert '/api/documents/{document_id}/retry' in schema['paths']
