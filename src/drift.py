"""Doc-hygiene drift report for the MCP tool `get_drift_report`.

Combines five signals (stale-string, dangling-ref, dep-out-of-date,
decision-contradict, consolidation) into a prioritised queue. Used by
the weekly hygiene loop documented in `docs/00-fwk-doc-hygiene-loop.md`.

Closes Contract 5 (doc consistency audit) in `00-spec-retrieval-contract`.

The actual signal collection lives in `scripts/detect_drift.py` and
runs in-process here. Slower than reading a cached JSON file but always
fresh.
"""
import logging
import sys
from pathlib import Path

# Bring scripts/ onto sys.path so `from detect_drift import collect`
# resolves the same way at runtime as in src/__init__.py.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

log = logging.getLogger(__name__)


def get_drift_report(top: int = 10,
                     signal: str | None = None,
                     area: int | None = None) -> dict:
    """Return the top-N drift items, optionally filtered.

    Args:
        top: Maximum items to return (default 10, max 100).
        signal: Filter to one signal name, 'stale-string', 'dangling-ref', 'dep-out-of-date',
            'decision-contradict', or 'consolidation'.
        area: Filter to a single capability area (0-12). Items match
            when the file path's leading two-digit area number matches.

    Returns:
        {
            "total": <int>,
            "by_signal": {<signal>: <count>, ...},
            "items": [<item dict>, ...],
        }

    Each item: file, line, signal, reason, authoritative_source,
    suggested_replacement, snippet.
    """
    top = max(1, min(top, 100))

    try:
        from detect_drift import collect, PRIORITY  # type: ignore
    except Exception as exc:
        log.error("detect_drift import failed: %s", exc)
        return {"error": str(exc), "items": [], "total": 0, "by_signal": {}}

    try:
        items = collect()
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

    return {
        "total": total,
        "by_signal": by_signal,
        "items": items[:top],
    }
