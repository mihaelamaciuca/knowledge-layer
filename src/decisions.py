"""Decision lookup and impact-target packets for the MCP tools
`get_decision` and `get_impact_targets`.

`get_decision(query_or_id)`. Contract 4 in the retrieval contract.
`get_impact_targets(doc_or_decision)`. Contract 1, registry-driven.

Reads from the `decisions` table populated by
`scripts/build_decision_registry.py`. If the table is empty (the
generator hasn't run yet), the tools return graceful empty results.
"""
import logging

from rag_core.relationships import to_full
from src.db import connection

log = logging.getLogger(__name__)


def _row_to_dict(cols, row):
    return {c: v for c, v in zip(cols, row)}


def _stringify_date(r: dict | None) -> None:
    if r and r.get("decided_on"):
        r["decided_on"] = r["decided_on"].isoformat()


_COLS = [
    "id", "decision_key", "area", "decision", "current_value",
    "source_doc", "decided_on", "cross_refs", "superseded_by",
]
_SELECT = "SELECT " + ", ".join(_COLS) + " FROM decisions"


def get_decision(query_or_id: str | int) -> dict:
    """Look up a single decision by id, key, or fuzzy text match.

    Resolution order:
        1. If `query_or_id` is an int or a digit string, lookup by id
        2. If it matches a `decision_key` slug, lookup by key
        3. Otherwise, ILIKE match on the decision text and current_value;
           return the highest-confidence match plus its alternatives

    Returns:
        {
            "decision": <row dict> or None,
            "alternatives": [<row dict>, ...],   # only when fuzzy match
            "supersedes_chain": [<row dict>, ...],
            "banner": "[CURRENT]" | "[SUPERSEDED by `<key>` on <date>]" | "[DRAFT]" | "[NOT FOUND]",
        }

    On error: `{"error": "<message>"}`.
    """
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                row: dict | None = None
                alternatives: list[dict] = []

                # 1. id lookup
                if isinstance(query_or_id, int) or (isinstance(query_or_id, str) and query_or_id.isdigit()):
                    cur.execute(_SELECT + " WHERE id = %s", (int(query_or_id),))
                    fetched = cur.fetchone()
                    if fetched:
                        row = _row_to_dict(_COLS, fetched)

                # 2. decision_key lookup
                if row is None and isinstance(query_or_id, str):
                    cur.execute(_SELECT + " WHERE decision_key = %s", (query_or_id,))
                    fetched = cur.fetchone()
                    if fetched:
                        row = _row_to_dict(_COLS, fetched)

                # 3. fuzzy match
                if row is None and isinstance(query_or_id, str):
                    cur.execute(
                        _SELECT + " WHERE decision ILIKE %s OR current_value ILIKE %s "
                        "ORDER BY length(decision) ASC LIMIT 5",
                        (f"%{query_or_id}%", f"%{query_or_id}%"),
                    )
                    matches = [_row_to_dict(_COLS, r) for r in cur.fetchall()]
                    if matches:
                        row = matches[0]
                        alternatives = matches[1:]

                if row is None:
                    return {
                        "decision": None,
                        "alternatives": [],
                        "supersedes_chain": [],
                        "banner": "[NOT FOUND]",
                    }

                # Walk supersession chain
                chain: list[dict] = []
                seen: set[int] = set()
                cursor_row = row
                for _ in range(10):
                    if cursor_row["superseded_by"] is None or cursor_row["id"] in seen:
                        break
                    seen.add(cursor_row["id"])
                    cur.execute(_SELECT + " WHERE id = %s", (cursor_row["superseded_by"],))
                    nxt = cur.fetchone()
                    if not nxt:
                        break
                    cursor_row = _row_to_dict(_COLS, nxt)
                    chain.append(cursor_row)

                if row["superseded_by"]:
                    target = chain[-1] if chain else None
                    if target:
                        banner = (
                            f"[SUPERSEDED by `{target['decision_key']}` on "
                            f"{target['decided_on'] or 'unknown date'}]"
                        )
                    else:
                        banner = f"[SUPERSEDED by id={row['superseded_by']}]"
                elif row.get("decided_on") is None:
                    banner = "[DRAFT]"
                else:
                    banner = "[CURRENT]"
    except Exception as exc:
        log.error("get_decision failed: %s", exc)
        return {"error": str(exc)}

    for r in [row, *alternatives, *chain]:
        _stringify_date(r)

    return {
        "decision": row,
        "alternatives": alternatives,
        "supersedes_chain": chain,
        "banner": banner,
    }


def _looks_like_decision_key(value: str) -> bool:
    """A decision_key is a lowercase slug without `.md` or path separators.

    A doc filename always carries `.md` or a `nn-type-` prefix; a decision
    key looks like `trial-length` or `advisory-lock-numbers`.
    """
    if not value:
        return False
    if value.endswith(".md"):
        return False
    if "/" in value:
        return False
    # Doc filenames start with two digits then a hyphen
    if len(value) >= 3 and value[0:2].isdigit() and value[2] == "-":
        return False
    return True


def get_impact_targets(doc_or_decision: str) -> dict:
    """Return every doc affected by a change to the given source.

    `doc_or_decision` may be:
        - A bare or full doc filename (delegates to get_doc_neighborhood)
        - A decision_key (resolves to its source_doc, then neighborhood)

    The resolver tries decision_key first when the value looks like a
    slug; if the lookup misses, it falls through to the doc-filename
    path. This way a key that happens to be a slug doesn't get treated
    as a missing doc.

    Returns:
        {
            "anchor": <doc filename or decision key>,
            "anchor_kind": "doc" | "decision",
            "decision": <row from decisions, or None>,
            "neighborhood": <full output of get_doc_neighborhood>,
        }

    On error: `{"error": "<message>"}` (only from the decision lookup; the
    neighborhood call has its own error surface).
    """
    from src.neighborhood import get_doc_neighborhood

    decision_row: dict | None = None
    anchor_doc: str | None = None
    anchor_kind = "doc"

    if isinstance(doc_or_decision, str) and _looks_like_decision_key(doc_or_decision):
        try:
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT id, decision_key, area, decision, current_value, "
                        "source_doc, decided_on, cross_refs FROM decisions "
                        "WHERE decision_key = %s",
                        (doc_or_decision,),
                    )
                    fetched = cur.fetchone()
                    if fetched:
                        cols = ["id", "decision_key", "area", "decision",
                                "current_value", "source_doc", "decided_on", "cross_refs"]
                        decision_row = dict(zip(cols, fetched))
                        anchor_doc = decision_row["source_doc"]
                        anchor_kind = "decision"
                        _stringify_date(decision_row)
        except Exception as exc:
            log.warning("decision lookup in get_impact_targets failed: %s", exc)

    if anchor_doc is None:
        anchor_doc = doc_or_decision

    neighborhood = get_doc_neighborhood(anchor_doc, include_superseded=False)

    return {
        "anchor": doc_or_decision,
        "anchor_kind": anchor_kind,
        "decision": decision_row,
        "neighborhood": neighborhood,
    }
