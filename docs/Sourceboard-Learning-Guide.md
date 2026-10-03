# SOURCEBOARD
## How the project is built

A beginner-to-developer handbook for the Production RAG Knowledge Base SaaS project

Code snapshot: September 12, 2026 | Application version: 0.2.0

Verification update: September 13, 2026. The complete live Gemini HTTP workflow passed; see sections 13.5 and 17.4.

This guide explains the application in this workspace. It is a teaching reconstruction of how to build the current system, not a claim about the exact order in which every original file was written. All examples use sample content and placeholder credentials. The real API key is intentionally excluded.

Read this with the project open in your IDE. Start with the concepts, follow one document through the system, and then study individual files. The code is the authority when it changes after this snapshot.

## Contents

1. What you are building and how to learn it
2. The technologies and why each exists
3. Architecture: the complete request journey
4. The project folder and file map
5. Prepare the development environment
6. Configuration: every setting explained
7. Database design and migrations
8. Authentication and workspace isolation
9. The backend API, route by route
10. Uploads, storage, extraction, and chunking
11. Background jobs, leases, retries, and deletion
12. Embeddings, retrieval, answers, and evidence
13. Gemini integration and the fixes we made
14. The frontend and its connection to the API
15. Docker images, networking, and startup
16. Rebuild the application in learning stages
17. Tests and what they actually prove
18. Run, inspect, and troubleshoot the project
19. Security, limitations, and production planning
20. Practical learning exercises and answers
21. Glossary, dependency reference, and further reading

# 1. What you are building and how to learn it

## 1.1 The problem

A company has policies, manuals, and other documents scattered across files. A person wants to ask a question such as, "How many days can I work remotely?" Sourceboard lets that person upload documents, ask questions, and inspect the passages used to support an answer.

The app stores original files, extracts their text, breaks it into passages, converts those passages into numerical representations, searches the representations, and asks a language model to answer from the selected passages. It also checks citations before showing an answer.

The name RAG means retrieval-augmented generation. Retrieval finds relevant source text. Augmentation adds that text to the model's input. Generation produces an answer using that input. Uploading a document does not train or fine-tune Gemini: it creates searchable application data.

## 1.2 What exists now

- Account creation and sign-in with a private workspace per account.
- PDF, TXT, Markdown, and CSV uploads with background processing.
- Semantic search over stored document passages using pgvector.
- Model-generated answers with claim-level citations and verbatim quotes.
- A source inspector, original-file download, document retry, and deletion.
- Saved question history, containerized services, and automated tests.
- A verified Gemini configuration for embeddings and structured answers.

The term SaaS describes the product direction. Shared team memberships, invitations, roles, subscriptions, and payments are not implemented. A label such as "Workspace owner" in the interface does not establish a complete permissions system.

## 1.3 A useful learning order

First learn the visible workflow: register, upload, wait, ask, inspect. Next learn HTTP and JSON, then the database tables. Follow the upload path before the answer path. Study worker concurrency only after the basic flow is clear. Finally study Docker, tests, failure handling, and production gaps.

You do not need to memorize every dependency. You should be able to answer four questions about each module: What input does it receive? What work does it perform? What output or side effect does it produce? What can fail?

## 1.4 The running example

Use this fictional policy throughout the guide:

```text
Employees may work remotely three days per week.
Manager approval is required.
```

A supported question is "How many days per week may employees work remotely?" An unsupported question is "What is the annual travel allowance?" The first has evidence in the policy. The second should result in insufficient evidence, rather than an invented allowance.

# 2. The technologies and why each exists

## 2.1 Languages, frameworks, and services

| Technology | Role in this project | Why it is used |
| --- | --- | --- |
| Python | Backend, worker, extraction, migrations, tests | Provides web, database, PDF, storage, and HTTP libraries. |
| TypeScript | Frontend application and server proxy | Adds static type checks to JavaScript code. |
| HTML through JSX | Structure of forms, panels, tables, dialogs | React turns component markup into browser elements. |
| CSS | Colors, layout, responsive rules, states | The interface uses custom CSS rather than Tailwind. |
| SQL | Schema, transactions, jobs, vector queries | Makes persistence and concurrency behavior explicit. |
| YAML | Docker Compose configuration | Describes services, ports, dependencies, and volumes. |
| React | Browser interface and state management | Renders the page when user and application state change. |
| Next.js | React framework and same-origin API proxy | Builds the frontend and runs server-side route handlers. |
| FastAPI | Backend HTTP API | Routes requests, validates models, and generates API documentation. |
| Uvicorn | Python ASGI server | Runs the FastAPI application and accepts HTTP connections. |
| PostgreSQL 17 | Persistent relational database | Stores accounts, jobs, passages, vectors, and history. |
| pgvector | PostgreSQL extension | Adds vector storage and cosine-distance operations. |
| MinIO | S3-compatible object storage | Stores original uploaded files separately from database rows. |
| Gemini API | Embeddings, answers, evidence review | Supplies the external AI capabilities. |
| Docker Compose | Local service orchestration | Starts the cooperating containers with a shared network. |
| pytest | Python test runner | Checks validation, API behavior, retrieval, and integration flows. |

## 2.2 Three different kinds of storage

The browser holds temporary interface state: the current view, typed question, displayed answer, and selected citation. PostgreSQL holds durable structured data, including passages and their vectors. MinIO holds original file bytes. These are different responsibilities and should not be confused.

An embedding is stored in PostgreSQL, not in Gemini's memory for your app. The original PDF is stored in MinIO, not inside the frontend. React state is not a database; refreshing the page discards temporary state and the app fetches persistent information again.

## 2.3 Tools deliberately not used

The active implementation does not use Streamlit, Django, Flask, Redis, Celery, Qdrant, Pinecone, a SQL ORM, LangChain, LlamaIndex, or LangGraph. The backend uses direct SQL and direct HTTP calls. The queue is implemented with PostgreSQL rows. React hooks handle frontend state without Redux. These choices keep the control flow visible for learning.

The archived prototype under `legacy/` used SQLite FTS5 and lexical retrieval. It is a different application. Do not combine its startup instructions or 200-word chunking rules with the active backend's 1500-character chunking.

# 3. Architecture: the complete request journey

## 3.1 The system at a glance

```text
Browser at localhost:3000
        |
        v
Next.js website + /api proxy
        |
        v
FastAPI -----> PostgreSQL + pgvector
   |                 ^
   v                 |
MinIO <---------- Python worker
                     |
                     v
                Gemini embeddings

FastAPI also calls Gemini for question embeddings,
answer generation, and evidence review.
```

Next.js does not perform the semantic search. FastAPI does not continuously poll the ingestion queue. MinIO does not extract text. Gemini does not enforce workspace authorization. Each layer has a limited responsibility, and correctness depends on the connections between them.

## 3.2 Upload journey

The browser creates a multipart request containing the file. The Next.js proxy forwards it to FastAPI with the session cookie and request-protection header. FastAPI authenticates the user, validates the upload, writes its original bytes to MinIO, and inserts a queued document row into PostgreSQL. It returns HTTP 202, meaning the file was accepted for processing.

The worker later claims the row, reads the original file, extracts text, produces passages, requests embeddings, and publishes the passages and ready status in one database transaction. The browser polls the documents endpoint every four seconds to show progress.

## 3.3 Question journey

The browser posts JSON containing the question. FastAPI identifies the workspace from the session, verifies that compatible ready documents exist, and embeds the question. PostgreSQL ranks that workspace's passages by vector distance. The backend filters candidates by the configured similarity threshold and sends the remaining passages to Gemini.

Gemini returns structured claims and quoted evidence. The server validates the structure, source IDs, and exact quotes. A second model request checks support. The API rechecks source availability before recording the result in question history. Finally the browser renders the claims and citation buttons.

## 3.4 What leaves your computer

In the current Gemini configuration, passages go to Google for embedding. Questions go to Google for embedding. Retrieved passages and questions go to Google for answer generation. Draft claims and their quotes go to Google for evidence review. The app itself stores originals in local MinIO volumes, but it is not an entirely offline AI system.

Google documents free-tier availability and data-use terms on its pricing page. Free-tier quotas and account eligibility can change. The project does not inspect your billing plan or enforce a Google spending limit. Use sample documents while learning.

# 4. The project folder and file map

## 4.1 Root files and generated folders

