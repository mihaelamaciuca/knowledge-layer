"""High-level per-file processing flow shared by populate and the Action.

Two entry points:
    process_markdown_file : chunk, scrub, embed, upsert one .md file
    process_html_file     : same flow for .html tracker files

Two utilities for the callers:
    fetch_existing_hashes  : pre-fetch hashes for skip-on-unchanged
    delete_chunks_for_files: bulk delete by source_file

The functions take an open cursor; the caller owns the connection and
commit/rollback policy. Connection autocommit is the v1 default.

v2 additions:
    - v2 fields (status, supersedes, doc_date, depends_on, feeds_into,
      also_touches) extracted from frontmatter and stamped on every chunk.
    - Provenance (git_sha, git_committed_at) passed in by the caller and
      stamped on every chunk.
    - Chunk preamble: every chunk's content is prefixed with a generated
      line that gives the embedding model document-level context.
"""
from datetime import date
from pathlib import Path

from rag_core.chunker import chunk_by_h2
from rag_core.embed import embed_batch, embed_text, to_pgvector
from rag_core.frontmatter import parse_frontmatter_v2
from rag_core.html_tracker import parse_html_tracker
from rag_core.outline import (
    delete_outline_for_source,
    extract_outline,
    upsert_outline,
)
from rag_core.relationships import (
    delete_relationships_for_source,
    extract_relationships,
    replace_relationships,
)
from rag_core.scrub import scrub_content
from rag_core.upsert import sha256_hash, upsert_chunk


def fetch_existing_hashes(cur) -> set[str]:
    """Fetch all known content_hash values for skip-on-unchanged logic."""
    cur.execute("SELECT content_hash FROM doc_chunks")
    return {row[0] for row in cur.fetchall()}


def delete_chunks_for_files(cur, source_files: list[str]) -> int:
    """Delete all chunks for the given source_file values. Returns count deleted.

    Also drops the corresponding doc_relationships rows so the graph
    stays in sync with the chunk index.
    """
    if not source_files:
        return 0
    cur.execute(
        "DELETE FROM doc_chunks WHERE source_file = ANY(%s)",
        (source_files,),
    )
    chunks_deleted = cur.rowcount
    cur.execute(
        "DELETE FROM doc_relationships WHERE source_file = ANY(%s)",
        (source_files,),
    )
    cur.execute(
        "DELETE FROM doc_outlines WHERE source_file = ANY(%s)",
        (source_files,),
    )
    return chunks_deleted


# ─── v2 helpers ──────────────────────────────────────────────────────────

def _normalise_scalar(value: str | None) -> str | None:
    """Convert YAML 'null' / empty strings to None."""
    if value is None:
        return None
    if value in ("null", "Null", "NULL", "~", ""):
        return None
    return value.strip().strip('"\'')


def _parse_date(value: str | None) -> str | None:
    """Validate a YAML date string and return ISO format, or None."""
    norm = _normalise_scalar(value)
    if not norm:
        return None
    try:
        return date.fromisoformat(norm).isoformat()
    except ValueError:
        return None


def _build_preamble(*, source_file: str, doc_type: str | None,
                    status: str | None, area_number: int | None,
                    section_header: str) -> str:
    """Construct the chunk preamble line.

    Format:
        File: {{PROJECT_NAME}}/docs/X.md · Type: spec · Status: complete · Area 4. Section header
        <blank line>
        <content>

    Missing fields render as `unknown` so the line is always well-formed.
    """
    return (
        f"File: {source_file} · "
        f"Type: {doc_type or 'unknown'} · "
        f"Status: {status or 'unknown'} · "
        f"Area {area_number if area_number is not None else 'unknown'}, "
        f"{section_header}"
    )


# ─── core processing ────────────────────────────────────────────────────

def _process_chunks(
    cur,
    *,
    chunks: list[tuple[str, str]],
    source_file: str,
    area_number: int | None,
    doc_type: str | None,
    status: str | None,
    supersedes: str | None,
    doc_date: str | None,
    depends_on: list[str] | None,
    feeds_into: list[str] | None,
    also_touches: list[int] | None,
    git_sha: str | None,
    git_committed_at: str | None,
    openai_client,
    existing_hashes: set[str] | None,
) -> tuple[int, int]:
    """Embed and upsert a list of (header, content) chunks. Returns (upserted, skipped).

    Three-pass pipeline:
        Pass 1: scrub + preamble + hash; drop chunks already indexed
        Pass 2: batch-embed the survivors in one OpenAI round-trip
        Pass 3: upsert each with its embedding + v2 fields + provenance

    Batching is the throughput win: 5,260 chunks at ~200ms per call become
    ~53 batched calls. Hash-based skip happens in pass 1 so we never pay
    for embedding a chunk we already have.
    """
    upserted = 0
    skipped = 0

    # Pass 1: scrub + preamble + hash; collect what needs embedding.
    pending: list[dict] = []
    for section_header, content in chunks:
        scrubbed = scrub_content(content)
        preamble = _build_preamble(
            source_file=source_file,
            doc_type=doc_type,
            status=status,
            area_number=area_number,
            section_header=section_header,
        )
        embedded_content = f"{preamble}\n\n{scrubbed}"
        content_hash = sha256_hash(embedded_content)

        if existing_hashes is not None and content_hash in existing_hashes:
            skipped += 1
            continue

        pending.append({
            "section_header": section_header,
            "embedded_content": embedded_content,
            "content_hash": content_hash,
        })

    if not pending:
        return upserted, skipped

    # Pass 2: batch-embed in one or a handful of OpenAI calls.
    embeddings = embed_batch(
        [item["embedded_content"] for item in pending],
        client=openai_client,
    )

    # Pass 3: upsert each row with its embedding + frontmatter fields.
    for item, embedding in zip(pending, embeddings):
        upsert_chunk(
            cur,
            source_file=source_file,
            section_header=item["section_header"],
            area_number=area_number,
            doc_type=doc_type,
            content=item["embedded_content"],
            content_hash=item["content_hash"],
            embedding_pgvector=to_pgvector(embedding),
            status=status,
            supersedes=supersedes,
            doc_date=doc_date,
            git_sha=git_sha,
            git_committed_at=git_committed_at,
            depends_on=depends_on,
            feeds_into=feeds_into,
            also_touches=also_touches,
        )
        if existing_hashes is not None:
            existing_hashes.add(item["content_hash"])
        upserted += 1

    return upserted, skipped


