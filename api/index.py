import base64
import os
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

EMAIL = os.getenv("EMAIL", "23f2001912@ds.study.iitm.ac.in")
TOTAL_ORDERS = 40
RATE_LIMIT = 16
WINDOW_SECONDS = 10.0

app = FastAPI(title="Orders API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["Retry-After", "Idempotency-Key"],
)

_lock = threading.Lock()
_idempotency = {}
_rate_events = defaultdict(deque)


def rate_limited(client_id: str):
    now = time.monotonic()
    with _lock:
        bucket = _rate_events[client_id]
        while bucket and now - bucket[0] >= WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= RATE_LIMIT:
            retry_after = max(1, int(WINDOW_SECONDS - (now - bucket[0]) + 0.999))
            return retry_after
        bucket.append(now)
        return None


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Let CORS preflight requests pass without consuming a client's quota.
    if request.method == "OPTIONS":
        return await call_next(request)

    # X-Client-Id makes the per-client behavior explicit for API consumers.
    client_id = request.headers.get("X-Client-Id") or (
        request.client.host if request.client else "anonymous"
    )
    retry_after = rate_limited(client_id)
    if retry_after is not None:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
            headers={
                "Retry-After": str(retry_after),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
            },
        )
        return response

    response = await call_next(request)
    # Guarantee the required header on every HTTP 429 response.
    if response.status_code == 429 and "Retry-After" not in response.headers:
        response.headers["Retry-After"] = "10"
    return response


@app.post("/orders")
def create_order(idempotency_key: str = Header(..., alias="Idempotency-Key")):
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Idempotency-Key must not be empty")
    with _lock:
        existing = _idempotency.get(key)
        if existing is not None:
            return JSONResponse(status_code=200, content=existing)
        order = {"id": str(uuid.uuid4()), "status": "created", "email": EMAIL}
        _idempotency[key] = order
        return JSONResponse(status_code=201, content=order)


def encode_cursor(offset: int) -> str:
    raw = f"orders:v1:{offset}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> int:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode()).decode()
        prefix, version, raw_offset = decoded.split(":")
        offset = int(raw_offset)
        if prefix != "orders" or version != "v1" or not 0 <= offset <= TOTAL_ORDERS:
            raise ValueError
        return offset
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid cursor")


@app.get("/orders")
def list_orders(
    limit: int = Query(default=10, ge=1, le=40),
    cursor: str | None = Query(default=None),
):
    offset = decode_cursor(cursor) if cursor else 0
    ids = range(1, TOTAL_ORDERS + 1)
    selected = list(ids)[offset:offset + limit]
    items = [
        {"id": order_id, "status": "catalog", "email": EMAIL}
        for order_id in selected
    ]
    new_offset = offset + len(selected)
    next_cursor = encode_cursor(new_offset) if new_offset < TOTAL_ORDERS else None
    return {"items": items, "next_cursor": next_cursor}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