| Path | What it contains or controls |
| --- | --- |
| README.md | Architecture, installation commands, tests, Gemini setup, and deployment limits. |
| VALIDATION.md | Dated observations about builds, test results, and checks not yet performed. |
| .env | Local secrets and configuration read by Python and supplied to backend containers. |
| .env.example | Copyable configuration examples without the real provider key. |
| compose.yaml | The running application's database, storage, migration, API, worker, and web services. |
| compose.test.yaml | Separate disposable infrastructure for automated integration tests. |
| requirements.txt | Forwards Python installation to backend/requirements.txt. |
| server.py | Compatibility entry point that starts FastAPI locally on port 8000. |
| .gitignore | Excludes secrets, generated files, environments, and local data from Git tracking. |
| .dockerignore | Excludes secrets and unnecessary folders from the backend build context. |
| .venv/ | Local Python interpreter environment and installed packages; generated, not application source. |
| frontend/node_modules/ | Installed JavaScript packages; generated by npm. |
| frontend/.next/ | Next.js generated development or production output. |
| data/ | Local data and test artifacts; not the active Compose named-volume storage location. |
| .npm-cache/ | Local npm download cache; not business logic. |
| legacy/ | Archived SQLite/extractive prototype. |
| infra/ | No active deployment files were present in the inspected folder. |
| docs/ | This learning guide and its document-generation materials. |

The workspace was not a Git repository when inspected earlier in this session. A `.gitignore` file alone does not initialize Git or provide version history. When you begin version control, verify that `.env` remains untracked before committing.

## 4.2 Every backend module

| File | Main responsibility |
| --- | --- |
| backend/app/__init__.py | Marks the application directory as a Python package. |
| backend/app/config.py | Defines typed settings and caches their loaded values. |
| backend/app/db.py | Opens PostgreSQL connections and supplies transaction scopes. |
| backend/app/storage.py | Creates the cached S3 client used for MinIO operations. |
| backend/app/migrate.py | Applies new SQL migrations and ensures the object bucket exists. |
| backend/app/auth.py | Password hashing, password checks, and authenticated-user lookup. |
| backend/app/main.py | FastAPI routes, input models, sessions, middleware, and error responses. |
| backend/app/extraction.py | File-format validation, text extraction, and passage creation. |
| backend/app/worker.py | Job claiming, leases, processing, publication, retry, and storage cleanup. |
| backend/app/provider.py | Provider HTTP calls, embedding validation, answer schema, and model review. |
| backend/app/rag.py | Tenant-filtered retrieval and server-side evidence validation. |
| backend/migrations/001_initial.sql | Initial schema, constraints, indexes, and vector extension. |
| backend/requirements.txt | Direct Python dependency ranges with a constraints-file reference. |
| backend/constraints.txt | Captured versions constraining dependency resolution. |
| backend/Dockerfile | Python image, dependency installation, source copy, and server command. |
| backend/pytest.ini | Test discovery, Python import path, integration marker, cache settings. |
| backend/tests/test_grounding.py | Citation, schema, extraction, embedding, and provider-response checks. |
| backend/tests/test_http.py | HTTP protection, validation, and unauthenticated route checks. |
| backend/tests/test_rag_pipeline.py | Empty-workspace behavior and rejection of unsupported claims. |
| backend/tests/test_integration.py | Real database/storage upload, retrieval, isolation, deletion, and fencing. |

## 4.3 Every frontend source and configuration file

| File | Main responsibility |
| --- | --- |
| frontend/app/page.tsx | The client component implementing authentication, questions, library, history, and citations. |
| frontend/app/layout.tsx | Shared HTML shell, English document language, metadata, and global stylesheet import. |
| frontend/app/globals.css | Design tokens, panels, forms, responsive layouts, and document status styles. |
| frontend/app/api/[...path]/route.ts | Server-side catch-all proxy for GET, POST, and DELETE API requests. |
| frontend/next.config.ts | Standalone build output and browser-facing response headers. |
| frontend/tsconfig.json | Strict TypeScript configuration and Next.js-generated type includes. |
| frontend/next-env.d.ts | Generated Next.js TypeScript declarations. |
| frontend/package.json | npm commands and direct frontend dependencies. |
| frontend/package-lock.json | Exact resolved package versions used by npm ci. |
| frontend/scripts/start.mjs | Copies static assets into standalone output and starts it locally. |
| frontend/Dockerfile | Separate dependency, build, and runtime stages for the web image. |
| frontend/.dockerignore | Keeps local dependencies, build output, and other exclusions out of the frontend context. |

# 5. Prepare the development environment

## 5.1 Understand the two ways to run

The Docker route runs the services in containers and is the simplest route for this workspace. It requires Docker Desktop with a working Linux engine. On this Windows machine, WSL and Windows virtualization features were required; Docker only became available after the machine setup was completed.

The local-development route runs Python and Node directly while PostgreSQL and MinIO run in Docker. It is useful for rapid code editing with reload. Do not run both API servers on port 8000 or both web servers on port 3000 at the same time.

## 5.2 Check Docker before debugging the application

```powershell
docker version
docker compose version
docker info
```

`docker info` must show an accessible server. A working Docker command-line executable does not necessarily mean the engine is running. A missing Docker engine pipe means the daemon is unavailable; it is not a Python or React failure.

## 5.3 Open the project

```powershell
cd "C:\Users\Rashid Ali Soomro\Desktop\Production RAG Knowledge Base SaaS"
```

Use the IDE explorer to open `backend/app/main.py`, `backend/app/worker.py`, and `frontend/app/page.tsx`. These three files show the main responsibilities. Keep `.env` private. Do not copy its real contents into screenshots, chat, or a public repository.

## 5.4 Local Python and Node setup

