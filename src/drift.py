"""Doc-hygiene drift report for the MCP tool `get_drift_report`.

Combines four signals (stale-string, dangling-ref, dep-out-of-date,
decision-contradict) into a prioritised queue. Used by the weekly
hygiene loop documented in `docs/00-fwk-doc-hygiene-loop.md`.

The actual signal collection lives in `scripts/detect_drift.py`. The
report is cached in-process for `DRIFT_CACHE_TTL_SECONDS` (default 60s)
so concurrent MCP callers don't each fork their own `stale_strings.py`,
walk `docs/`, and shell out to `git log`. Set the env var to 0 to
disable caching entirely.

Each item: file, line, signal, reason, authoritative_source,
suggested_replacement, snippet.
"""
import logging
import os
import sys
import threading
import time
from pathlib import Path

# Bring scripts/ onto sys.path so `from detect_drift import collect`
# resolves the same way at runtime as in src/__init__.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

log = logging.getLogger(__name__)

_CACHE_LOCK = threading.Lock()
_cache_items: list[dict] | None = None
_cache_expires_at: float = 0.0


def _cache_ttl() -> float:
    try:
        return float(os.getenv("DRIFT_CACHE_TTL_SECONDS", "60"))
    except (TypeError, ValueError):
        return 60.0


def _collect_cached() -> list[dict]:
    """Return cached items if fresh, else recompute under the lock."""
    global _cache_items, _cache_expires_at
    ttl = _cache_ttl()
    now = time.monotonic()
    if ttl <= 0:
        return _collect_fresh()
    with _CACHE_LOCK:
        if _cache_items is not None and now < _cache_expires_at:
            return _cache_items
        items = _collect_fresh()
        _cache_items = items
        _cache_expires_at = now + ttl
        return items


def _collect_fresh() -> list[dict]:
    from detect_drift import collect  # type: ignore
    return collect()


def get_drift_report(top: int = 10,
                     signal: str | None = None,
                     area: int | None = None) -> dict:
    """Return the top-N drift items, optionally filtered.

    Args:
        top: Maximum items to return (default 10, max 100).
        signal: Filter to one signal name, 'stale-string', 'dangling-ref',
            'dep-out-of-date', or 'decision-contradict'.
        area: Filter to a single capability area. Items match when the
            file path's leading two-digit area number matches.

    Returns:
        {
            "total": <int>,
            "by_signal": {<signal>: <count>, ...},
            "items": [<item dict>, ...],
            "cache_age_seconds": <float>,  # 0 when this call recomputed
        }
    """
    top = max(1, min(top, 100))

    try:
        items = _collect_cached()
    except Exception as exc:
        log.error("drift collect failed: %s", exc)
        return {"error": str(exc), "items": [], "total": 0, "by_signal": {}}

    if signal:
        items = [i for i in items if i["signal"] == signal]
    if area is not None:
        prefix = f"{int(area):02d}-"
        items = [
            i for i in items
            if Path(i["file"]).name.startswith(prefix)
            or Path(i["file"]).name.startswith(prefix.lstrip("0"))
        ]

    total = len(items)
    by_signal: dict[str, int] = {}
    for it in items:
        by_signal[it["signal"]] = by_signal.get(it["signal"], 0) + 1

    cache_age = max(0.0, _cache_expires_at - time.monotonic())
    cache_age_seconds = max(0.0, _cache_ttl() - cache_age) if _cache_ttl() > 0 else 0.0

    return {
        "total": total,
        "by_signal": by_signal,
        "items": items[:top],
        "cache_age_seconds": round(cache_age_seconds, 1),
    }
