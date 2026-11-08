"""LangGraph checkpointer selection: Postgres in production, SQLite locally."""
from __future__ import annotations

import sqlite3
import threading

from . import db

_LOCK = threading.Lock()
_SAVER = None
_SQLITE_CONN = None


def get_checkpointer():
    global _SAVER, _SQLITE_CONN
    if _SAVER is not None:
        return _SAVER

    with _LOCK:
        if _SAVER is not None:
            return _SAVER

        if db.is_postgres():
            from langgraph.checkpoint.postgres import PostgresSaver

            _SAVER = PostgresSaver(db.get_checkpoint_pool())
            _SAVER.setup()
        else:
            from langgraph.checkpoint.sqlite import SqliteSaver

            db.CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            _SQLITE_CONN = sqlite3.connect(
                str(db.CHECKPOINT_PATH), check_same_thread=False, timeout=30
            )
            _SAVER = SqliteSaver(_SQLITE_CONN)
            _SAVER.setup()

        return _SAVER


def close_checkpointer() -> None:
    global _SAVER, _SQLITE_CONN
    with _LOCK:
        if _SQLITE_CONN is not None:
            _SQLITE_CONN.close()
        _SQLITE_CONN = None
        _SAVER = None
