CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS workspaces (
 id uuid PRIMARY KEY, name varchar(80) NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS users (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 email varchar(254) NOT NULL UNIQUE, password_hash text NOT NULL, salt text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash text PRIMARY KEY, user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 expires_at timestamptz NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 name varchar(200) NOT NULL, object_key text NOT NULL UNIQUE, size bigint NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','ready','failed','deleting')),
 pages integer NOT NULL DEFAULT 0, chunk_count integer NOT NULL DEFAULT 0,
 error text, attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz, lease_token uuid, embedding_model text,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_workspace ON documents(workspace_id);
CREATE INDEX IF NOT EXISTS documents_queue ON documents(status,available_at);
CREATE TABLE IF NOT EXISTS chunks (
 id uuid PRIMARY KEY, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES workspaces(id), text text NOT NULL, page integer NOT NULL,
 ordinal integer NOT NULL, embedding vector(1536) NOT NULL,
 UNIQUE(document_id,ordinal)
);
CREATE INDEX IF NOT EXISTS chunks_workspace ON chunks(workspace_id);
-- Exact tenant-filtered search initially. Add HNSW only after tenant recall benchmarks.
CREATE TABLE IF NOT EXISTS questions (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
 question text NOT NULL, result jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS questions_workspace ON questions(workspace_id,created_at DESC);
