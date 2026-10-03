"""Sourceboard: tenant-scoped knowledge retrieval with evidence-first responses."""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import io
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).parent
DB = Path(os.environ.get('SOURCEBOARD_DB', str(ROOT / 'data' / 'sourceboard.db')))
MAX_UPLOAD = 10 * 1024 * 1024
STOP = set('a an the is are was were what which who when where how why can could would should do does did to of for in on and or with from about me tell please our your it this that be have has'.split())

@contextmanager
def connect():
    con = sqlite3.connect(DB, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys=ON')
    try:
        with con:
            yield con
    finally:
        con.close()

def init_db():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as c:
        c.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE,password TEXT,salt TEXT,workspace TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),name TEXT,size INTEGER,pages INTEGER,created REAL);
        CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,document_id TEXT REFERENCES documents(id) ON DELETE CASCADE,user_id TEXT,text TEXT,page INTEGER);
        CREATE INDEX IF NOT EXISTS chunk_owner ON chunks(user_id);
        CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY,user_id TEXT,question TEXT,answer TEXT,created REAL);
        CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(text,chunk_id UNINDEXED,user_id UNINDEXED, tokenize='unicode61');
        ''')

def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()

def extract(name, content):
    ext = Path(name).suffix.lower()
    if ext == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError('PDF support needs pypdf. Run pip install -r requirements.txt.')
        try:
            reader = PdfReader(io.BytesIO(content))
            if len(reader.pages) > 300:
                raise ValueError('PDFs are limited to 300 pages.')
            pages = [p.extract_text() or '' for p in reader.pages]
        except ValueError:
            raise
        except Exception:
            raise ValueError('Could not read this PDF. Upload an unlocked, text-based PDF.')
    elif ext in ('.txt', '.md', '.csv'):
        try:
            pages = [content.decode('utf-8-sig')]
        except UnicodeDecodeError:
            raise ValueError('Text documents must use UTF-8 encoding.')
    else:
        raise ValueError('Supported formats: PDF, TXT, Markdown, and CSV.')
    if not any(p.strip() for p in pages):
        raise ValueError('No readable text found. Scanned PDFs need OCR before uploading.')
    if sum(map(len, pages)) > 2_000_000:
        raise ValueError('Extracted document text exceeds the 2 million character limit.')
    return pages

def ingest(user, name, content):
    pages = extract(name, content)
    doc_id = secrets.token_hex(12)
    count = 0
    with connect() as c:
        c.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)', (doc_id,user,name,len(content),len(pages),time.time()))
        for page, text in enumerate(pages, 1):
            words = text.split()
            for start in range(0,len(words),160):
                passage = ' '.join(words[start:start+200])
                if not passage: continue
                chunk_id = secrets.token_hex(12)
                c.execute('INSERT INTO chunks VALUES(?,?,?,?,?)',(chunk_id,doc_id,user,passage,page))
                c.execute('INSERT INTO passages VALUES(?,?,?)',(passage,chunk_id,user))
                count += 1
    return {'id':doc_id,'chunks':count}

def answer_question(user, question):
    terms = list(dict.fromkeys(t for t in re.findall(r'\w+',question.lower()) if t not in STOP and len(t)>1))[:24]
    sources = []
    if terms:
        match = ' OR '.join('"'+t+'"' for t in terms)
        with connect() as c:
            rows = c.execute('''SELECT ch.id,ch.text,ch.page,d.name,d.id AS document_id,bm25(passages) AS rank
              FROM passages JOIN chunks ch ON ch.id=passages.chunk_id JOIN documents d ON d.id=ch.document_id
              WHERE passages MATCH ? AND ch.user_id=? AND passages.user_id=? ORDER BY rank LIMIT 12''',(match,user,user)).fetchall()
        for row in rows:
            words = set(re.findall(r'\w+',row['text'].lower()))
            coverage = len(words.intersection(terms))/len(terms)
            if coverage < .6: continue
            if any(s['document_id']==row['document_id'] and s['page']==row['page'] for s in sources): continue
            sources.append({k:row[k] for k in ('id','text','page','name','document_id')})
            if len(sources)==3: break
    if sources:
        answer = 'I found these source passages related to your question. These are direct excerpts; relevance does not guarantee they fully answer your question.'
    else:
        answer = 'Insufficient evidence. I couldn’t find source passages that reliably match this question. Try a more specific question or upload a document that covers this topic.'
    result = {'answer':answer,'sources':sources,'status':'evidence_found' if sources else 'insufficient_evidence','mode':'extractive'}
    with connect() as c:
        c.execute('INSERT INTO questions VALUES(?,?,?,?,?)',(secrets.token_hex(12),user,question,json.dumps(result),time.time()))
    return result

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Never log query strings, request content, or session tokens.
        pass

    def respond(self,status,data,cookie=None):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if cookie: self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)

    def user(self):
        cookie = SimpleCookie()
        try: cookie.load(self.headers.get('Cookie',''))
        except Exception: return None
        token = cookie.get('session')
        if not token: return None
        with connect() as c:
            row = c.execute('SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?',(hashlib.sha256(token.value.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None

    def do_GET(self):
        path = urlparse(self.path).path
        if not path.startswith('/api/'):
            files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'}
            if path not in files: return self.respond(404,{'error':'Not found'})
            file = ROOT / 'static' / files[path]
            raw = file.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}[file.suffix[1:]])
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
            self.end_headers()
            self.wfile.write(raw)
            return
        user = self.user()
        if not user: return self.respond(401,{'error':'Sign in to your workspace.'})
        if path == '/api/me': return self.respond(200,{k:user[k] for k in ('email','workspace')})
        with connect() as c:
            if path == '/api/documents':
                rows = c.execute('SELECT d.*, (SELECT count(*) FROM chunks WHERE document_id=d.id) AS chunks FROM documents d WHERE user_id=? ORDER BY created DESC',(user['id'],)).fetchall()
                return self.respond(200,[dict(r) for r in rows])
            if path == '/api/history':
                rows = c.execute('SELECT question,answer,created FROM questions WHERE user_id=? ORDER BY created DESC LIMIT 30',(user['id'],)).fetchall()
                return self.respond(200,[dict(r) for r in rows])
        return self.respond(404,{'error':'Not found'})

    def do_POST(self):
        try:
            # Require same-origin JSON requests. Browsers cannot cross-origin POST
            # this content type without a preflight, which this server never allows.
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.respond(415,{'error':'Expected application/json'})
            length = int(self.headers.get('Content-Length','0'))
            if length <= 0 or length > MAX_UPLOAD*1.4:
                return self.respond(413,{'error':'Request too large (10 MB file limit).'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('Expected a JSON object.')
            path = urlparse(self.path).path
            if path in ('/api/register','/api/login'):
                email = str(body.get('email','')).strip().lower()
                password = str(body.get('password',''))
                if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email) or len(email)>254:
                    raise ValueError('Enter a valid email address.')
                if not 10<=len(password)<=128: raise ValueError('Use a password between 10 and 128 characters.')
                with connect() as c:
                    if path.endswith('register'):
                        salt = secrets.token_hex(16)
                        uid = secrets.token_hex(12)
                        workspace = str(body.get('workspace','My workspace')).strip()[:80] or 'My workspace'
                        try: c.execute('INSERT INTO users VALUES(?,?,?,?,?)',(uid,email,password_hash(password,salt),salt,workspace))
                        except sqlite3.IntegrityError: raise ValueError('Unable to create account. Try signing in.')
                    else:
                        row = c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()
                        computed = password_hash(password,row['salt'] if row else '00'*16)
                        if not row or not hmac.compare_digest(row['password'],computed):
                            return self.respond(401,{'error':'Email or password is incorrect.'})
                        uid = row['id']
                    token = secrets.token_urlsafe(32)
                    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
                    c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+86400*7))
                secure = '; Secure' if os.environ.get('COOKIE_SECURE')=='1' else ''
                return self.respond(200,{'ok':True},f'session={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=604800{secure}')
            user = self.user()
            if not user: return self.respond(401,{'error':'Sign in to your workspace.'})
            if path == '/api/logout':
                with connect() as c: c.execute('DELETE FROM sessions WHERE user_id=?',(user['id'],))
                return self.respond(200,{'ok':True},'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path == '/api/upload':
                import base64
                name = str(body.get('name','')).replace('\\','/').split('/')[-1][:200]
                try: content = base64.b64decode(body.get('content',''),validate=True)
                except Exception: raise ValueError('Invalid file encoding.')
                if len(content)>MAX_UPLOAD: raise ValueError('Files must be under 10 MB.')
                return self.respond(201,ingest(user['id'],name,content))
            if path == '/api/ask':
                question = str(body.get('question','')).strip()
                if not 3<=len(question)<=2000: raise ValueError('Questions must contain 3–2,000 characters.')
                return self.respond(200,answer_question(user['id'],question))
            if path == '/api/delete':
                with connect() as c:
                    ids = c.execute('SELECT id FROM chunks WHERE document_id=? AND user_id=?',(body.get('id'),user['id'])).fetchall()
                    for row in ids: c.execute('DELETE FROM passages WHERE chunk_id=?',(row['id'],))
                    c.execute('DELETE FROM documents WHERE id=? AND user_id=?',(body.get('id'),user['id']))
                    # Historical answers contain excerpts; purge on deletion.
                    c.execute('DELETE FROM questions WHERE user_id=?',(user['id'],))
                return self.respond(200,{'ok':True})
            return self.respond(404,{'error':'Not found'})
        except (ValueError,TypeError) as error:
            return self.respond(400,{'error':str(error)})
        except Exception:
            return self.respond(500,{'error':'The request could not be completed. Please try again.'})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT','8000'))
    print(f'Sourceboard is running at http://127.0.0.1:{port}',flush=True)
    ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),port),Handler).serve_forever()