The container targets Python 3.12 and Node 22. Earlier local validation also used Python 3.14. Prefer the container target versions when reproducing a build outside Docker.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
npm --prefix frontend ci
```

`venv` isolates Python packages from other projects. `pip` installs Python packages. `npm ci` installs the JavaScript dependencies from the lockfile. Installing dependencies is different from starting the application.

# 6. Configuration: every setting explained

## 6.1 How settings reach the code

`Settings` in `backend/app/config.py` inherits from Pydantic's `BaseSettings`. It reads environment variables and the root `.env` file when the command starts from the project root. Unknown dotenv entries are ignored. The `settings()` function uses `lru_cache`, so the settings object is reused in a running process.

Compose loads the root `.env` for variable substitution. The backend services also receive it through `env_file`. Compose explicitly overrides the database and storage addresses to service names that work inside the container network. Environment configuration is not baked into the source code or frontend bundle.

## 6.2 Configuration reference

| Setting | Meaning and current usage |
| --- | --- |
| MODEL_API_KEY | Private provider credential. Passed in the backend Authorization header. Never shown here. |
| MODEL_BASE_URL | Provider API root. Gemini uses https://generativelanguage.googleapis.com/v1beta/openai. |
| EMBEDDING_MODEL | Current Gemini model: gemini-embedding-2. The database schema still requires 1536 dimensions. |
| CHAT_MODEL | Current answer/review model: gemini-3.5-flash-lite. |
| MIN_SIMILARITY | Retrieval cutoff, default 0.40. A heuristic, not a factual-confidence percentage. |
| DATABASE_URL | PostgreSQL connection string. Local default targets localhost:5432; Compose overrides host to postgres. |
| POSTGRES_PASSWORD | Compose variable used to configure PostgreSQL and construct backend connection strings. |
| APP_ORIGIN | Browser origin accepted for mutations. Current value: http://localhost:3000. |
| COOKIE_SECURE | Whether session cookies require HTTPS. False for local HTTP; true when serving over HTTPS. |
| S3_ENDPOINT | Object storage endpoint. Local: http://localhost:9000. Container: http://minio:9000. |
| S3_ACCESS_KEY | Storage access identity. Compose uses it as the local MinIO root username. |
| S3_SECRET_KEY | Storage secret. Compose uses it as the local MinIO root password. |
| S3_BUCKET | Bucket holding original files; default sourceboard. |
| S3_REGION | Region used for request signing/bucket creation; default us-east-1. |
| UPLOAD_LIMIT | Optional backend setting in bytes; default 10 * 1024 * 1024. UI/proxy limits must stay consistent if changed. |
| WORKER_POLL_SECONDS | Optional backend setting; default 3 seconds between empty-queue checks. |
| API_INTERNAL_URL | Next.js server-only upstream URL. Compose uses http://api:8000; local default is http://127.0.0.1:8000. |
| TEST_DATABASE_URL | Explicit opt-in connection string for integration tests. Use only disposable test infrastructure. |
| NODE_ENV | Runtime web container uses production. |
| HOSTNAME / PORT | Web server binding. Docker uses 0.0.0.0 and port 3000; local startup binds 127.0.0.1. |
| NEXT_TELEMETRY_DISABLED | Set to 1 during the frontend Docker build. |

Do not increase `UPLOAD_LIMIT` in isolation. The browser currently rejects files above 10 MB, the proxy allows an 11 MB multipart body, and several messages and worker checks assume the documented limits.

## 6.3 Gemini configuration example

```dotenv
MODEL_API_KEY=YOUR_PRIVATE_GOOGLE_AI_STUDIO_KEY
MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
EMBEDDING_MODEL=gemini-embedding-2
CHAT_MODEL=gemini-3.5-flash-lite
MIN_SIMILARITY=0.40
```

This example is not a usable credential. Your existing `.env` is already configured. Do not overwrite it with `.env.example` unless you intend to replace your saved settings. Changing a provider key alone is insufficient when the API endpoint and model names belong to a different provider.

After changes, run `docker compose up -d` to apply changed container configuration. Use `docker compose up --build -d` when source code or Docker build inputs also changed. A simple `docker compose restart` does not recreate a container with newly supplied environment values.

# 7. Database design and migrations

## 7.1 Relational concepts in this schema

A table groups records of the same kind. A primary key identifies one row. A foreign key connects a row to a parent row. A unique constraint prevents duplicate values. An index helps selected queries locate rows. A transaction groups changes so they commit together or roll back together.

Most application identifiers are UUIDs generated by Python. Timestamps use `timestamptz`. Answer results use `jsonb`, which stores JSON in PostgreSQL. Embeddings use `vector(1536)`, supplied by the pgvector extension.

## 7.2 All tables and columns

| Table | Columns and meaning |
| --- | --- |
| schema_migrations | name: applied SQL filename; applied_at: application timestamp. Created by the migration runner. |
| workspaces | id: UUID; name: up to 80 characters; created_at: creation time. |
| users | id; workspace_id foreign key; unique email up to 254 characters; password_hash; salt; created_at. |
| sessions | token_hash primary key; user_id foreign key; expires_at. User deletion cascades to sessions. |
| documents | id; workspace_id; name; unique object_key; size; status; pages; chunk_count; error; attempts; available_at; lease_until; lease_token; embedding_model; created_at. |
| chunks | id; document_id; workspace_id; text; page; ordinal; embedding. A document/ordinal pair is unique. Deleting a document cascades to chunks. |
| questions | id; workspace_id; question; result as JSONB; created_at. |

The `documents` table is both a file metadata table and the durable job queue. `available_at` controls when a job is eligible. `lease_until` controls when its ownership expires. `lease_token` distinguishes one processing attempt from another. `embedding_model` identifies which embedding space produced its vectors.

`chunks.workspace_id` duplicates tenant ownership for direct filtering. The application inserts consistent workspace values, but the schema does not define a composite foreign key guaranteeing that every chunk's workspace matches its document's workspace. Retrieval checks both document and chunk workspace IDs. This is application-level tenant enforcement, not PostgreSQL row-level security.

## 7.3 Relationships

```text
workspaces 1 ---- many users
users      1 ---- many sessions
workspaces 1 ---- many documents
documents  1 ---- many chunks
workspaces 1 ---- many questions
```

The schema permits several users to reference one workspace, but the registration route always creates a new workspace for a new account. A schema capability is not the same as an implemented invitation or membership feature.

## 7.4 Indexes and constraints

There are indexes for document workspace lookup, queue status/availability, chunk workspace lookup, and recent workspace questions. Primary keys and unique constraints also create supporting indexes. Document status is restricted to queued, processing, ready, failed, or deleting by a CHECK constraint.

There is no HNSW vector index. The current retrieval query uses exact cosine-distance ordering over eligible rows. This is straightforward and avoids approximate-recall tuning at the current stage, but cost can grow as the number of passages grows.

## 7.5 How migrations work

`migrate.main()` acquires a PostgreSQL transaction-level advisory lock with ID 734192. It creates the migration bookkeeping table if necessary, scans SQL files in sorted filename order, runs unapplied files, and records each filename. The transaction lock prevents simultaneous migration processes from applying the same migration concurrently.

After the database transaction completes, it checks the object bucket. If the storage service reports that the bucket does not exist, it creates the bucket. Permission errors are not treated as permission to create a different bucket.

For future schema changes, add a new migration such as `002_document_tags.sql`. Editing an already-applied `001_initial.sql` does not cause it to rerun. The runner tracks filenames, not file-content checksums. Keep old migrations stable once used.

## 7.6 Connection and transaction behavior

`database()` opens a psycopg connection with dictionary-shaped result rows and a five-second connection timeout. A clean context exit commits. An exception rolls back. There is no connection pool in this implementation; repeated operations open new connections. Pooling is a future performance option, not a current feature.

# 8. Authentication and workspace isolation

## 8.1 Registration

The registration request contains email, password, and workspace name. Pydantic enforces a 3-254-character email with a simple email pattern, a 10-128-character password, and a 1-80-character workspace name. The email is lowercased before insertion. These checks do not verify ownership of the email address.

The API generates user and workspace UUIDs plus a random 16-byte salt represented as hexadecimal. `hash_password()` uses scrypt with n=16384, r=8, and p=1. The hash and salt are stored; the original password is not. A uniqueness failure rolls back registration and returns HTTP 409.

## 8.2 Sign-in and sessions

`check_password()` hashes the supplied password with the stored salt and compares the result using `hmac.compare_digest`. If no account exists, the route still performs a dummy password check. Invalid credentials return a generic error rather than revealing which field was wrong.

On successful authentication, the server creates a random opaque token with `secrets.token_urlsafe(32)`. The raw token is placed in the session cookie. Only its SHA-256 hash is stored in PostgreSQL. The database row expires after seven days, and the cookie maximum age is 604800 seconds.

The cookie is HttpOnly, which prevents ordinary frontend JavaScript from reading it. SameSite is strict. Secure is controlled by `COOKIE_SECURE`. Logout removes the current session row and clears the cookie; it does not implement a logout-all-devices feature.

## 8.3 Authentication on protected routes

The `User` annotation combines a dictionary result with `Depends(current_user)`. Before a protected route runs, `current_user()` reads the cookie, hashes its token, finds a nonexpired session, joins the user and workspace, and returns the authenticated identity. Missing or expired sessions produce HTTP 401.

Protected routes obtain `workspace_id` from that authenticated result. A browser does not get to choose an arbitrary workspace ID in the upload or ask body. SQL queries use `%s` parameter placeholders to pass values separately from SQL text.

## 8.4 Request protection

For mutation methods, the middleware rejects a supplied Origin header that differs from `APP_ORIGIN` and requires `X-Sourceboard: 1`. The frontend helper supplies this header. These protections complement the cookie settings; they are not an alternative to authentication or a full abuse-prevention system.

Using `http://127.0.0.1:3000` while `APP_ORIGIN` is `http://localhost:3000` can produce an origin rejection. The two addresses may reach the same machine, but they are different browser origins. Use the documented localhost URL consistently.

# 9. The backend API, route by route

## 9.1 API reference

| Method and route | Input, result, and purpose |
| --- | --- |
| GET /health/live | Public. Returns status=ok if the route can execute. |
| GET /health/ready | Public. Checks migration-table access and the storage bucket. Does not validate model credentials. |
| POST /api/register | Email, password, workspace JSON. Creates workspace/user/session. Returns 201 and ok=true. |
| POST /api/login | Email/password JSON. Creates a session on successful authentication. |
| POST /api/logout | Authenticated. Deletes the current session and cookie. |
| GET /api/me | Authenticated user/workspace information and provider_configured boolean. |
| GET /api/documents | Authenticated. Lists current workspace document metadata, newest first. |
| POST /api/documents | Multipart field named file. Saves original and queues ingestion; returns 202 with document ID. |
| POST /api/documents/{id}/retry | Authenticated. Requeues a failed document in the same workspace. |
| DELETE /api/documents/{id} | Authenticated. Removes passages/history immediately and queues original deletion; returns 202. |
| GET /api/documents/{id}/download | Authenticated. Streams the original file if the document belongs to the workspace and is not deleting. |
| GET /api/history | Authenticated. Returns at most 30 latest saved questions/results. |
| POST /api/ask | Question JSON, 3-2000 characters. Retrieves, generates, validates, saves, and returns a result. |

Interactive API documentation is available at `http://localhost:8000/docs`. A direct request from API documentation still has to satisfy authentication and the mutation-protection header; merely opening the documentation does not bypass those requirements.

## 9.2 Status codes are part of the contract

HTTP 200 means success for a completed operation. 201 means an account was created. 202 means work was accepted but is still asynchronous. 400 indicates certain invalid inputs. 401 means missing/invalid authentication. 403 indicates request protection failure. 404 hides missing or inaccessible documents. 409 indicates an account conflict. 413 means the body is too large. Pydantic validation can return 422. Provider or database availability failures return 503.

Insufficient evidence is usually a successful HTTP response containing an application status such as `insufficient_evidence`. It differs from a provider outage. The first means the app cannot support an answer from available sources; the second means a required service failed.

