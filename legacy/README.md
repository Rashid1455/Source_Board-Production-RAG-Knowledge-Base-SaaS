# Sourceboard

A working, self-hosted foundation for a company knowledge SaaS: create a private workspace, upload documents, ask questions, inspect source passages, and revisit question history.

## Run locally

Requires Python 3.11+ with SQLite FTS5. No Node build step or AI API key is needed.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python server.py
```

Open **http://127.0.0.1:8000**, create a workspace, and upload PDF, UTF-8 TXT, Markdown, or CSV files. Documents are limited to 10 MB and PDFs to 300 pages. Scanned PDFs need external OCR. Text uploads work without installing dependencies.

## What works

- Responsive document library, drag-and-drop uploads, question interface, source inspection, and saved history.
- Persistent SQLite storage with per-account document and retrieval isolation.
- PDF extraction with page citations, overlapping 200-word passages, and SQLite FTS5/BM25 retrieval.
- Evidence-first results: quoted passages with source references; explicit insufficient-evidence responses when keyword coverage is below threshold.
- Password hashing with scrypt; opaque, hashed-at-rest session tokens; HttpOnly SameSite cookies; parameterized database queries; restrictive browser content policy.
- Source deletion removes indexed passages and the workspace’s saved answer history to avoid retaining deleted excerpts.

## Retrieval limits

This implementation uses **lexical retrieval and direct excerpts**, not embeddings or LLM-generated synthesis. The 60% query-term overlap threshold is a retrieval heuristic, not a factual confidence score. A matching passage can still be irrelevant, incomplete, outdated, or contradictory. The interface labels results as related evidence instead of claiming a verified answer. Queries using synonyms may return no evidence. Text files use page 1; PDF citations refer to physical PDF page numbers. Source inspection shows the indexed passage, not a PDF viewer.

Uploaded text is treated as data and never executed or used as model instructions. The app does not include sample documents or fabricated usage metrics.

## Validation

```powershell
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests cover HTTP account/session flows, tenant isolation, evidence retrieval, refusal on unrelated questions, deletion and history cleanup, upload validation, and PDF text extraction when pypdf is installed.

## Before offering this as a production SaaS

This is a runnable foundation, **not a production-certified deployment**. Each account currently owns one isolated workspace; invitations, shared membership, and roles are not implemented. The built-in HTTP server binds to localhost and is for local use. For an internet-facing service, add a production application server and HTTPS reverse proxy, rate limiting and login abuse protection, email verification/password reset or an identity provider, team RBAC, background ingestion with bounded worker resources, file scanning and parser isolation, quotas, audit logs, backups with restore tests, monitoring, and retention controls. Uploaded text is stored unencrypted in the local database; original files are not retained. There is no billing integration.

For a full semantic RAG pipeline, add tenant-filtered embeddings and reranking, evaluate retrieval on representative company questions, and introduce a synthesis model with structured citation validation, contradiction handling, and groundedness evaluations. Do not interpret lexical overlap as proof that a question is answerable.

Configuration: `PORT` (default 8000), `HOST` (default 127.0.0.1), `SOURCEBOARD_DB` (default `data/sourceboard.db`), and `COOKIE_SECURE=1` when served through HTTPS. Keep the database outside any publicly served directory.
