import hashlib
import hmac
from fastapi import Request, HTTPException
from .db import database


def hash_password(password: str, salt: str):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()


def check_password(password, salt, expected):
    return hmac.compare_digest(hash_password(password,salt),expected)


def current_user(request: Request):
    token=request.cookies.get('session','')
    if not token: raise HTTPException(401,'Sign in to your workspace.')
    with database() as db:
        user=db.execute('''SELECT u.id,u.email,u.workspace_id,w.name AS workspace
                           FROM sessions s JOIN users u ON u.id=s.user_id JOIN workspaces w ON w.id=u.workspace_id
                           WHERE s.token_hash=%s AND s.expires_at>now()''',
                           (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    if not user: raise HTTPException(401,'Your session expired. Sign in again.')
    return user
