"""Hybrid (vector + lexical) similarity search over doc_chunks.

Used by the FastMCP `search_docs` tool and the FastAPI `/search` endpoint.

Hybrid scoring: combined = VECTOR_WEIGHT * vec_sim + LEXICAL_WEIGHT * lex_rank
A row qualifies for ranking if it beats either signal: vector cosine
similarity above MIN_SIMILARITY, OR a non-empty `ts_rank` match. The
combined score drives ordering with a deterministic tiebreaker on `id`.
Pure-vector queries still return the natural-language top-k; pure-
lexical hits (exact phrase, decision id, advisory-lock number) surface
even when their embeddings are far from the query.

Authority awareness: rows with `status = 'superseded'` are excluded by
default. Pass `include_superseded=True` to include them; they return
with a `[SUPERSEDED, see <target>]` banner prepended to `content`.

Every call writes a row to `query_log` (scrubbed query + top-k ids +
latency + caller) including on the error path, so misconfiguration is
visible in telemetry. The caller field is best-effort: FastMCP tools
do not have a direct handle on the HTTP context, so we tag MCP calls
"mcp" and direct REST calls "rest".
"""
import logging
import os
import time
import uuid

from rag_core.embed import get_client
from rag_core.scrub import scrub_content
from src.db import connection

log = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_K = 20
DEFAULT_K = 10

MIN_SIMILARITY = 0.35
VECTOR_WEIGHT = 0.7
LEXICAL_WEIGHT = 0.3


def embed_query(query: str) -> list[float]:
    client = get_client()
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=query,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    return response.data[0].embedding


def _build_search_sql(filters: dict) -> tuple[str, list]:
    """Build the hybrid search SQL with dynamic filter clauses.

    Returns (sql, extra_params_after_filters). Caller appends the
    embedding/query/threshold params at the start and limit at the end.
    """
    where_extras: list[str] = []
    extras: list = []

    if filters.get("status"):
        where_extras.append("status = %s")
        extras.append(filters["status"])
    if filters.get("area") is not None:
        where_extras.append("area_number = %s")
        extras.append(filters["area"])
    if filters.get("doc_type"):
        where_extras.append("doc_type = %s")
        extras.append(filters["doc_type"])
    if not filters.get("include_superseded"):
        where_extras.append("(status IS NULL OR status <> 'superseded')")

    where_clause = ""
    if where_extras:
        where_clause = "AND " + " AND ".join(where_extras)

    sql = f"""
    WITH ranked AS (
        SELECT
            id,
            source_file, section_header, area_number, doc_type, content,
            status, supersedes, doc_date,
            git_sha,
            to_char(git_committed_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS git_committed_at,
            depends_on, feeds_into, also_touches,
            1 - (embedding <=> %s::vector) AS vec_sim,
            ts_rank(tsv, plainto_tsquery('english', %s)) AS lex_rank,
            to_char(updated_at, 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS updated_at
        FROM doc_chunks
        WHERE (
            (1 - (embedding <=> %s::vector) >= %s)
            OR tsv @@ plainto_tsquery('english', %s)
        )
        {where_clause}
    )
    SELECT *, ({VECTOR_WEIGHT} * vec_sim + {LEXICAL_WEIGHT} * lex_rank) AS score
    FROM ranked
    ORDER BY score DESC, id ASC
    LIMIT %s;
    """
    return sql, extras


def _apply_supersession_banner(rows: list[dict]) -> list[dict]:
    """Prepend a status banner to content for superseded / needs-review rows."""
    out: list[dict] = []
    for row in rows:
        status = row.get("status")
        if status == "superseded":
            target = row.get("supersedes") or "(target not declared)"
            row = {
                **row,
                "content": f"[SUPERSEDED, see {target}]\n\n" + (row.get("content") or ""),
            }
        elif status == "needs-review":
            row = {
                **row,
                "content": "[NEEDS REVIEW, flagged by hygiene loop]\n\n" + (row.get("content") or ""),
            }
        out.append(row)
    return out


def _log_query(*, query: str, top_k_ids: list[uuid.UUID],
               latency_ms: int, caller: str, error: str | None = None) -> None:
    """Write one row to query_log using a short-lived connection.

    Best-effort: failures here are logged and swallowed so the original
    search call's outcome is not obscured by telemetry trouble.
    """
    try:
        scrubbed = scrub_content(query)
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO query_log (query_scrubbed, top_k_ids, latency_ms, caller)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        (scrubbed[:500] + (f" [ERROR: {error[:200]}]" if error else "")),
                        top_k_ids,
                        latency_ms,
                        caller,
                    ),
                )
            conn.commit()
    except Exception as exc:
        log.warning("query_log insert failed: %s", exc)


def search_docs(
    query: str,
    k: int = DEFAULT_K,
    *,
    status: str | None = None,
    area: int | None = None,
    doc_type: str | None = None,
    include_superseded: bool = False,
    caller: str = "mcp",
) -> list[dict] | dict:
    """Hybrid vector+lexical search over the index.

    Returns a list of top-k row dicts on success. On error, returns a
    `{"error": "<message>", "results": []}` dict so callers can
    distinguish "no results" from "DB unreachable".
    """
    k = min(max(1, k), MAX_K)
    start = time.monotonic()

    try:
        embedding = embed_query(query)
    except Exception as exc:
        log.error("embedding failed: %s", exc)
        latency_ms = int((time.monotonic() - start) * 1000)
        _log_query(query=query, top_k_ids=[], latency_ms=latency_ms,
                   caller=caller, error=f"embedding: {exc}")
        return {"error": f"embedding failed: {exc}", "results": []}
    embedding_str = str(embedding)

    filters = {
        "status": status,
        "area": area,
        "doc_type": doc_type,
        "include_superseded": include_superseded,
    }
    sql, extras = _build_search_sql(filters)
    params = [embedding_str, query, embedding_str, MIN_SIMILARITY, query] + extras + [k]

    rows: list[dict] = []
    error_msg: str | None = None
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [desc[0] for desc in cur.description]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                rows = _apply_supersession_banner(rows)
            conn.commit()
    except Exception as exc:
        log.error("hybrid search failed: %s", exc)
        error_msg = str(exc)

    latency_ms = int((time.monotonic() - start) * 1000)
    _log_query(
        query=query,
        top_k_ids=[r["id"] for r in rows] if rows else [],
        latency_ms=latency_ms,
        caller=caller,
        error=error_msg,
    )

    if error_msg is not None:
        return {"error": error_msg, "results": []}
    return rows


HEALTH_SQL = """
SELECT source_file,
       count(*) AS chunk_count,
       to_char(min(updated_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS oldest_chunk,
       to_char(max(updated_at), 'YYYY-MM-DD"T"HH24:MI:SS"Z"') AS newest_chunk,
       max(updated_at) < now() - interval '24 hours' AS is_stale
FROM doc_chunks
GROUP BY source_file
ORDER BY max(updated_at) ASC;
"""


def check_index_health() -> dict:
    try:
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(HEALTH_SQL)
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
    except Exception as exc:
        log.error("index health check failed: %s", exc)
        return {"error": str(exc)}

    files = [dict(zip(cols, row)) for row in rows]
    stale = [f for f in files if f.get("is_stale")]
    total = sum(f["chunk_count"] for f in files)

    return {
        "total_chunks": total,
        "total_files": len(files),
        "stale_files": stale,
        "files": files,
    }
