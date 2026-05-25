"""Decision lookup and impact-target packets for the MCP tools
`get_decision` and `get_impact_targets`.

`get_decision(query_or_id)`. Contract 4 in the retrieval contract.
`get_impact_targets(doc_or_decision)`. Contract 1, registry-driven.

Reads from the `decisions` table populated by
`scripts/build_decision_registry.py`. If the table is empty (the
generator hasn't run yet), the tools return graceful empty results.
"""
import logging
import os

import psycopg2

from rag_core.relationships import to_full

log = logging.getLogger(__name__)


def _connect():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _row_to_dict(cols, row):
    return {c: v for c, v in zip(cols, row)}


def get_decision(query_or_id: str | int) -> dict:
    """Look up a single decision by id, key, or fuzzy text match.

    Resolution order:
        1. If `query_or_id` is an int or a digit string → lookup by id
        2. If it matches a `decision_key` slug → lookup by key
        3. Otherwise → ILIKE match on the decision text and current_value;
           return the highest-confidence match plus its alternatives

    Returns:
        {
            "decision": <row dict> or None,
            "alternatives": [<row dict>, ...],   # only when fuzzy match
            "supersedes_chain": [<row dict>, ...],
            "banner": "[CURRENT]" | "[SUPERSEDED by <id> on <date>]" | "[DRAFT]",
        }
    """
    cols = [
        "id", "decision_key", "area", "decision", "current_value",
        "source_doc", "decided_on", "cross_refs", "superseded_by",
    ]
    select = "SELECT " + ", ".join(cols) + " FROM decisions"

    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                row = None
                alternatives: list[dict] = []

                # Try id
                if isinstance(query_or_id, int) or (isinstance(query_or_id, str) and query_or_id.isdigit()):
                    cur.execute(select + " WHERE id = %s", (int(query_or_id),))
                    fetched = cur.fetchone()
                    if fetched:
                        row = _row_to_dict(cols, fetched)

                # Try decision_key
                if row is None and isinstance(query_or_id, str):
                    cur.execute(select + " WHERE decision_key = %s", (query_or_id,))
                    fetched = cur.fetchone()
                    if fetched:
                        row = _row_to_dict(cols, fetched)

                # Try fuzzy match
                if row is None and isinstance(query_or_id, str):
                    cur.execute(
                        select + " WHERE decision ILIKE %s OR current_value ILIKE %s "
                        "ORDER BY length(decision) ASC LIMIT 5",
                        (f"%{query_or_id}%", f"%{query_or_id}%"),
                    )
                    matches = [_row_to_dict(cols, r) for r in cur.fetchall()]
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
                    cur.execute(select + " WHERE id = %s", (cursor_row["superseded_by"],))
                    nxt = cur.fetchone()
                    if not nxt:
                        break
                    cursor_row = _row_to_dict(cols, nxt)
                    chain.append(cursor_row)

                if row["superseded_by"]:
                    target = chain[-1] if chain else None
                    banner = f"[SUPERSEDED by id={row['superseded_by']}]"
                    if target:
                        banner = (
                            f"[SUPERSEDED by `{target['decision_key']}` on "
                            f"{target['decided_on'] or 'unknown date'}]"
                        )
                else:
                    banner = "[CURRENT]"
        finally:
            conn.close()
    except Exception as exc:
        log.error("get_decision failed: %s", exc)
        return {"error": str(exc)}

    # Stringify dates for JSON friendliness
    for r in [row, *alternatives, *chain]:
        if r and r.get("decided_on"):
            r["decided_on"] = r["decided_on"].isoformat()

    return {
        "decision": row,
        "alternatives": alternatives,
        "supersedes_chain": chain,
        "banner": banner,
    }


def get_impact_targets(doc_or_decision: str) -> dict:
    """Return every doc affected by a change to the given source.

    `doc_or_decision` may be:
        - A bare or full doc filename (delegates to get_doc_neighborhood)
        - A decision_key (resolves to its source_doc, then neighborhood)

    Returns:
        {
            "anchor": <doc filename or decision key>,
            "anchor_kind": "doc" | "decision",
            "decision": <row from decisions, or None>,
            "neighborhood": <full output of get_doc_neighborhood>,
        }
    """
    from src.neighborhood import get_doc_neighborhood

    # Try as decision key first
    decision_row: dict | None = None
    anchor_doc: str | None = None
    anchor_kind = "doc"

    if isinstance(doc_or_decision, str) and "/" not in doc_or_decision and not doc_or_decision.endswith(".md"):
        try:
            conn = _connect()
            try:
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
                        if decision_row.get("decided_on"):
                            decision_row["decided_on"] = decision_row["decided_on"].isoformat()
            finally:
                conn.close()
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
