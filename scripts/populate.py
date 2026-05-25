#!/usr/bin/env python3
"""Populate doc_chunks in Supabase from a local docs/ folder.

Handles Markdown (.md) and HTML tracker (.html) files. Shared parsing,
chunking, embedding, and upsert logic lives in scripts/rag_core/.

Usage:
    python3 scripts/populate.py --docs-dir docs
    python3 scripts/populate.py --docs-dir docs --full-reindex

Environment variables (loaded from .env if present):
    DATABASE_URL    direct Postgres connection string
    OPENAI_API_KEY  for embedding generation

Exit codes:
    0 - all files processed (some may have produced zero chunks)
    1 - one or more files failed; details printed above
    2 - environment or argument error
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import psycopg2

# Add scripts/ to the path so `from rag_core import ...` resolves from a direct
# `python3 scripts/populate.py` invocation regardless of the CWD.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_core import (
    fetch_existing_hashes,
    process_html_file,
    process_markdown_file,
)
from rag_core.embed import get_client as get_openai_client

REPO_PREFIX = "{{PROJECT_NAME}}"


def _check_placeholder_substituted() -> None:
    """Refuse to run if the {{PROJECT_NAME}} placeholder hasn't been
    swapped by `scripts/init.sh`. Indexing under the literal placeholder
    would poison every chunk's source_file."""
    if "{{" in REPO_PREFIX or "}}" in REPO_PREFIX:
        print(
            f"Error: REPO_PREFIX still contains the literal placeholder "
            f"({REPO_PREFIX!r}). Run `scripts/init.sh` to set your project "
            f"name before indexing.",
            file=sys.stderr,
        )
        sys.exit(2)


def _file_git_provenance(file_path: Path, repo_root: Path) -> tuple[str | None, str | None]:
    """Return (git_sha, git_committed_at_iso) for the file's last commit.

    Falls back to (None, None) if not in a git repo or the file is untracked.
    Used to stamp provenance on every chunk.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%H %cI", "--", str(file_path)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return (None, None)
        sha, _, committed_at = out.stdout.strip().partition(" ")
        return (sha or None, committed_at or None)
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return (None, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", required=True, help="Path to the docs/ folder")
    parser.add_argument("--full-reindex", action="store_true",
                        help="Delete all existing chunks before indexing")
    args = parser.parse_args()

    _check_placeholder_substituted()

    docs_dir = Path(args.docs_dir).resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory", file=sys.stderr)
        return 2

    # Repo root for git provenance lookups (docs/ is usually one level below).
    repo_root = docs_dir.parent

    for var in ("DATABASE_URL", "OPENAI_API_KEY"):
        if not os.environ.get(var):
            print(f"Error: {var} is not set", file=sys.stderr)
            return 2

    print("Script started")
    print(f"  DATABASE_URL:  {os.environ['DATABASE_URL'][:40]}...")
    print(f"  OPENAI_API_KEY: {os.environ['OPENAI_API_KEY'][:10]}...")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    # Explicit transaction control: each file is one transaction so a
    # mid-run failure doesn't leave partial state in the index.
    conn.autocommit = False
    openai_client = get_openai_client()

    if args.full_reindex:
        with conn.cursor() as cur:
            print("Full reindex requested, deleting all existing chunks...")
            cur.execute("DELETE FROM doc_chunks")
            cur.execute("DELETE FROM doc_relationships")
            cur.execute("DELETE FROM doc_outlines")
        conn.commit()
        print("  Cleared doc_chunks, doc_relationships, doc_outlines.")

    # In incremental mode we delete-then-insert per file so edits don't
    # leave orphan chunks from the prior content_hash. existing_hashes is
    # therefore unused on that path (every file is re-embedded).
    delete_before_upsert = not args.full_reindex
    existing_hashes: set[str] | None = None
    if args.full_reindex:
        with conn.cursor() as cur:
            try:
                existing_hashes = fetch_existing_hashes(cur)
                print(f"  Hash cache primed with {len(existing_hashes)} entries")
            except Exception as exc:
                print(f"  Warning: could not fetch existing hashes ({exc})")
                existing_hashes = None
        conn.commit()

    failures: list[str] = []
    total_files = 0
    total_upserted = 0
    total_skipped = 0

    md_files = sorted(docs_dir.rglob("*.md"))
    html_files = sorted(docs_dir.rglob("*.html"))
    print(f"Found {len(md_files)} Markdown + {len(html_files)} HTML files in {docs_dir}\n")

    def _process_one(path: Path, processor) -> None:
        nonlocal total_files, total_upserted, total_skipped
        rel_path = path.relative_to(docs_dir)
        source_file = f"{REPO_PREFIX}/docs/{rel_path}"
        total_files += 1

        git_sha, git_committed_at = _file_git_provenance(path, repo_root)

        try:
            with conn.cursor() as cur:
                upserted, skipped = processor(
                    cur,
                    file_path=path,
                    source_file=source_file,
                    openai_client=openai_client,
                    existing_hashes=existing_hashes,
                    delete_before_upsert=delete_before_upsert,
                    git_sha=git_sha,
                    git_committed_at=git_committed_at,
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            failures.append(str(rel_path))
            print(f"  [FAIL] {rel_path}: {exc}")
            return

        total_upserted += upserted
        total_skipped += skipped
        total_chunks = upserted + skipped
        if total_chunks == 0:
            print(f"  [{total_files}/{len(md_files) + len(html_files)}] {rel_path}, no chunks")
        else:
            print(
                f"  [{total_files}/{len(md_files) + len(html_files)}] {rel_path}, "
                f"{total_chunks} chunks: {upserted} upserted, {skipped} skipped"
            )

    for md_path in md_files:
        _process_one(md_path, process_markdown_file)
    for html_path in html_files:
        _process_one(html_path, process_html_file)

    conn.close()

    print()
    print("Done.")
    print(f"  Files processed:  {total_files}")
    print(f"  Chunks upserted:  {total_upserted}")
    print(f"  Chunks skipped:   {total_skipped}")
    if failures:
        print(f"  Files failed:     {len(failures)}")
        for f in failures:
            print(f"    - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
