"""Helpers shared by subagents."""
from __future__ import annotations

import time


def audit(state: dict, agent: str, summary: str, data: dict | None = None) -> list:
    """Append one audit entry and return the full trace (state replacer)."""
    trace = list(state.get("trace") or [])
    trace.append({
        "ts": time.strftime("%H:%M:%S"),
        "agent": agent,
        "summary": summary,
        "data": data or {},
    })
    return trace


def money(value: float) -> float:
    return round(float(value or 0), 2)
