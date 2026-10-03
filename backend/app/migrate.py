from pathlib import Path
from .db import database
from .storage import storage
from .config import settings
from botocore.exceptions import ClientError


def main():
    with database() as db:
        db.execute('SELECT pg_advisory_xact_lock(734192)')
        db.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz DEFAULT now())')
        for file in sorted((Path(__file__).resolve().parents[1] / 'migrations').glob('*.sql')):
            if not db.execute('SELECT 1 FROM schema_migrations WHERE name=%s',(file.name,)).fetchone():
                db.execute(file.read_text(encoding='utf-8'))
                db.execute('INSERT INTO schema_migrations(name) VALUES(%s)',(file.name,))
    client = storage()
    try:
        client.head_bucket(Bucket=settings().s3_bucket)
    except ClientError as error:
        if error.response['Error']['Code'] not in ('404','NoSuchBucket'): raise
        kwargs = {'Bucket':settings().s3_bucket}
        if settings().s3_region != 'us-east-1':
            kwargs['CreateBucketConfiguration'] = {'LocationConstraint':settings().s3_region}
        client.create_bucket(**kwargs)
    print('Migrations applied; object storage ready.')


if __name__ == '__main__':
    main()