def _extract_v2_fields(metadata: dict) -> dict:
    """Pull the v2 indexer columns out of parsed frontmatter."""
    area_number: int | None = None
    raw_area = metadata.get("area")
    if raw_area is not None:
        try:
            area_number = int(raw_area)
        except (ValueError, TypeError):
            pass

    return {
        "area_number": area_number,
        "doc_type": _normalise_scalar(metadata.get("type")),
        "status": _normalise_scalar(metadata.get("status")),
        "supersedes": _normalise_scalar(metadata.get("supersedes")),
        "doc_date": _parse_date(metadata.get("date")),
        "depends_on": metadata.get("depends-on") or [],
        "feeds_into": metadata.get("feeds-into") or [],
        "also_touches": metadata.get("also-touches") or [],
    }


def process_markdown_file(
    cur,
    *,
    file_path: Path,
    source_file: str,
    openai_client=None,
    existing_hashes: set[str] | None = None,
    delete_before_upsert: bool = False,
    git_sha: str | None = None,
    git_committed_at: str | None = None,
) -> tuple[int, int]:
    """Process one markdown file end-to-end.

    Returns (upserted, skipped). Caller controls connection.

    `delete_before_upsert=True` deletes existing chunks for this source_file
    before re-inserting (Action incremental mode). The bulk indexer uses
    hash-based skip and does not delete.

    `git_sha` and `git_committed_at` are stamped on every chunk for the
    file. Callers without provenance pass None.
    """
    text = file_path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter_v2(text)
    v2 = _extract_v2_fields(metadata)

    chunks = chunk_by_h2(body)
    if not chunks:
        return (0, 0)

    if delete_before_upsert:
        delete_chunks_for_files(cur, [source_file])

    result = _process_chunks(
        cur,
        chunks=chunks,
        source_file=source_file,
        git_sha=git_sha,
        git_committed_at=git_committed_at,
        openai_client=openai_client,
        existing_hashes=existing_hashes,
        **v2,
    )

    # Refresh the doc_relationships rows for this file. Replace-on-write
    # so deleted frontmatter edges don't linger.
    edges = extract_relationships(metadata)
    replace_relationships(cur, source_file, edges)

    # Refresh the doc_outlines row for this file. Single-row upsert.
    outline = extract_outline(body)
    if outline:
        upsert_outline(cur, source_file, outline)
    else:
        delete_outline_for_source(cur, source_file)

    return result


def process_html_file(
    cur,
    *,
    file_path: Path,
    source_file: str,
    openai_client=None,
    existing_hashes: set[str] | None = None,
    delete_before_upsert: bool = False,
    git_sha: str | None = None,
    git_committed_at: str | None = None,
) -> tuple[int, int]:
    """Process one HTML tracker file end-to-end.

    Same contract as process_markdown_file. Returns (upserted, skipped).

    HTML trackers don't have YAML frontmatter, so the v2 fields default
    to None / empty. doc_type is derived from filename by the HTML parser.
    """
    html_text = file_path.read_text(encoding="utf-8")
    html_chunks = parse_html_tracker(
        html_text,
        source_file=source_file,
        filename_stem=file_path.stem,
    )
    if not html_chunks:
        return (0, 0)

    if delete_before_upsert:
        delete_chunks_for_files(cur, [source_file])

    upserted = 0
    skipped = 0

    # Pass 1: scrub + preamble + hash; collect what needs embedding.
    pending: list[dict] = []
    for chunk in html_chunks:
        scrubbed = scrub_content(chunk["content"])
        preamble = _build_preamble(
            source_file=chunk["source_file"],
            doc_type=chunk["doc_type"],
            status=None,
            area_number=chunk["area_number"],
            section_header=chunk["section_header"],
        )
        embedded_content = f"{preamble}\n\n{scrubbed}"
        content_hash = sha256_hash(embedded_content)

        if existing_hashes is not None and content_hash in existing_hashes:
            skipped += 1
            continue

        pending.append({
            "chunk": chunk,
            "embedded_content": embedded_content,
            "content_hash": content_hash,
        })

    if not pending:
        return upserted, skipped

    # Pass 2: batch-embed.
    embeddings = embed_batch(
        [item["embedded_content"] for item in pending],
        client=openai_client,
    )

    # Pass 3: upsert each row.
    for item, embedding in zip(pending, embeddings):
        chunk = item["chunk"]
        upsert_chunk(
            cur,
            source_file=chunk["source_file"],
            section_header=chunk["section_header"],
            area_number=chunk["area_number"],
            doc_type=chunk["doc_type"],
            content=item["embedded_content"],
            content_hash=item["content_hash"],
            embedding_pgvector=to_pgvector(embedding),
            git_sha=git_sha,
            git_committed_at=git_committed_at,
        )
        if existing_hashes is not None:
            existing_hashes.add(item["content_hash"])
        upserted += 1

    return upserted, skipped
