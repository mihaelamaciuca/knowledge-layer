"""Process-wide Postgres connection pool for the MCP server tools.

Lazily created on first use; closed when the FastAPI lifespan tears
down (see src/main.py). Each tool handler grabs a connection from the
pool, uses it, and returns it. Avoids the ~20-50ms TCP+TLS+auth
handshake that bare `psycopg2.connect()` per call would cost.

Use:
    from src.db import connection
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(...)

Tunables (env vars):
    PG_POOL_MIN  default 1   minimum connections kept open
    PG_POOL_MAX  default 10  maximum connections (raise for high concurrency)
"""
from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from typing import Iterator

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

log = logging.getLogger(__name__)

_pool: ThreadedConnectionPool | None = None
_lock = threading.Lock()


def get_pool() -> ThreadedConnectionPool:
    """Return the process-wide pool, creating it on first call."""
    global _pool
    if _pool is None:
        with _lock:
            if _pool is None:
                minconn = int(os.getenv("PG_POOL_MIN", "1"))
                maxconn = int(os.getenv("PG_POOL_MAX", "10"))
                _pool = ThreadedConnectionPool(
                    minconn, maxconn,
                    os.environ["DATABASE_URL"],
                )
                log.info("Postgres pool initialised (min=%d, max=%d)", minconn, maxconn)
    return _pool


@contextmanager
def connection() -> Iterator[psycopg2.extensions.connection]:
    """Borrow a connection from the pool; return it on context exit.

    The caller owns transaction policy (commit/rollback) on the borrowed
    connection. If an exception escapes the `with` block, the connection
    is returned to the pool flagged as broken so the pool drops it.
    """
    pool = get_pool()
    conn = pool.getconn()
    broken = False
    try:
        yield conn
    except Exception:
        broken = True
        raise
    finally:
        pool.putconn(conn, close=broken)


def close_pool() -> None:
    """Close every connection in the pool. Called from main.py lifespan
    teardown so Railway redeploys don't leak Postgres connections."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception as exc:
            log.warning("closing Postgres pool failed: %s", exc)
        _pool = None