## 9.3 Health is narrower than readiness to answer

`provider_configured` is only `bool(settings().model_api_key)`. It does not prove the key is correct, funded, permitted to access a model, or below quota. Likewise, a ready API health check proves database and bucket access, not successful model inference. This distinction explains why a website can work while uploads fail during embedding.

## 9.4 Error and response handling

The API translates `ProviderError` into a 503 response with `status: provider_unavailable`. PostgreSQL operational failures also receive a generic 503. The middleware adds `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. Some storage errors are handled directly within routes with clear messages.

# 10. Uploads, storage, extraction, and chunking

## 10.1 Accepting a file

The browser places each selected file into `FormData` under the name `file`. It sends selected files sequentially. The API strips directory components from the filename, truncates it to 200 characters, and checks its suffix against `.pdf`, `.txt`, `.md`, and `.csv`.

The API reads no more than upload_limit + 1 bytes. The extra byte lets it detect an oversized file without accepting unlimited data. Empty files and unsupported extensions are rejected. A filename extension alone is not a malware scan or a guarantee of valid content; PDF parsing happens later in the worker.

## 10.2 Saving the original

An object key has the form `workspace UUID/document UUID/original`. It does not use the original filename as the storage location. The API stores bytes as `application/octet-stream`, then inserts document metadata with the default queued status.

If the row insertion fails after object upload, the code attempts to delete the newly written object. This is compensating cleanup, not a distributed transaction. A process crash or cleanup failure can still leave an orphaned object, which is why reconciliation remains a production task.

`storage.py` uses boto3 with S3 version-4 signing, path-style addressing, a five-second connection timeout, a 30-second read timeout, and a retry configuration with max_attempts=3. The client is cached for the process lifetime.

## 10.3 Extracting readable text

For a PDF, `PdfReader(BytesIO(content))` opens the uploaded bytes. Encrypted PDFs are rejected. PDFs are limited to 300 physical pages. The extractor walks each page and calls `extract_text()`, keeping page boundaries. It enforces a two-million-character extracted-text limit.

For TXT, Markdown, and CSV, the code decodes UTF-8 with optional BOM handling using `utf-8-sig`. All content is treated as text on page 1. CSV is not interpreted as a structured spreadsheet, and Markdown is not converted into semantic sections. Scanned PDFs containing no readable text require OCR outside this project.

## 10.4 Chunking with a concrete example

`chunk_pages()` normalizes whitespace within each page using `' '.join(text.split())`. It takes windows up to 1500 characters long with a stride of 1200. Adjacent full windows therefore overlap by 300 characters. The unit is characters, not words or model tokens.

```text
Normalized page text, 2800 characters:
chunk 0: characters    0 through 1499
chunk 1: characters 1200 through 2699
chunk 2: characters 2400 through 2799

Each chunk has: page, text, global ordinal.
The next PDF page starts a new set of windows.
```

Overlap helps preserve context around a boundary, but this simple algorithm can split sentences and does not understand headings or tables. It never merges two PDF pages into one passage. A citation's quote is checked against normalized indexed text; it may not have the original PDF's exact spacing or line breaks.

## 10.5 Downloading and viewing sources

The download route verifies ownership, reads the object, and streams it in 64 KiB chunks. Its generator closes the storage response body even when streaming ends. The attachment filename is URL-quoted for Content-Disposition.

The citation dialog shows an indexed passage with a page number and a link to download the original. It is not an embedded PDF renderer and does not automatically highlight text on the original PDF page.

# 11. Background jobs, leases, retries, and deletion

## 11.1 Why the worker is separate

Parsing a large document and calling an embedding API can take far longer than accepting an upload. Performing everything inside the upload request would keep the browser waiting and make recovery harder. The separate worker lets the API return quickly while PostgreSQL records durable work to do.

## 11.2 State transitions

```text
upload -> queued -> processing -> ready
                     |
                     +-> queued (retryable, attempts remain)
                     +-> failed (permanent or attempts exhausted)

failed -- user Retry --> queued
any owned document -- Delete --> deleting --> row removed
```

Deletion retries remain in deleting when storage is unavailable. They do not use the same three-attempt stopping rule as ingestion. Old processing jobs with expired leases are reclaimable, but repeatedly abandoned jobs eventually become failed.

## 11.3 Claiming a job safely

`claim()` first marks exhausted, expired processing jobs as failed. It then selects an eligible queued/deleting row, or an expired processing row, prioritizing deletions. `FOR UPDATE SKIP LOCKED LIMIT 1` means another worker can skip a row already being claimed instead of processing the same claim concurrently.

Within that transaction, the worker increments attempts, writes a fresh UUID lease token, sets a 15-minute lease, and changes ingestion jobs to processing. This establishes ownership for the attempt. Multiple worker processes can coordinate through these rows, though the current Compose setup starts one worker service instance.

## 11.4 Heartbeats and publication

Before each embedding batch of up to 24 passages, `heartbeat()` extends the lease only if the document is still processing with the same token. Heartbeats are not a separate continuous thread. Very long parsing or provider calls still depend on the lease design and timeout behavior.

The worker collects all vectors, then locks the document row again. It verifies the status and lease token, replaces existing chunks, inserts passage/vector pairs, and sets pages, chunk_count, embedding_model, and ready status. These final database changes commit atomically. `zip(..., strict=True)` prevents silently pairing unequal numbers of chunks and vectors.

## 11.5 Fencing: preventing a stale worker from publishing

Imagine worker A begins embedding. The user deletes the document, which invalidates A's token and changes the status. A finishes its remote request afterward. Without a final ownership check, A could recreate searchable passages for a deleted source. The token/status check prevents that publication.

Lease expiration also allows worker B to reclaim a job with a new token. When A eventually resumes, its old token no longer authorizes publication. The token acts as an attempt identity; expiration alone is not enough to enforce this property.

## 11.6 Retry behavior

`fail()` treats `ValueError` as permanent input/extraction failure. Other ingestion failures are requeued unless the third attempt has been reached. Retryable jobs become available again after 30 seconds. The browser Retry action resets a failed document's attempts to zero and clears the error and lease.

Logs include job IDs and exception type names, not document text, credentials, or raw model responses. There is no dead-letter dashboard, scheduled reconciliation service, or full general-purpose task platform.

## 11.7 Deletion and concurrent questions

The delete route locks the workspace, sets deleting, invalidates the worker lease, deletes chunks, and clears all saved question history for that workspace. Search removal is immediate on commit. Original storage deletion happens later in the worker.

The ask route also locks the workspace just before saving history and rechecks that cited chunks still exist in ready documents. If sources disappeared while Gemini was generating, the result becomes `sources_changed`. This reduces the chance of saving an answer that relies on a source concurrently deleted from the app. It cannot erase an answer already seen or downloaded by a user.

# 12. Embeddings, retrieval, answers, and evidence

## 12.1 What an embedding means

An embedding is a list of numbers generated from text by a model. In this app it must contain 1536 finite numbers and must not be the all-zero vector. Similar meanings often map to nearby directions in that model's vector space, allowing search by meaning rather than exact word overlap.

These numbers are not encrypted document text, a compressed original file, or a confidence score. The same dimensions from two different embedding models are not automatically comparable. That is why ready documents are filtered by their recorded embedding_model.

## 12.2 Embedding-response validation

The provider sends model, input texts, dimensions=1536, and encoding_format=float. It sorts returned records by index, checks that indexes exactly match the input positions, checks vector lengths, and rejects nonfinite or zero vectors. This protects against storing malformed provider output.

For Google's hostname only, an omitted index is interpreted as zero. Duplicate zero indexes still fail validation. The compatibility fix does not simply trust response order or silently accept missing batch entries.

## 12.3 Retrieval step by step

The RAG function first counts ready documents in the authenticated workspace that match the configured embedding model. If none exist, it abstains before making any model request. Otherwise it embeds the question and queries PostgreSQL.

```sql
-- Conceptual shape; real code uses parameterized values.
SELECT passage, 1 - cosine_distance AS similarity
FROM eligible_workspace_passages
ORDER BY cosine_distance
LIMIT 6;
```

The actual pgvector cosine-distance operator is `<=>`. Similarity is calculated as `1 - distance`. The query filters both document and chunk workspace IDs, requires ready documents, and matches the embedding model. After retrieving up to six rows, Python keeps only those with similarity at least `MIN_SIMILARITY`.

The threshold 0.40 is not "40 percent correct." A highly similar passage can still fail to answer the question. A relevant answer may also fall below a poorly calibrated threshold. This implementation has no reranker, keyword/vector hybrid retrieval, metadata filters in the UI, or automatic query expansion.

## 12.4 Structured answer generation

The system message instructs the model to use only supplied passages and treat their contents as untrusted data. The user message contains the question and source IDs/text serialized as JSON. The response format requests a strict JSON schema with `answerable` and `claims`.

```json
{
  "answerable": true,
  "claims": [{
    "text": "Employees may work remotely three days per week.",
    "evidence": [{
      "source_id": "a-retrieved-chunk-id",
      "quote": "Employees may work remotely three days per week."
    }]
  }]
}
```

This is an illustrative response, not a real persisted source identifier. Structured output makes the result machine-checkable. It does not make the model factually correct by itself.

## 12.5 Server-side validation

Pydantic models in `rag.py` forbid unexpected fields and use strict types. There may be up to ten claims. Each claim has text up to 2000 characters and one to six evidence entries. Each quote must be 12-1500 characters long. A true answerable flag with no claims still results in abstention.

Every cited source ID must belong to the retrieved source collection. Every quote must appear as an exact substring of that source's indexed text. Unknown IDs and invented quotes return `invalid_evidence`. Valid claims are joined with blank lines to form the answer, and only cited source objects are returned.

## 12.6 Evidence review and final result

The second model request asks whether every claim is supported by its quotes and answers the question without unsupported inference. It requests a supported boolean. A false or unusable review causes `unsupported_claims`. A provider HTTP failure remains a service error rather than being relabeled as lack of evidence.

`provider.generate()` rejects incomplete or refused responses when finish_reason is not stop or a refusal is present. JSON parsing and response-shape failures are also handled. Generation uses max_completion_tokens=1800; review uses 300. These are response budgets, not guarantees that every model can finish every answer within them.

An ordinary successful question with usable documents can make three provider calls: one question embedding, one answer generation, and one review. Uploads make embedding calls in worker batches. Empty workspaces can abstain with zero provider calls.

## 12.7 Why the safeguards are not a proof of truth

A quote can be real while its interpretation is wrong. Two model calls can share the same mistake. A source can be outdated, malicious, incomplete, or contradictory. Prompt instructions and quote checks reduce failure modes but do not eliminate prompt injection or prove entailment. Users should inspect citations, and production evaluation should measure retrieval and answer behavior on representative questions.

# 13. Gemini integration and the fixes we made

## 13.1 The provider adapter

The project uses httpx directly rather than a Gemini SDK. It sends requests to Google's OpenAI-compatible endpoint with a bearer credential. A single adapter supplies `/embeddings` and `/chat/completions`, so the rest of the app can keep using its own provider functions.

The HTTP client uses a 90-second timeout configuration with a 10-second connection timeout. Error messages deliberately omit secrets and raw provider responses. This timeout is not a guarantee that an entire multi-call answer will always complete within 90 seconds.

## 13.2 A listed model can still be unavailable

The saved key successfully authenticated with Google's model-list endpoint. However, `gemini-2.5-flash-lite` returned HTTP 404 for this account, explaining that it was no longer available to new users and recommending `gemini-3.5-flash-lite`. The configuration was changed to that model and a real structured-answer check succeeded.

This is an example of why a model-list check alone is insufficient. Provider availability is account- and time-dependent. When a model stops working, inspect the actual error safely, consult current provider documentation, and verify the replacement with representative request shapes.

## 13.3 The omitted embedding index

The first embedding record from Google contained a 1536-dimensional vector but omitted the index field. In a two-input check, the second record had index 1. The original strict validator expected an explicit zero and rejected the response.

The change restores the omitted default zero only for the Google API hostname, then applies the original sorting and sequence checks. The regression test uses an out-of-order response with index 1 followed by an omitted zero, and also confirms that two omitted indexes are rejected. This protects correct text-to-vector pairing.

## 13.4 What was verified

Direct provider checks returned two separate 1536-dimensional vectors, a valid cited answer for synthetic policy text, and a true evidence-review result. The website and API readiness checks passed after rebuilding and restarting the app.

Google's native Embedding 2 API documents aggregation behavior for multiple inputs, while the compatibility endpoint used here returned separate vectors for the tested two-string input. Do not assume those two interfaces behave identically. The adapter validates response count/indexes, and larger-document live-provider behavior still deserves testing.

The complete live-Gemini upload-to-answer HTTP flow subsequently passed on September 13, 2026, as detailed below. The automated database/storage integration tests still use deterministic fake model responses; the live check is separate evidence. Remaining free quota and the account's billing tier were not inspected.

## 13.5 Complete live workflow: what we did and learned

On September 13, 2026, a separate test account and workspace were created through the Next.js proxy at `http://localhost:3000`. Requests used the normal session cookie, Origin header, and `X-Sourceboard: 1` protection header. The test used the running API, real PostgreSQL/pgvector and MinIO, the actual background worker, and live Gemini calls. No model responses were mocked.

