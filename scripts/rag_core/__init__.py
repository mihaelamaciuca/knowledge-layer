"""rag_core: shared parsing, chunking, scrubbing, and indexing for the
knowledge layer.

Used by:
    scripts/populate.py            (bulk reindex)
    scripts/sync_changed.py        (Action entry point, incremental sync)
    .github/workflows/sync-to-rag.yml  (calls sync_changed.py)
    scripts/lightweight-action-template.yml  (a copy-into-other-repos workflow that
                                              inlines its own indexer rather than
                                              depending on this package)

Module map:
    frontmatter.py     : YAML frontmatter parser (no PyYAML dependency)
    chunker.py         : markdown chunking by ## with ### / char-split fallback
    scrub.py           : governance scrub for excluded fields (no-op until you populate EXCLUDED_FIELDS)
    outline.py         : section tree extraction
    relationships.py   : frontmatter graph extraction
    embed.py           : OpenAI embedding client with rate-limit delay
    html_tracker.py    : JS-tracker-array parser for capability area HTML
    upsert.py          : doc_chunks INSERT/UPDATE SQL
    sync.py            : high-level per-file processing flow

Imports are lazy: submodules are imported explicitly by callers so a
lightweight tool (e.g. the parity check) does not have to pull `openai`
or `psycopg2` transitively.
"""

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBED_DELAY_SECONDS = 0.1
MAX_CHUNK_CHARS = 4000


def __getattr__(name):
    """Lazy attribute access, `from rag_core import process_markdown_file`
    works without importing every submodule up front."""
    if name in {"chunk_by_h2"}:
        from rag_core.chunker import chunk_by_h2
        return chunk_by_h2
    if name in {"parse_frontmatter"}:
        from rag_core.frontmatter import parse_frontmatter
        return parse_frontmatter
    if name in {"parse_html_tracker"}:
        from rag_core.html_tracker import parse_html_tracker
        return parse_html_tracker
    if name in {"scrub_content"}:
        from rag_core.scrub import scrub_content
        return scrub_content
    if name in {"embed_text", "to_pgvector"}:
        from rag_core.embed import embed_text, to_pgvector
        return {"embed_text": embed_text, "to_pgvector": to_pgvector}[name]
    if name in {"UPSERT_SQL", "upsert_chunk", "sha256_hash"}:
        from rag_core.upsert import UPSERT_SQL, sha256_hash, upsert_chunk
        return {
            "UPSERT_SQL": UPSERT_SQL,
            "upsert_chunk": upsert_chunk,
            "sha256_hash": sha256_hash,
        }[name]
    if name in {"delete_chunks_for_files", "fetch_existing_hashes",
                "process_html_file", "process_markdown_file"}:
        from rag_core.sync import (
            delete_chunks_for_files,
            fetch_existing_hashes,
            process_html_file,
            process_markdown_file,
        )
        return {
            "delete_chunks_for_files": delete_chunks_for_files,
            "fetch_existing_hashes": fetch_existing_hashes,
            "process_html_file": process_html_file,
            "process_markdown_file": process_markdown_file,
        }[name]
    raise AttributeError(f"module 'rag_core' has no attribute {name!r}")


__all__ = [
    "EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EMBED_DELAY_SECONDS",
    "MAX_CHUNK_CHARS",
    "chunk_by_h2",
    "embed_text",
    "parse_frontmatter",
    "parse_html_tracker",
    "scrub_content",
    "delete_chunks_for_files",
    "fetch_existing_hashes",
    "process_html_file",
    "process_markdown_file",
    "UPSERT_SQL",
    "upsert_chunk",
    "sha256_hash",
    "to_pgvector",
]
