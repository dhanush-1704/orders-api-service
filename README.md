# Orders API

FastAPI service demonstrating three API patterns:

- **Idempotent creation:** `POST /orders` requires an `Idempotency-Key`. Repeating a key returns the same order.
- **Cursor pagination:** `GET /orders?limit=10&cursor=...` pages through 40 sample catalog orders.
- **Per-client rate limiting:** 16 requests per 10 seconds, keyed by `X-Client-Id` (or client IP if omitted). Rate-limited requests return HTTP 429 and `Retry-After`.
- **CORS:** permits cross-origin GET, POST, and OPTIONS requests.
- **Health check:** `GET /healthz`.

## Deploy to Vercel

Import this repository into Vercel and deploy from the repository root. The API entry point is `api/index.py`.

Optional environment variable: `EMAIL`.

> Demo note: rate-limit and idempotency state is stored in process memory. For durable production behavior across serverless instances, replace it with shared storage such as Redis or a database.