1. Register an isolated account. This keeps the sample policy separate from existing user documents and history.
2. Upload `policy.txt` containing the two sentences from section 1.4. The upload was accepted, and the worker produced a ready document on its first attempt: one page and one indexed chunk. This connects original-file storage, extraction, embedding, and database publication in one real workflow.
3. Ask, "How many days per week may employees work remotely?" The application returned `answered` with: "Employees may work remotely three days per week."
4. Verify the returned citation. Its source belonged to the uploaded document, and the quote "Employees may work remotely three days per week." appeared exactly in the indexed passage. The retrieved passage had similarity approximately 0.885, above the configured 0.40 threshold. This value measures vector similarity, not factual certainty.
5. Download the original through the authenticated route. Its bytes matched the uploaded policy exactly.
6. Ask, "What is the annual travel allowance?" The application returned `insufficient_evidence` with no claims or sources, rather than inventing an allowance.
7. Fetch history and confirm both question results were saved. Then delete the sample document, wait for the worker to remove its document row, and confirm history was cleared. Log out to invalidate the test session. The empty test account remains; existing user workspaces were not used for this check.

The recorded response is in `docs/Live-Gemini-Verification.json`, and the project validation summary is in `VALIDATION.md`. The repeatable check is `docs/.build/live_workflow_check.py`; running it again creates a new isolated account and makes real provider requests. It is a manual smoke check, not part of the deterministic pytest suite.

This result verifies the basic live HTTP path through the frontend proxy and backend services. It does not verify browser button clicks, citation-dialog rendering, large PDF processing, retrieval across many documents, load handling, or production readiness. The unsupported result proves the final abstention behavior; it does not identify whether that specific question stopped at retrieval or model generation. Account billing and remaining quota were not checked.

# 14. The frontend and its connection to the API

## 14.1 React and TypeScript basics

`page.tsx` starts with `'use client'`, which allows browser state, event handlers, and hooks. A component is a function returning JSX. Type aliases such as User, Document, Source, Claim, Answer, and History describe the shapes expected by the interface. TypeScript catches many mistakes during a build, but it does not validate arbitrary HTTP JSON at runtime.

`useState` stores values that affect rendering. `useEffect` starts work associated with a render lifecycle and can return cleanup logic. `useRef` holds a file input or dialog reference without making the reference itself part of displayed state. `useCallback` stabilizes functions used by effects.

## 14.2 State groups

Authentication state includes user, loading, registering, authBusy, and authError. Navigation/data state includes view, documents, history, and filter. Question state includes question, asked, result, and asking. Upload state includes uploading and dragging. Feedback state includes notice and selected source.

The initial effect calls `/api/me`. A successful response shows the workspace; failure leads to the authentication screen. This implementation does not distinguish every startup network error from an unauthenticated state in that initial effect.

Once authenticated, an effect loads documents and polls every 4000 milliseconds. It clears the timer during cleanup. History is fetched when the history view opens. Notices clear after eight seconds. Selecting a source opens the native HTML dialog.

## 14.3 The API helper

`api<T>()` calls browser fetch with `/api/` plus the endpoint path. Mutation requests receive `X-Sourceboard: 1`. String request bodies receive JSON Content-Type. FormData bodies keep the browser-generated multipart boundary. The helper reads JSON and throws an Error on non-success responses, using a string detail message when available.

The browser sends same-origin session cookies with these requests. The provider key never needs to be in React state, frontend environment variables, or browser headers. `NEXT_PUBLIC_` variables would be bundled into browser code and are not appropriate for secrets.

## 14.4 The four visible experiences

Authentication toggles between account creation and sign-in. Ask knowledge shows suggested questions, a composer, claims, citations, and an evidence panel. Knowledge sources offers a file picker/drop zone, client-side filename filtering, statuses, retry, download, and delete. Recent questions loads saved results and can display one without regenerating an answer.

Pressing Enter submits a question, while Shift+Enter permits a newline. Busy states disable relevant actions. The source dialog displays the normalized indexed passage. Source counts and indexed passage totals are calculated from document metadata, not hardcoded demo metrics.

## 14.5 Why there is a Next.js proxy

