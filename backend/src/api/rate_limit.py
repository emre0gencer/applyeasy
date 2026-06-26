"""Lightweight in-memory sliding-window rate limiter (per-process, per-IP).

Not distributed — it matches this app's single-process SQLite deployment. Its
job is to stop an anonymous caller from hammering the expensive /generate and
/upload endpoints (each /generate fans out to several Groq calls + local
embedding/PDF work, so unbounded calls = quota/billing exhaustion + CPU DoS).

Used as FastAPI route dependencies; raises 429 with a Retry-After header.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request


class _SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            dq = self._hits[key]
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= self.max_requests:
                retry_after = int(dq[0] + self.window_seconds - now) + 1
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please slow down and try again shortly.",
                    headers={"Retry-After": str(retry_after)},
                )
            dq.append(now)


def _client_ip(request: Request) -> str:
    # Honor the first X-Forwarded-For hop when behind a proxy; else peer address.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Expensive multi-LLM pipeline: generous but bounded.
_generate_limiter = _SlidingWindowLimiter(max_requests=10, window_seconds=60.0)
# Uploads are cheaper but still parse PDFs; allow more.
_upload_limiter = _SlidingWindowLimiter(max_requests=20, window_seconds=60.0)


def rate_limit_generate(request: Request) -> None:
    _generate_limiter.check(_client_ip(request))


def rate_limit_upload(request: Request) -> None:
    _upload_limiter.check(_client_ip(request))
