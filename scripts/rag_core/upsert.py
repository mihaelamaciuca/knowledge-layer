"""SQL surface for doc_chunks upserts.

The column set includes the authority, provenance, graph, and outline
fields plus `tsv`. Those columns are nullable; callers that don't have
a value pass None.

`tsv` is computed by Postgres from `content` via `to_tsvector('english', ...)`
at insert time, the caller never sends a tsvector value.
"""
import hashlib

UPSERT_SQL = """
INSERT INTO doc_chunks (
    source_file, section_header, area_number, doc_type,
    content, content_hash, embedding, updated_at,
    status, supersedes, doc_date,
    git_sha, git_committed_at,
    depends_on, feeds_into, also_touches,
    tsv
) VALUES (
    %s, %s, %s, %s,
    %s, %s, %s::vector, now(),
    %s, %s, %s,
    %s, %s,
    %s, %s, %s,
    to_tsvector('english', %s)
)
ON CONFLICT (content_hash) DO UPDATE SET
    source_file       = EXCLUDED.source_file,
    section_header    = EXCLUDED.section_header,
    area_number       = EXCLUDED.area_number,
    doc_type          = EXCLUDED.doc_type,
    content           = EXCLUDED.content,
    embedding         = EXCLUDED.embedding,
    status            = EXCLUDED.status,
    supersedes        = EXCLUDED.supersedes,
    doc_date          = EXCLUDED.doc_date,
    git_sha           = EXCLUDED.git_sha,
    git_committed_at  = EXCLUDED.git_committed_at,
    depends_on        = EXCLUDED.depends_on,
    feeds_into        = EXCLUDED.feeds_into,
    also_touches      = EXCLUDED.also_touches,
    tsv               = EXCLUDED.tsv,
    updated_at        = now();
"""


def upsert_chunk(cur, *, source_file: str, section_header: str,
                 area_number: int | None, doc_type: str | None,
                 content: str, content_hash: str,
                 embedding_pgvector: str,
                 status: str | None = None,
                 supersedes: str | None = None,
                 doc_date: str | None = None,
                 git_sha: str | None = None,
                 git_committed_at: str | None = None,
                 depends_on: list[str] | None = None,
                 feeds_into: list[str] | None = None,
                 also_touches: list[int] | None = None) -> None:
    """Single-row upsert. The caller manages the connection and the transaction.

    extended fields default to None / empty, callers that don't have them yet
    (legacy code paths) keep working with the original arg shape.
    """
    cur.execute(UPSERT_SQL, (
        source_file,
        section_header,
        area_number,
        doc_type,
        content,
        content_hash,
        embedding_pgvector,
        status,
        supersedes,
        doc_date,
        git_sha,
        git_committed_at,
        depends_on if depends_on is not None else None,
        feeds_into if feeds_into is not None else None,
        also_touches if also_touches is not None else None,
        content,  # tsv source. Postgres tokenises it via to_tsvector('english', ...)
    ))


def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