The browser talks to the same origin that served its page. The catch-all route handler then calls the fixed API host on the server. This lets cookies and request behavior remain same-origin and keeps the internal container hostname out of browser code.

The proxy forwards only cookie, content-type, origin, and x-sourceboard headers. It does not manufacture the protection header for a caller that omitted it. Each path segment is encoded before building the upstream URL, and the user cannot select a different host.

For the upload path, the proxy permits an 11 MB body to allow multipart overhead. Other paths are limited to 32 KiB. It checks Content-Length and also counts streamed body bytes. It buffers the permitted request body, forwards it with no-store caching and manual redirects, and uses a 300000-millisecond upstream abort signal.

The response preserves content-type, content-disposition, and set-cookie, then streams the upstream body. This is HTTP body forwarding, not token-by-token AI generation streaming. Only GET, POST, and DELETE handlers are exported.

## 14.6 Styling and responsive design

`globals.css` defines tokens such as background, ink, muted text, border, blue, soft blue, and green. Flexbox handles sidebars and aligned controls; CSS Grid handles statistics and the answer/evidence layout. Media queries adjust layouts around 1450, 1150, 900, and 600 pixels.

The interface includes visible focus outlines, labels, status/alert regions, keyboard upload activation, and a native dialog. These are useful accessibility features, but no full accessibility certification or comprehensive browser visual audit has been established.

# 15. Docker images, networking, and startup

## 15.1 Images versus containers

An image is a packaged filesystem and startup configuration. A container is a running instance of an image. A volume persists selected data independently of a container's writable layer. Compose describes how several containers cooperate.

Changing source files on Windows does not automatically change source copied into a production image. The active Compose app does not bind-mount backend source for hot reload. Rebuild to apply code changes.

## 15.2 The backend Dockerfile

The backend starts from `python:3.12-slim`, sets Python bytecode/unbuffered-output environment flags, and uses `/app` as its working directory. It copies dependency files before source, installs packages, then copies app and migrations. This ordering lets Docker reuse the dependency layer when only application code changes.

It creates and switches to an unprivileged appuser. Its default command is Uvicorn on 0.0.0.0:8000. Compose overrides that command for the worker and migration services. The same source/build definition therefore supports three different process roles.

## 15.3 The frontend Dockerfile

The dependencies stage uses Node 22 Alpine and runs npm ci. The build stage copies installed dependencies and source, then runs npm run build. The runtime stage copies only standalone server output and static assets, sets production environment values, switches to the node user, and runs server.js.

`output: 'standalone'` in Next.js configuration enables this packaging approach. `EXPOSE` documents a container port; host access comes from Compose port mappings. Binding 0.0.0.0 inside a container is needed for network access from outside that container.

## 15.4 Services and dependencies

| Service | Startup and persistence |
| --- | --- |
| postgres | Uses pgvector/pgvector:pg17 and a persistent postgres_data volume; pg_isready health check. |
| minio | Uses the pinned Quay MinIO release and an objects volume; HTTP liveness check. |
| migrate | Waits for healthy database/storage; applies schema and bucket setup; exits successfully. |
| api | Waits for successful migration; starts Uvicorn; readiness checks database and storage. |
| worker | Waits for successful migration; starts the queue loop; limited to 1 GB memory and one CPU by Compose. |
| web | Waits for healthy API; starts the standalone Next.js server. |

The long-running services use `restart: unless-stopped`. The migration service uses restart=no because it is a one-shot task. An exited migration container with exit code zero is expected, not a broken application.

## 15.5 Networking and ports

| Address | Purpose |
| --- | --- |
| http://localhost:3000 | User-facing website. |
| http://localhost:8000/docs | Backend API documentation. |
| http://localhost:8000/health/ready | Database/storage readiness check. |
| localhost:5432 | PostgreSQL host port for local tools. |
| http://localhost:9000 | MinIO S3 API. |
| http://localhost:9001 | MinIO console. |

Inside the Compose network, service names act as hostnames: postgres, minio, and api. Inside the API container, localhost means the API container itself, not your Windows machine or the database container. Compose overrides are what make its database and storage connections work.

Host mappings bind to 127.0.0.1, so these ports are intended for local access. Docker named volumes `sourceboard_postgres_data` and `sourceboard_objects` store the active application's database and original files. Stopping or recreating a container should not delete those named volumes.

## 15.6 The MinIO registry fix

The original Docker Hub MinIO image address returned pull access denied in this environment. The same pinned release downloaded successfully from `quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z`. Both application and test Compose files now use that address.

This was an image-distribution issue, not an S3 password or application-code failure. A release tag is more stable than latest, but tags are not the same as immutable image digests. The PostgreSQL and Python/Node base tags also remain floating within their named versions.

# 16. Rebuild the application in learning stages

## Stage 1: Define the behavior before choosing libraries

Write the user story: a signed-in person uploads a policy, waits for indexing, asks a question, and sees evidence. Define unavailable-evidence and provider-failure behavior before coding. Choose the supported formats and limits. Deliverable: a written input/output contract, not a mock promise that every question will be answerable.

## Stage 2: Create the backend skeleton

Create the backend/app package, typed Settings, a database connection helper, and a FastAPI object. Add `/health/live` first. Start it with Uvicorn and verify JSON at that URL. Learn imports, Python functions, decorators, environment variables, and context managers here.

## Stage 3: Add persistence and migrations

Write the SQL extension, tables, relationships, constraints, and indexes. Build a runner that applies new filenames transactionally. Add storage bucket initialization. Verify that running the migrator twice does not duplicate schema rows or recreate account data.

## Stage 4: Add authentication before document access

Implement hashing, session creation, current-user dependency, register/login/logout/me routes, and mutation protection. Test unauthenticated denial and cross-workspace access. Avoid using a client-provided workspace ID as authorization.

## Stage 5: Make uploads durable

Add file limits and suffix checks. Write the original to storage, insert a queued row, and return 202. Verify that a valid upload can exist before the worker is running. This separates acceptance from indexing and exposes the queue clearly.

## Stage 6: Implement extraction and chunking as pure logic

Write functions that accept bytes or strings and return page text/passages without opening database connections. Test empty files, invalid PDF bytes, UTF-8 errors, page boundaries, and overlap. Keep this stage independent of model credentials.

## Stage 7: Build the worker

Start with selecting one queued document and processing it. Add transactional claiming, status updates, batches, lease ownership, heartbeats, retries, and fencing. Verify final atomic publication and a deletion that occurs while a worker is still calculating vectors.

## Stage 8: Build the provider boundary

Implement a single HTTP request wrapper, embedding-response validation, structured answer schema, and review schema. Initially use mocked responses. Then send short synthetic requests to the real configured provider. Keep provider-specific compatibility rules inside this boundary.

## Stage 9: Add retrieval and evidence validation

Implement model/workspace filtering, question embedding, cosine ranking, top-six retrieval, threshold filtering, answer generation, exact quote checks, and review. Add tests where the model invents a source ID or quote. Confirm that such results abstain.

## Stage 10: Save history and complete deletion semantics

Add history persistence and the source recheck under the workspace lock. Implement immediate search removal plus asynchronous original deletion. Decide explicitly whether deletion clears all history or only affected entries; the current app clears all workspace history.

## Stage 11: Build the interface and proxy

Start with the authentication form and API helper. Add document loading/polling, upload, status display, ask flow, source dialog, and history. Add the fixed-destination Next.js proxy. Apply responsive CSS and keyboard interactions. Build with TypeScript checks enabled.

## Stage 12: Package, test, and document

Create backend and multistage frontend Dockerfiles. Wire Compose health checks and startup dependencies. Add isolated integration infrastructure, run tests, and capture actual results. Document both successes and gaps. Do not use a passing build as a substitute for testing a real provider response.

Each stage should leave a small working behavior you can demonstrate. Rebuilding all layers simultaneously makes it harder to locate a failure. Use the file map to compare each stage with the current implementation.

# 17. Tests and what they actually prove

## 17.1 Local tests

```powershell
.\.venv\Scripts\python -m pytest -c backend/pytest.ini backend/tests -q
npm --prefix frontend run build
```

The Python command runs the backend tests with the specified configuration. Integration cases skip unless TEST_DATABASE_URL is explicitly supplied. The Next.js command checks compilation, TypeScript, and page generation; it is not a browser interaction test.

## 17.2 What each test group checks

Grounding tests accept real quotes and reject invented sources, invented quotes, absent citations, malformed schemas, refusals, and empty answers. Extraction tests check supported inputs and chunk behavior. Embedding tests check dimensionality, ordering, invalid numeric values, and the Gemini zero-index compatibility rule.

