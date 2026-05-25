"""Document outline lookup for the MCP tool `get_doc_outline`.

Given a doc filename (bare or full form), returns the section tree
that the indexer wrote to `doc_outlines` at the last upsert.

Used by Claude to navigate long specs (the 4,800-line test plan, the
3,000-line build guides) without grep-searching the body.
"""
import logging

from rag_core.relationships import to_bare, to_full
from src.db import connection

log = logging.getLogger(__name__)


def get_doc_outline(filename: str, max_level: int = 3) -> dict:
    """Return the section tree for `filename`.

    `filename` may be the bare form (e.g. `05-spec-architecture`) or the
    full form (`{{PROJECT_NAME}}/docs/...md`).

    Returns:
        {
            "filename": "<bare>",
            "source_file": "<full>",
            "outline": [{"level", "header", "anchor", "char_start", "char_end"}, ...]
        }

    `outline` is filtered to entries with `level <= max_level`. An empty
    list means the doc had no headers OR the indexer hasn't written its
    outline yet (the next reindex populates everything).

    `max_level` is clamped to [1, 3]; values outside the range silently
    snap to the closest valid level.
    """
    max_level = max(1, min(int(max_level), 3))
    bare = to_bare(filename) if "/" in filename else filename
    if bare.endswith(".md"):
        bare = bare[:-3]
    full = to_full(bare)

    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT outline FROM doc_outlines WHERE source_file = %s",
                    (full,),
                )
                row = cur.fetchone()
    except Exception as exc:
        log.error("get_doc_outline failed: %s", exc)
        return {"error": str(exc)}

    if not row:
        return {"filename": bare, "source_file": full, "outline": []}

    outline = row[0] or []
    if max_level < 3:
        outline = [e for e in outline if e.get("level", 1) <= max_level]

    return {
        "filename": bare,
        "source_file": full,
        "outline": outline,
    }
