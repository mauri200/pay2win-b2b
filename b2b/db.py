"""Database access for the B2B module.

Uses ``DATABASE_URL`` (Postgres) when available and falls back to a local
SQLite file for development. Both dialects share the same schema and queries.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

_SQLITE_DEFAULT = Path(__file__).resolve().parent / "data" / "b2b.sqlite3"
SQLITE_PATH = Path(os.getenv("B2B_SQLITE_PATH", str(_SQLITE_DEFAULT))).expanduser()
CHECKPOINT_PATH = Path(
    os.getenv("B2B_CHECKPOINT_PATH", str(SQLITE_PATH.with_name("checkpoints.sqlite3")))
).expanduser()

_POOL = None
_CHECKPOINT_POOL = None
_POOL_LOCK = threading.Lock()
_INIT_LOCK = threading.Lock()
_INITIALIZED = False


def is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgresql://", "postgres://"))


def _new_pool(*, autocommit: bool):
    from psycopg_pool import ConnectionPool

    options = {
        "conninfo": DATABASE_URL,
        "min_size": 0,
        "max_size": 5,
        "open": True,
        "max_idle": 60.0,
        "max_lifetime": 1800.0,
        "timeout": 30.0,
        # Neon's pooled endpoint (PgBouncer) does not play well with
        # server-side prepared statements.
        "kwargs": {"prepare_threshold": None},
    }
    if autocommit:
        options["kwargs"]["autocommit"] = True
    return ConnectionPool(**options)


def get_pool():
    global _POOL
    if not is_postgres():
        raise RuntimeError("DATABASE_URL is not configured for Postgres")
    if _POOL is None:
        with _POOL_LOCK:
            if _POOL is None:
                _POOL = _new_pool(autocommit=False)
    return _POOL


def get_checkpoint_pool():
    """Dedicated pool for LangGraph.

    ``PostgresSaver.setup()`` runs ``CREATE INDEX CONCURRENTLY``, which cannot
    execute inside a transaction, so this pool must use autocommit.
    """
    global _CHECKPOINT_POOL
    if not is_postgres():
        raise RuntimeError("DATABASE_URL is not configured for Postgres")
    if _CHECKPOINT_POOL is None:
        with _POOL_LOCK:
            if _CHECKPOINT_POOL is None:
                _CHECKPOINT_POOL = _new_pool(autocommit=True)
    return _CHECKPOINT_POOL


def close_pool() -> None:
    global _POOL, _CHECKPOINT_POOL
    with _POOL_LOCK:
        if _CHECKPOINT_POOL is not None:
            _CHECKPOINT_POOL.close()
            _CHECKPOINT_POOL = None
        if _POOL is not None:
            _POOL.close()
            _POOL = None


def placeholder() -> str:
    return "%s" if is_postgres() else "?"


@contextmanager
def connection() -> Iterator[Any]:
    if is_postgres():
        with get_pool().connection() as conn:
            yield conn
        return

    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(SQLITE_PATH), check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _statements() -> list[str]:
    serial_pk = "BIGSERIAL PRIMARY KEY" if is_postgres() else "INTEGER PRIMARY KEY AUTOINCREMENT"
    return [
        f"""
        CREATE TABLE IF NOT EXISTS delegations (
            thread_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            created_ts DOUBLE PRECISION NOT NULL,
            updated_at TEXT NOT NULL,
            customer_id TEXT,
            objective TEXT,
            budget DOUBLE PRECISION NOT NULL DEFAULT 0,
            per_item_cap DOUBLE PRECISION NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'USD',
            financing TEXT,
            status TEXT,
            grand_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            remaining DOUBLE PRECISION NOT NULL DEFAULT 0,
            order_id TEXT,
            approve_url TEXT,
            payment_mode TEXT,
            items TEXT,
            customs TEXT,
            logistics TEXT,
            compliance TEXT,
            treasury TEXT,
            payments TEXT,
            trace TEXT,
            message TEXT,
            items_count INTEGER NOT NULL DEFAULT 0,
            suppliers TEXT,
            goods_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            duties_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            tax_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            shipping_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            fees_total DOUBLE PRECISION NOT NULL DEFAULT 0,
            state_json TEXT
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS paypal_events (
            id {serial_pk},
            event_id TEXT UNIQUE,
            event_type TEXT,
            order_id TEXT,
            verified BOOLEAN NOT NULL DEFAULT FALSE,
            detail TEXT,
            amount DOUBLE PRECISION NOT NULL DEFAULT 0,
            payload TEXT,
            received_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_delegations_order_id ON delegations(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_paypal_events_order_id ON paypal_events(order_id)",
        "CREATE INDEX IF NOT EXISTS idx_paypal_events_received_at ON paypal_events(received_at DESC)",
    ]


def init_db() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:
            return
        with connection() as conn:
            cur = conn.cursor()
            if not is_postgres():
                cur.execute("PRAGMA journal_mode=WAL")
            for statement in _statements():
                cur.execute(statement)
            if not is_postgres():
                conn.commit()
        _INITIALIZED = True
