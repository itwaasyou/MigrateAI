from __future__ import annotations

import logging
import os
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .api import router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("migrateai.api")
web_origins = [
    origin.strip()
    for origin in os.getenv(
        "WEB_ORIGINS", os.getenv("WEB_ORIGIN", "http://localhost:3000")
    ).split(",")
    if origin.strip()
]
app = FastAPI(
    title="MigrateAI API",
    version="0.2.0",
    description="Evidence-based software migration analysis",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=web_origins,
    allow_origin_regex=os.getenv("WEB_ORIGIN_REGEX") or None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", "")[:80] or os.urandom(8).hex()
    started = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_id=%s method=%s path=%s status=%s duration_ms=%d",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        int((time.monotonic() - started) * 1000),
    )
    return response
