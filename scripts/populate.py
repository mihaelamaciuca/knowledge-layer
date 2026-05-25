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
        )
        if out.returncode != 0 or not out.stdout.strip():
            return (None, None)
        sha, _, committed_at = out.stdout.strip().partition(" ")
        return (sha or None, committed_at or None)
    except (FileNotFoundError, OSError):
        return (None, None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-dir", required=True, help="Path to the docs/ folder")
    parser.add_argument("--full-reindex", action="store_true",
                        help="Delete all existing chunks before indexing")
    args = parser.parse_args()

    docs_dir = Path(args.docs_dir).resolve()
    if not docs_dir.is_dir():
        print(f"Error: {docs_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Repo root for git provenance lookups (docs/ is usually one level below).
    repo_root = docs_dir.parent

    for var in ("DATABASE_URL", "OPENAI_API_KEY"):
        if not os.environ.get(var):
            print(f"Error: {var} is not set", file=sys.stderr)
            sys.exit(1)

    print("Script started")
    print(f"  DATABASE_URL:  {os.environ['DATABASE_URL'][:40]}...")
    print(f"  OPENAI_API_KEY: {os.environ['OPENAI_API_KEY'][:10]}...")

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    cur = conn.cursor()
    openai_client = get_openai_client()

    if args.full_reindex:
        print("Full reindex requested, deleting all existing chunks...")
        cur.execute("DELETE FROM doc_chunks")
        print("  Cleared.")

    print("Fetching existing chunk hashes from Postgres...")
    existing_hashes: set[str] = set()
    try:
        existing_hashes = fetch_existing_hashes(cur)
        print(f"  Found {len(existing_hashes)} existing chunks")
    except Exception as exc:
        print(f"  Warning: could not fetch existing hashes ({exc}), will attempt all upserts")
        conn.rollback()

    total_files = 0
    total_upserted = 0
    total_skipped = 0

    # ── Markdown files ────────────────────────────────────────────────────
    md_files = sorted(docs_dir.rglob("*.md"))
    print(f"Found {len(md_files)} Markdown files in {docs_dir}\n")

    for md_path in md_files:
        rel_path = md_path.relative_to(docs_dir)
        source_file = f"{REPO_PREFIX}/docs/{rel_path}"
        total_files += 1

        git_sha, git_committed_at = _file_git_provenance(md_path, repo_root)

        try:
            upserted, skipped = process_markdown_file(
                cur,
                file_path=md_path,
                source_file=source_file,
                openai_client=openai_client,
                existing_hashes=existing_hashes,
                delete_before_upsert=False,
                git_sha=git_sha,
                git_committed_at=git_committed_at,
            )
        except Exception as exc:
            print(f"  [{total_files}/{len(md_files)}] {rel_path}, error: {exc}")
            conn.rollback()
            continue

        total_upserted += upserted
        total_skipped += skipped
        total_chunks = upserted + skipped
        if total_chunks == 0:
            print(f"  [{total_files}/{len(md_files)}] {rel_path}, no chunks, skipping")
        else:
            print(
                f"  [{total_files}/{len(md_files)}] {rel_path}, "
                f"{total_chunks} chunks: {upserted} upserted, {skipped} skipped"
            )

    # ── HTML tracker files ────────────────────────────────────────────────
    html_files = sorted(docs_dir.rglob("*.html"))
    if html_files:
        print(f"\nFound {len(html_files)} HTML files in {docs_dir}\n")

    for html_path in html_files:
        rel_path = html_path.relative_to(docs_dir)
        source_file = f"{REPO_PREFIX}/docs/{rel_path}"
        total_files += 1

        git_sha, git_committed_at = _file_git_provenance(html_path, repo_root)

        try:
            upserted, skipped = process_html_file(
                cur,
                file_path=html_path,
                source_file=source_file,
                openai_client=openai_client,
                existing_hashes=existing_hashes,
                delete_before_upsert=False,
                git_sha=git_sha,
                git_committed_at=git_committed_at,
            )
        except Exception as exc:
            print(f"  {rel_path}, error: {exc}")
            conn.rollback()
            continue

        total_upserted += upserted
        total_skipped += skipped
        total_chunks = upserted + skipped
        if total_chunks == 0:
            print(f"  {rel_path}, no chunks, skipping")
        else:
            print(
                f"  {rel_path}, "
                f"{total_chunks} chunks: {upserted} upserted, {skipped} skipped"
            )

    cur.close()
    conn.close()

    print(f"\nDone.")
    print(f"  Files processed:  {total_files}")
    print(f"  Chunks upserted:  {total_upserted}")
    print(f"  Chunks skipped:   {total_skipped}")


if __name__ == "__main__":
    main()