HTTP tests cover liveness, unauthorized access, mutation protection, invalid credentials/input, excessive sizes, and route schema presence. RAG pipeline tests prove that empty workspaces abstain without provider calls and that rejected entailment does not become an accepted answer.

## 17.3 Isolated integration tests

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yaml down
```

The test project is named sourceboard-tests. PostgreSQL and MinIO use disposable tmpfs data. The tests service mounts the test source/config read-only and uses the backend image. It waits for healthy dependencies. Its TEST_DATABASE_URL targets only the test database.

The fixture runs real migrations and real S3 operations. It patches embedding, generation, and verification to deterministic fake functions. One test registers two users, uploads a policy, runs the worker, asks a question, checks tenant isolation, clears history through deletion, and removes the original. Another checks that a stale worker cannot republish a deleted source.

The fake embedding vector is dimensionally valid but deliberately simplistic. It verifies plumbing and isolation, not semantic retrieval quality. Passing these tests does not prove that Gemini always selects the right policy passage.

## 17.4 Recorded results and their limits

| Check | Recorded result |
| --- | --- |
| Docker backend suite before the Gemini fix | 23 passed, no skips, including both real database/storage integration cases. |
| Local backend suite after the Gemini fix | 22 passed, two integration cases skipped. Includes the new compatibility regression test. |
| Frontend production build | Passed, including TypeScript and prerendering. |
| Full application Compose startup | Passed; database/storage healthy, migrations successful, API/worker/web running. |
| HTTP checks | Website 200; readiness status=ok; anonymous API request 401. |
| Direct Gemini smoke checks | Authentication, two 1536-dimensional embeddings, cited answer validation, and review succeeded on sample text. |
| Full live-Gemini upload-to-answer HTTP test | Passed September 13, 2026: real indexing, correct cited answer, unsupported-question abstention, original download, history, deletion, and logout. See section 13.5. |
| Broad groundedness, performance, and browser QA | Not established by the checks above. |

Upstream Starlette/httpx and AnyIO deprecation warnings appeared without failing the tests. The record should be updated after future changes rather than treating these historical counts as permanent guarantees.

# 18. Run, inspect, and troubleshoot the project

## 18.1 Normal startup and shutdown

```powershell
docker compose up --build -d
docker compose ps
```

Open `http://localhost:3000`. Register or sign in, upload a small readable file, and wait for ready. A queued upload is not searchable yet. For ordinary subsequent starts without source changes, `docker compose up -d` is sufficient.

```powershell
docker compose logs --tail=100 api worker
docker compose logs --tail=100 web migrate
docker compose down
```

`-d` starts in the background. `--build` rebuilds images. `logs` displays service output. `down` removes the project's containers and network while preserving named data volumes by default. Adding `-v` would remove named volumes and application data; it is not part of normal shutdown.

## 18.2 Quick health checks

```powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Use the browser for account and file actions while learning. A raw POST from PowerShell must still include the correct session cookie and X-Sourceboard header. A public health check needs neither.

## 18.3 Local development with reload

Stop the containerized app before using the same host ports. Then start only its infrastructure:

```powershell
docker compose up -d postgres minio
.\.venv\Scripts\python -m backend.app.migrate
.\.venv\Scripts\python -m uvicorn backend.app.main:app --reload --port 8000
```

In another terminal from the root:

```powershell
.\.venv\Scripts\python -m backend.app.worker
```

In a third terminal:

```powershell
npm --prefix frontend run dev
```

The worker does not automatically reload its Python code. Restart it after worker changes. If the frontend needs a nondefault local API host, put API_INTERNAL_URL in frontend/.env.local; the root `.env` is not automatically a Next.js environment file when running from the frontend directory.

## 18.4 Troubleshooting by symptom

| Symptom | What to check and do |
| --- | --- |
| Docker cannot connect to its engine pipe | Start Docker Desktop and wait for the Linux engine. Check docker info before editing the app. |
| MinIO pull access denied | Confirm the Compose image is the Quay address used in this guide. Pull errors precede application startup. |
| Port already allocated | Check for local Uvicorn, Next.js, or another container using 3000/8000/5432/9000/9001. Stop only the conflicting service you own. |
| Website cannot reach API | Check compose ps, API readiness, and API_INTERNAL_URL. Inside Docker the host should be api, not localhost. |
| 403 Origin not allowed | Use localhost:3000 consistently with APP_ORIGIN, or update the configured origin and recreate services. |
| 403 Missing request protection header | Mutations need X-Sourceboard: 1. Use the app's helper or add it to your own authorized request. |
| 401 after a week or after logout | Sign in again. Session expiry is expected behavior. |
| Upload stays queued | Check that worker is running and connected to the same database/storage as API. Allow for polling. |
| Document becomes failed | Inspect the displayed error and worker logs. Check file readability, provider availability, and quota; Retry after fixing the cause. |
| Scanned PDF has no readable text | Run OCR externally or upload a text-based PDF/TXT. The current worker does not perform OCR. |
| Key saved but models fail | Key presence is not validation. Check provider URL, allowed models, credential permissions, and quota. |
| Gemini model returns 404 | A listed model can be unavailable to this account. Verify a supported replacement and update CHAT_MODEL. |
| Gemini returns 429 | Quota/rate limits may be exhausted. Wait according to provider guidance or inspect account limits; repeated immediate retries will not create quota. |
| Model returns invalid embeddings | Check dimensions, batch record count/indexes, and provider compatibility. Do not disable validation to force ingestion. |
| Ready documents but no answers after changing embedding model | Old vectors are excluded. Delete/re-upload affected documents to embed them with the current model. |
| Insufficient evidence for a question | Inspect source relevance, wording, current embedding model, and threshold. This can be a correct refusal. |
| Docker still runs old code | Rebuild and recreate with docker compose up --build -d. Production containers do not mount your source for live reload. |
| Document remains deleting | Search removal already happened; the worker may be retrying object-storage cleanup. Check worker/MinIO health. |

Do not print the complete container environment or `.env` when asking for help. Share error codes and redacted configuration names instead of credentials. Provider exceptions shown by the app intentionally omit detailed raw responses.

# 19. Security, limitations, and production planning

## 19.1 Protections already present

The app hashes passwords with scrypt, stores hashes of opaque session tokens, uses cookie protections, derives workspace identity from authentication, parameterizes SQL, limits accepted files, validates citations, and runs the backend container as a non-root user. The proxy has a fixed upstream and counts body bytes. The frontend sets frame denial, nosniff, and same-origin referrer headers.

Worker fencing protects against stale writes. Original files are served through an authenticated route rather than a public bucket URL. Deletion clears searchable chunks and saved answer history. These mechanisms each address specific problems; none is a general production-security certificate.

## 19.2 Important limitations visible in the code

There is no identity provider, email verification, password reset, invitation system, role-based access control, or billing. There is no distributed login/request rate limiter or model-spend quota. There is no malware scanner, per-file parser sandbox, or hard extraction deadline. Worker memory/CPU limits reduce exposure but do not supply all those features.

The API checks declared body sizes and bounds file reads, while the Next.js proxy also counts streamed body bytes. Direct API exposure needs its own deployment-level request limits. The application has no explicit connection pool, HNSW index, reranker, cache of model answers, or token-streaming response UX.

There is no automated backup/restore drill, audit log system, centralized metrics stack, object-orphan reconciler, retention policy engine, or complete accessibility audit. Local example storage credentials are administrative development credentials, not a scoped production bucket identity.

## 19.3 A responsible next implementation sequence

First add identity recovery, team membership/authorization, HTTPS, production secrets, quotas, and monitoring appropriate to the intended users. Then add backup and restore procedures for both PostgreSQL and MinIO. Restoring only one store can leave document metadata and originals inconsistent.

Build a representative evaluation set with questions, expected supporting passages, answerable/unanswerable labels, and tenant boundaries. Measure retrieval recall, citation correctness, unsupported-claim rate, latency, and provider usage. Use that evidence to choose chunking, thresholds, batching, and any approximate index.

Add upload scanning and stronger parser isolation before accepting arbitrary public uploads. Plan reconciliation for interrupted storage/database operations. Use immutable image digests and a reviewed deployment configuration when moving beyond local development. These are proposed next steps, not features this guide claims to have added.

# 20. Practical learning exercises and answers

## Exercise 1: Follow a document without reading every file

Create a UTF-8 sample policy file with the remote-work example. Upload it and observe queued/processing/ready. Locate the upload route, worker claim/process functions, and frontend polling effect. Explain why a successful upload response arrives before the file is ready.

Expected understanding: HTTP 202 records accepted work; the worker performs indexing later. The browser is polling status rather than receiving a model push notification. If the worker is fast, you may not see every intermediate state in the four-second UI interval.

## Exercise 2: Predict the chunks

Before running anything, predict the windows for 2800 characters on one page. Compare your answer with the chunking test. Then ask what happens if page 2 contains only one short sentence.

Expected understanding: three windows begin at 0, 1200, and 2400. Page 2 becomes its own passage with page=2 and the next global ordinal. It is not joined to the previous page.

## Exercise 3: Ask an unsupported question

Ask about annual travel allowance using only the remote-work policy. Inspect the result. Find `abstain()` and list situations where it can be called. Do not change the prompt to demand an answer regardless of evidence.

Expected understanding: abstention can happen before generation, after structural/quote validation, after review, or after a source changes. Provider failure is separately represented as a service error.

## Exercise 4: Explain a database transaction

Read the final database block in `worker.process()`. Write down all rows it changes. Explain the harm if ready status were committed before chunk insertion completed.

Expected understanding: search could observe a ready document with missing or incomplete passages. Atomic publication makes chunks and ready metadata visible together. Remote embedding calls occur before this final transaction, so the worker does not hold a document write lock throughout network processing.

## Exercise 5: Trace a citation

Click a citation in a displayed answer. Find where the source ID was created, retrieved, inserted into model input, validated, and rendered. Explain why checking that a quote exists is different from checking that it supports a claim.

Expected understanding: a chunk UUID becomes the source ID. Exact substring checks verify textual integrity, while entailment is a separate semantic question. The second model review helps but is not mathematical proof.

## Exercise 6: Learn tenant isolation

Read the two-user integration test. Identify document list, download, delete, and ask checks that protect one user's sources from the other. Explain why merely hiding another user's files in the frontend would be insufficient.

Expected understanding: enforcement belongs in authenticated backend queries. A browser interface can be bypassed by direct requests; server-side workspace filtering is essential.

## Exercise 7: Make a harmless interface change

Change one suggested question in `frontend/app/page.tsx`. Build the frontend. In local dev mode observe the refresh; in Docker rebuild the web image and recreate the web service. Restore the wording if it was only a learning experiment.

Expected understanding: React source changes affect the built frontend. Installing dependencies, compiling source, and restarting containers are separate operations. A production Docker container does not automatically read the changed local source file.

## Exercise 8: Plan a real feature before implementing it

Design document tags on paper. Identify a new migration, API validation, upload/update behavior, library display, and optional retrieval filtering. Specify tenant checks and tests. Do not add a frontend field that is never persisted or trusted correctly by the backend.

Expected understanding: a feature often crosses schema, API, UI, and tests. Its authorization rules must remain intact throughout. A design can use a join table for multiple tags rather than squeezing unrelated behavior into an existing string column.

## Exercise 9: Investigate a failed model call safely

Read the provider request wrapper and the validation record. Explain the difference among a missing key, rejected credential, unavailable model, exhausted quota, and malformed successful response. Identify which information can be shared without revealing a key.

Expected understanding: key presence alone is weak evidence. HTTP status, sanitized error reason, model name, endpoint host, and response dimensions/counts are useful diagnostic facts. Raw headers and `.env` contents are not needed.

## Exercise 10: Explain the project in your own words

Without looking at code, describe the path from Add sources to a cited answer in ten sentences. Then point to the file responsible for each sentence. If you cannot name a file, revisit the module map rather than memorizing more terminology.

# 21. Glossary, dependency reference, and further reading

## 21.1 Glossary

| Term | Meaning here |
| --- | --- |
| API | HTTP interface through which the browser and services exchange requests/results. |
| Endpoint | One method/path combination, such as POST /api/ask. |
| JSON | Structured text format used for request bodies and answer results. |
| Multipart | Request encoding used to send a file plus form fields. |
| Backend | Python service implementing authorization, persistence, and business logic. |
| Frontend | Browser interface and its Next.js server support. |
| ASGI | Python application-server interface implemented by FastAPI/Uvicorn. |
| ORM | A library mapping database rows to objects; this project uses direct SQL instead. |
| Tenant/workspace | Ownership boundary for documents, chunks, and question history. |
| Session | Server-recorded authentication represented by a browser cookie token. |
| Hash | One-way derived representation; used differently for passwords and session tokens. |
| Salt | Random input added to password hashing to separate otherwise identical passwords. |
| Migration | Versioned schema change applied once by the migration runner. |
| Transaction | Group of database changes committed or rolled back together. |
| Object storage | Storage addressed by bucket and object key, used for original files. |
| Chunk/passage | Bounded extracted-text segment used for search and citations. |
| Embedding | Model-produced vector representing a text input numerically. |
| Cosine distance | Vector comparison based on direction; pgvector exposes it through <=>. |
| Grounding | Constraining an answer to evidence available in supplied sources. |
| Entailment | Whether quoted evidence actually supports a stated claim. |
| Abstention | Returning insufficient evidence instead of manufacturing an answer. |
| Lease | Time-limited worker ownership of a document job. |
| Fencing token | Attempt identifier checked to reject stale worker publication. |
| Idempotence | Repeating an operation without creating unintended duplicate effects. |
| Image/container | Packaged runtime versus one running instance of that package. |
| Volume | Persistent container-managed storage independent of a container instance. |
| Proxy | Server forwarding requests to another fixed service. |
| Mock | Test substitute returning controlled behavior instead of contacting a real provider. |
| OCR | Converting text in images/scans into machine-readable characters. |

## 21.2 Direct dependencies and commands

The Python direct requirements are FastAPI, Uvicorn with standard extras, psycopg with binary extras, boto3, httpx, pydantic-settings, pypdf, python-multipart, and pytest. Transitive packages support those libraries: Starlette for web behavior; Pydantic/pydantic-core for validation; botocore/s3transfer for S3; httpcore/h11 for HTTP; AnyIO for async support; and other small utilities.

The constraints file records versions including FastAPI 0.141.1, Uvicorn 0.52.4, psycopg 3.3.5, boto3 1.43.93, httpx 0.28.1, pypdf 6.18.1, and pytest 9.1.1. It constrains versions but is not a hash-verified lockfile of every platform-specific dependency. Uvicorn's Linux extras can differ from a Windows installation.

The frontend directly depends on Next.js, React, and React DOM. Development dependencies include TypeScript plus Node/React type definitions. The recorded Next.js production build used 16.3.5. `package.json` contains allowed ranges; `package-lock.json` contains resolved versions. Use the lockfile rather than assuming a dependency range is the exact installed version.

| npm script | Actual purpose |
| --- | --- |
| dev | Runs Next.js development server bound to 127.0.0.1. |
| build | Runs next build. |
| start | Runs scripts/start.mjs for local standalone production output. |
| typecheck | Runs tsc --noEmit to check types without producing JavaScript output. |

## 21.3 Source-reading map for deeper study

For authentication, read `auth.py` then the session/register/login functions in `main.py`. For ingestion, read `upload()` then `worker.claim()`, `worker.process()`, and `extraction.py`. For answers, read `rag.answer()`, `provider.generate()`, `validate_answer()`, `provider.verify()`, and the history-save block in `main.ask()`.

For frontend behavior, read the `api<T>()` helper, state declarations, effects, and action functions before the JSX. For operations, compare the Dockerfiles with Compose commands and dependencies. For correctness, read a test next to each implementation rather than reading all tests only at the end.

## 21.4 Official references

These links support further study. The application descriptions in this guide are based on the local source files; provider pricing, availability, and account behavior should be rechecked before changing models or deploying.

- Python tutorial: https://docs.python.org/3/tutorial/
- React learning guide: https://react.dev/learn
- TypeScript handbook: https://www.typescriptlang.org/docs/handbook/intro.html
- Next.js App Router documentation: https://nextjs.org/docs/app
- FastAPI tutorial: https://fastapi.tiangolo.com/tutorial/
- Pydantic settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
- Psycopg documentation: https://www.psycopg.org/psycopg3/docs/
- PostgreSQL 17 documentation: https://www.postgresql.org/docs/17/
- pgvector source and documentation: https://github.com/pgvector/pgvector
- Boto3 S3 client: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html
- pypdf documentation: https://pypdf.readthedocs.io/
- HTTPX documentation: https://www.python-httpx.org/
- pytest documentation: https://docs.pytest.org/
- Docker Compose documentation: https://docs.docker.com/compose/
- Gemini OpenAI compatibility: https://ai.google.dev/gemini-api/docs/openai
- Gemini embeddings: https://ai.google.dev/gemini-api/docs/embeddings
- Gemini pricing and free-tier data-use notes: https://ai.google.dev/gemini-api/docs/pricing
- Google AI Studio API keys: https://aistudio.google.com/apikey

The next useful milestone is to run the sample document yourself, inspect its citation, and trace that action through the files. Understanding that complete path gives you a foundation for adding features without losing the system's evidence and ownership guarantees.
