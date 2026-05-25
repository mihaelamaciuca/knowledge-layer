"""Dependency-graph neighborhood lookup for the MCP tool `get_doc_neighborhood`.

Given a doc filename (bare form like `10-dec-pricing` OR full form like
`{{PROJECT_NAME}}/docs/10-dec-pricing.md`), returns:

    - depends_on, outgoing depends-on edges with target metadata
    - feeds_into, outgoing feeds-into edges with target metadata
    - also_touches, area numbers this doc declares
    - supersedes_chain, chain of prior versions, oldest first
    - depended_on_by, inverse edges (who depends on this doc)
    - feeds_from, inverse edges (who feeds this doc)
    - warnings, dangling refs (target doesn't exist as a doc)

Closes Contract 1. Impact-target check, in 00-spec-retrieval-contract.
"""
import logging

from rag_core.relationships import to_bare, to_full
from src.db import connection

log = logging.getLogger(__name__)


def _fetch_doc_meta(cur, source_files: list[str]) -> dict:
    """Look up status / doc_date / git_committed_at for a list of source_files."""
    if not source_files:
        return {}
    cur.execute(
        """
        SELECT source_file,
               max(status) AS status,
               max(supersedes) AS supersedes,
               max(doc_date) AS doc_date,
               to_char(max(git_committed_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS git_committed_at
        FROM doc_chunks
        WHERE source_file = ANY(%s)
        GROUP BY source_file
        """,
        (source_files,),
    )
    return {
        row[0]: {
            "status": row[1],
            "supersedes": row[2],
            "doc_date": row[3].isoformat() if row[3] else None,
            "git_committed_at": row[4],
        }
        for row in cur.fetchall()
    }


def _resolve(target: str, doc_meta: dict, repo: str = "{{PROJECT_NAME}}") -> dict:
    """Build a target descriptor, bare ref + status + dangling flag."""
    full = to_full(target, repo=repo)
    meta = doc_meta.get(full)
    return {
        "ref": target,
        "source_file": full if meta else None,
        "status": (meta or {}).get("status"),
        "doc_date": (meta or {}).get("doc_date"),
        "git_committed_at": (meta or {}).get("git_committed_at"),
        "dangling": meta is None,
    }


def _build_supersedes_chain(cur, start_full: str) -> list[dict]:
    """Walk the supersedes chain backward from `start_full`.

    Stops at first cycle or 10-step depth. Each entry is a target descriptor.
    """
    chain: list[dict] = []
    seen: set[str] = set()
    current = start_full

    for _ in range(10):
        if current in seen:
            break
        seen.add(current)
        cur.execute(
            "SELECT max(supersedes) FROM doc_chunks WHERE source_file = %s",
            (current,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            break
        prior = row[0]
        prior_full = to_full(prior)
        meta = _fetch_doc_meta(cur, [prior_full])
        chain.append(_resolve(prior, meta))
        current = prior_full

    return chain


def get_doc_neighborhood(filename: str,
                         include_superseded: bool = False) -> dict:
    """Return the dependency-graph neighborhood of `filename`.

    `filename` may be the bare form (`10-dec-pricing`) or the full form
    (`{{PROJECT_NAME}}/docs/10-dec-pricing.md`). The returned dict keys are
    documented in the module docstring.
    """
    bare = to_bare(filename) if "/" in filename else filename
    if bare.endswith(".md"):
        bare = bare[:-3]
    full = to_full(bare)

    try:
        with connection() as conn:
            with conn.cursor() as cur:
                # Outgoing edges, what this doc declares.
                cur.execute(
                    "SELECT relation, target FROM doc_relationships "
                    "WHERE source_file = %s ORDER BY relation, target",
                    (full,),
                )
                outgoing = cur.fetchall()

                # Inverse edges, who points at this doc.
                cur.execute(
                    "SELECT source_file, relation FROM doc_relationships "
                    "WHERE target = %s ORDER BY source_file",
                    (bare,),
                )
                inverse = cur.fetchall()

                # Resolve metadata for every distinct outgoing target.
                file_targets = {to_full(t) for r, t in outgoing
                                if r in ("depends_on", "feeds_into", "supersedes")
                                and not t.startswith("area-")}
                file_targets |= {sf for sf, _ in inverse}
                doc_meta = _fetch_doc_meta(cur, sorted(file_targets))

                supersedes_chain = _build_supersedes_chain(cur, full)
    except Exception as exc:
        log.error("get_doc_neighborhood failed: %s", exc)
        return {"error": str(exc)}

    depends_on: list[dict] = []
    feeds_into: list[dict] = []
    also_touches: list[int] = []
    warnings: list[str] = []

    for relation, target in outgoing:
        if relation == "depends_on":
            res = _resolve(target, doc_meta)
            depends_on.append(res)
            if res["dangling"] and not target.startswith("area-"):
                warnings.append(f"depends_on `{target}` does not resolve to a known doc")
        elif relation == "feeds_into":
            res = _resolve(target, doc_meta)
            feeds_into.append(res)
            if res["dangling"] and not target.startswith("area-"):
                warnings.append(f"feeds_into `{target}` does not resolve to a known doc")
        elif relation == "also_touches":
            try:
                also_touches.append(int(target))
            except (TypeError, ValueError):
                continue

    depended_on_by: list[dict] = []
    feeds_from: list[dict] = []
    for source_file, relation in inverse:
        meta = doc_meta.get(source_file, {})
        descriptor = {
            "ref": to_bare(source_file),
            "source_file": source_file,
            "status": meta.get("status"),
            "doc_date": meta.get("doc_date"),
            "git_committed_at": meta.get("git_committed_at"),
        }
        if not include_superseded and descriptor["status"] == "superseded":
            continue
        if relation == "depends_on":
            depended_on_by.append(descriptor)
        elif relation == "feeds_into":
            feeds_from.append(descriptor)

    return {
        "filename": bare,
        "source_file": full,
        "depends_on": depends_on,
        "feeds_into": feeds_into,
        "also_touches": sorted(set(also_touches)),
        "supersedes_chain": supersedes_chain,
        "depended_on_by": depended_on_by,
        "feeds_from": feeds_from,
        "warnings": warnings,
    }
