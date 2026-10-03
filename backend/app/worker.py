"""Durable Postgres queue with leases, fencing, retries and atomic publication."""
import json
import logging
import signal
import threading
import uuid
from .config import settings
from .db import database
from .storage import storage
from .extraction import extract, chunk_pages
from .provider import embed

log=logging.getLogger('sourceboard.worker')
stop=threading.Event()


def claim():
    with database() as db:
        db.execute("""UPDATE documents SET status='failed',lease_token=NULL,lease_until=NULL,
                      error='Worker stopped repeatedly. Retry this document after checking worker health.'
                      WHERE status='processing' AND lease_until<now() AND attempts>=3""")
        doc=db.execute("""SELECT * FROM documents
              WHERE (status IN ('queued','deleting') AND available_at<=now()
                     AND (lease_until IS NULL OR lease_until<now()))
                 OR (status='processing' AND lease_until<now())
              ORDER BY (status='deleting') DESC,available_at
              FOR UPDATE SKIP LOCKED LIMIT 1""").fetchone()
        if not doc: return None
        token=uuid.uuid4()
        return db.execute("""UPDATE documents SET status=CASE WHEN status='deleting' THEN 'deleting' ELSE 'processing' END,
                           attempts=attempts+1,lease_until=now()+interval '15 minutes',lease_token=%s
                           WHERE id=%s RETURNING *""",(token,doc['id'])).fetchone()


def heartbeat(doc):
    with database() as db:
        return db.execute("""UPDATE documents SET lease_until=now()+interval '15 minutes'
                           WHERE id=%s AND lease_token=%s AND status='processing' RETURNING id""",
                          (doc['id'],doc['lease_token'])).fetchone() is not None


def process(doc):
    if doc['status']=='deleting':
        storage().delete_object(Bucket=settings().s3_bucket,Key=doc['object_key'])
        with database() as db:
            db.execute("DELETE FROM documents WHERE id=%s AND lease_token=%s AND status='deleting'",(doc['id'],doc['lease_token']))
        return
    obj=storage().get_object(Bucket=settings().s3_bucket,Key=doc['object_key'])
    try: content=obj['Body'].read(settings().upload_limit+1)
    finally: obj['Body'].close()
    if len(content)>settings().upload_limit: raise ValueError('File exceeds upload limit.')
    pages=extract(doc['name'],content)
    chunks=chunk_pages(pages)
    vectors=[]
    for start in range(0,len(chunks),24):
        if not heartbeat(doc): return
        vectors.extend(embed([c['text'] for c in chunks[start:start+24]]))
    with database() as db:
        current=db.execute('SELECT status,lease_token FROM documents WHERE id=%s FOR UPDATE',(doc['id'],)).fetchone()
        if not current or current['status']!='processing' or current['lease_token']!=doc['lease_token']: return
        db.execute('DELETE FROM chunks WHERE document_id=%s',(doc['id'],))
        with db.cursor() as cursor:
            cursor.executemany('''INSERT INTO chunks(id,document_id,workspace_id,text,page,ordinal,embedding)
                                  VALUES(%s,%s,%s,%s,%s,%s,%s::vector)''',
                               [(uuid.uuid4(),doc['id'],doc['workspace_id'],c['text'],c['page'],c['ordinal'],json.dumps(v))
                                for c,v in zip(chunks,vectors,strict=True)])
        db.execute("""UPDATE documents SET status='ready',pages=%s,chunk_count=%s,embedding_model=%s,
                      lease_until=NULL,lease_token=NULL,error=NULL WHERE id=%s""",
                   (len(pages),len(chunks),settings().embedding_model,doc['id']))


def fail(doc, error):
    permanent=isinstance(error,ValueError)
    deleting=doc['status']=='deleting'
    status='deleting' if deleting else ('failed' if permanent or doc['attempts']>=3 else 'queued')
    message=str(error) if permanent else 'Processing service unavailable. Retry after checking worker, storage, and provider configuration.'
    with database() as db:
        db.execute("""UPDATE documents SET status=%s,error=%s,lease_until=NULL,lease_token=NULL,
                      available_at=now()+interval '30 seconds' WHERE id=%s AND lease_token=%s""",
                   (status,message,doc['id'],doc['lease_token']))


def main():
    logging.basicConfig(level=logging.INFO)
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,lambda *_:stop.set())
    log.info('Ingestion worker started')
    while not stop.is_set():
        try:
            doc=claim()
            if not doc:
                stop.wait(settings().worker_poll_seconds)
                continue
            try:
                process(doc)
                log.info('Job handled: %s',doc['id'])
            except Exception as error:
                # No source text, provider responses, or credentials in logs.
                log.warning('Job %s failed (%s)',doc['id'],type(error).__name__)
                fail(doc,error)
        except Exception as error:
            log.warning('Queue unavailable (%s)',type(error).__name__)
            stop.wait(settings().worker_poll_seconds)


if __name__=='__main__': main()
