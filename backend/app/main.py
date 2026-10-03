import hashlib
import secrets
import uuid
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
import psycopg
from psycopg.types.json import Jsonb
from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from .auth import current_user, hash_password, check_password
from .config import settings
from .db import database
from .extraction import ALLOWED
from .storage import storage
from .provider import ProviderError
from .rag import answer, abstain

app=FastAPI(title='Sourceboard API',version='0.2.0')
User=Annotated[dict,Depends(current_user)]


@app.middleware('http')
async def security(request: Request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        if request.headers.get('origin') and request.headers['origin'] != settings().app_origin:
            return JSONResponse({'detail':'Origin not allowed.'},403)
        if request.headers.get('x-sourceboard') != '1':
            return JSONResponse({'detail':'Missing request protection header.'},403)
        try: length=int(request.headers.get('content-length','0'))
        except ValueError: return JSONResponse({'detail':'Invalid content length.'},400)
        limit=settings().upload_limit+1024*1024 if request.url.path=='/api/documents' else 32*1024
        if length>limit: return JSONResponse({'detail':'Request too large.'},413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Cache-Control']='no-store'
    return response


@app.exception_handler(ProviderError)
async def provider_error(request, error):
    return JSONResponse({'detail':str(error),'status':'provider_unavailable'},503)


@app.exception_handler(psycopg.OperationalError)
async def database_error(request, error):
    return JSONResponse({'detail':'Database unavailable. Please retry shortly.'},503)


class Credentials(BaseModel):
    email: str = Field(min_length=3,max_length=254,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=10,max_length=128)
    workspace: str = Field(default='My workspace',min_length=1,max_length=80)


class Question(BaseModel):
    question: str = Field(min_length=3,max_length=2000)


def session(response, db, user_id):
    token=secrets.token_urlsafe(32)
    db.execute('DELETE FROM sessions WHERE expires_at<now()')
    db.execute("INSERT INTO sessions VALUES(%s,%s,now()+interval '7 days')",
               (hashlib.sha256(token.encode()).hexdigest(),user_id))
    response.set_cookie('session',token,httponly=True,secure=settings().cookie_secure,samesite='strict',max_age=604800)


@app.post('/api/register',status_code=201)
def register(body: Credentials,response: Response):
    user_id,workspace_id=uuid.uuid4(),uuid.uuid4()
    salt=secrets.token_hex(16)
    hashed=hash_password(body.password,salt)
    try:
        with database() as db:
            db.execute('INSERT INTO workspaces(id,name) VALUES(%s,%s)',(workspace_id,body.workspace.strip() or 'My workspace'))
            db.execute('INSERT INTO users(id,workspace_id,email,password_hash,salt) VALUES(%s,%s,%s,%s,%s)',
                       (user_id,workspace_id,body.email.lower(),hashed,salt))
            session(response,db,user_id)
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409,'Unable to create account. Try signing in.')
    return {'ok':True}


@app.post('/api/login')
def login(body: Credentials,response: Response):
    with database() as db:
        user=db.execute('SELECT * FROM users WHERE email=%s',(body.email.lower(),)).fetchone()
        valid=check_password(body.password,user['salt'] if user else '00'*16,user['password_hash'] if user else '0'*128)
        if not user or not valid: raise HTTPException(401,'Email or password is incorrect.')
        session(response,db,user['id'])
    return {'ok':True}


@app.post('/api/logout')
def logout(request: Request,response: Response,user: User):
    with database() as db:
        db.execute('DELETE FROM sessions WHERE token_hash=%s',
                   (hashlib.sha256(request.cookies.get('session','').encode()).hexdigest(),))
    response.delete_cookie('session',httponly=True,samesite='strict',secure=settings().cookie_secure)
    return {'ok':True}


@app.get('/api/me')
def me(user: User):
    return {**user,'provider_configured':bool(settings().model_api_key)}


@app.get('/health/live')
def live(): return {'status':'ok'}


@app.get('/health/ready')
def ready():
    with database() as db: db.execute('SELECT 1 FROM schema_migrations LIMIT 1')
    try: storage().head_bucket(Bucket=settings().s3_bucket)
    except Exception: raise HTTPException(503,'Object storage unavailable.')
    return {'status':'ok'}


@app.get('/api/documents')
def documents(user: User):
    with database() as db:
        return db.execute('''SELECT id,name,size,status,pages,chunk_count,error,attempts,created_at
                             FROM documents WHERE workspace_id=%s ORDER BY created_at DESC''',(user['workspace_id'],)).fetchall()


@app.post('/api/documents',status_code=202)
def upload(file: UploadFile,user: User):
    if not settings().model_api_key: raise HTTPException(503,'Configure MODEL_API_KEY before uploading documents.')
    name=(file.filename or '').replace('\\','/').split('/')[-1][:200]
    if Path(name).suffix.lower() not in ALLOWED: raise HTTPException(400,'Supported formats: PDF, TXT, Markdown, CSV.')
    content=file.file.read(settings().upload_limit+1)
    if not content: raise HTTPException(400,'The file is empty.')
    if len(content)>settings().upload_limit: raise HTTPException(413,'Files must be 10 MB or smaller.')
    doc_id=uuid.uuid4()
    key=f'{user["workspace_id"]}/{doc_id}/original'
    try: storage().put_object(Bucket=settings().s3_bucket,Key=key,Body=content,ContentType='application/octet-stream')
    except Exception: raise HTTPException(503,'Object storage unavailable. Please retry.')
    try:
        with database() as db:
            db.execute('INSERT INTO documents(id,workspace_id,name,object_key,size) VALUES(%s,%s,%s,%s,%s)',
                       (doc_id,user['workspace_id'],name,key,len(content)))
    except Exception:
        # Compensate if the queue transaction fails after object creation.
        storage().delete_object(Bucket=settings().s3_bucket,Key=key)
        raise
    return {'id':doc_id,'status':'queued'}


@app.post('/api/documents/{document_id}/retry')
def retry(document_id: uuid.UUID,user: User):
    with database() as db:
        row=db.execute("""UPDATE documents SET status='queued',error=NULL,attempts=0,available_at=now(),lease_until=NULL,lease_token=NULL
                          WHERE id=%s AND workspace_id=%s AND status='failed' RETURNING id""",
                       (document_id,user['workspace_id'])).fetchone()
    if not row: raise HTTPException(404,'Failed document not found.')
    return {'status':'queued'}


@app.delete('/api/documents/{document_id}',status_code=202)
def delete(document_id: uuid.UUID,user: User):
    with database() as db:
        # Serialize deletion with history persistence, without holding a lock during model calls.
        db.execute('SELECT id FROM workspaces WHERE id=%s FOR NO KEY UPDATE',(user['workspace_id'],))
        row=db.execute("""UPDATE documents SET status='deleting',lease_token=NULL,lease_until=NULL,available_at=now(),error=NULL
                          WHERE id=%s AND workspace_id=%s RETURNING id""",(document_id,user['workspace_id'])).fetchone()
        if not row: raise HTTPException(404,'Document not found.')
        db.execute('DELETE FROM chunks WHERE document_id=%s AND workspace_id=%s',(document_id,user['workspace_id']))
        db.execute('DELETE FROM questions WHERE workspace_id=%s',(user['workspace_id'],))
    return {'status':'deleting'}


@app.get('/api/documents/{document_id}/download')
def download(document_id: uuid.UUID,user: User):
    with database() as db:
        doc=db.execute("SELECT * FROM documents WHERE id=%s AND workspace_id=%s AND status!='deleting'",
                       (document_id,user['workspace_id'])).fetchone()
    if not doc: raise HTTPException(404,'Document not found.')
    try: obj=storage().get_object(Bucket=settings().s3_bucket,Key=doc['object_key'])
    except Exception: raise HTTPException(503,'Original file is unavailable. Please retry.')
    def stream():
        try: yield from obj['Body'].iter_chunks(chunk_size=64*1024)
        finally: obj['Body'].close()
    return StreamingResponse(stream(),media_type='application/octet-stream',headers={
        'Content-Disposition':f"attachment; filename*=UTF-8''{quote(doc['name'],safe='')}"})


@app.get('/api/history')
def history(user: User):
    with database() as db:
        return db.execute('SELECT id,question,result,created_at FROM questions WHERE workspace_id=%s ORDER BY created_at DESC LIMIT 30',
                          (user['workspace_id'],)).fetchall()


@app.post('/api/ask')
def ask(body: Question,user: User):
    question=body.question.strip()
    if len(question)<3: raise HTTPException(400,'Enter a question of at least 3 characters.')
    result=answer(user['workspace_id'],question)
    with database() as db:
        db.execute('SELECT id FROM workspaces WHERE id=%s FOR NO KEY UPDATE',(user['workspace_id'],))
        ids=[uuid.UUID(s['id']) for s in result['sources']]
        if ids:
            alive=db.execute("""SELECT c.id FROM chunks c JOIN documents d ON d.id=c.document_id
                                WHERE c.id=ANY(%s) AND c.workspace_id=%s AND d.status='ready'""",
                             (ids,user['workspace_id'])).fetchall()
            if len(alive)!=len(ids): result=abstain('sources_changed')
        db.execute('INSERT INTO questions(id,workspace_id,question,result) VALUES(%s,%s,%s,%s)',
                   (uuid.uuid4(),user['workspace_id'],question,Jsonb(result)))
    return result
