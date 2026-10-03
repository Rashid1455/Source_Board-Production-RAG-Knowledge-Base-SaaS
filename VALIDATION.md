# Validation record

Validated locally on September 12, 2026:

- Docker backend suite: **23 tests passed**, **0 skipped**, in 6.93 seconds on Python 3.12.14, including both integration cases against real Postgres/pgvector and MinIO. Compose exited with code 0.
- Backend Docker image build and test infrastructure health checks: **passed**. MinIO is pulled from `quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z` because the Docker Hub address returned pull access denied. Both Compose files now use Quay.
- Next.js 16.3.5 production build: **passed**, including TypeScript and prerendering.
- Live HTTP checks: Next.js page **200**, FastAPI liveness **200**, anonymous request through the Next.js proxy **401**, unprotected mutation through the proxy **403**.
- Python modules compile. Both Compose files parse as YAML.
- npm reported no vulnerabilities during dependency installation.

Gemini configuration verified on September 12, 2026:

- Saved key authenticated with Google's model-list endpoint (key never printed).
- `gemini-embedding-2` returned two separate 1536-dimensional embeddings through the compatibility endpoint. Fixed Google's omitted zero index while retaining batch validation.
- `gemini-3.5-flash-lite` generated a structurally valid cited answer and passed evidence review using synthetic sample text. The older 2.5 Flash-Lite model returned 404 for this account.
- Local backend tests after the compatibility fix: **22 passed**, **2 integration cases skipped**. The earlier Docker integration result above predates this fix.
- Application rebuilt and restarted with Gemini settings; website HTTP 200 and API readiness passed.

Live application workflow verified on September 13, 2026:

- Tested through the Next.js HTTP proxy at localhost:3000 using an isolated test account, the real worker, PostgreSQL/pgvector, MinIO, and live Gemini calls (no provider mocks).
- Registered successfully, uploaded a synthetic policy, and observed ready status on the first ingestion attempt: one page and one chunk.
- Asked how many days employees may work remotely. Returned `answered`: "Employees may work remotely three days per week." Verified the citation belonged to the uploaded document and its exact quote appeared in the indexed passage.
- Downloaded the original and verified its bytes matched the upload.
- Asked about annual travel allowance. Returned `insufficient_evidence` with no claims or sources.
- Verified both results appeared in history. Deleted the sample document, waited for worker removal, verified history was cleared, and logged out. An empty isolated test account remains.
- Full result: `docs/Live-Gemini-Verification.json`. This verifies the HTTP workflow, not browser clicking, dialog rendering, broad retrieval quality, or production readiness.

Not verified here:

- Account billing tier, whether the successful requests incurred charges, and remaining free quota were not inspected.
- Visual browser QA: the available browser plugin failed initialization during the earlier prototype work.

The test runner emitted upstream Starlette/httpx deprecation warnings. These did not fail the tests. This record does not claim production readiness or model groundedness evaluation.
