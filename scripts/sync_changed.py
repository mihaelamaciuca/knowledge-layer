#!/usr/bin/env python3
"""Incremental indexer entry point, called by the GitHub Action on push to main.

For each changed file: delete its existing chunks, re-process, embed, upsert.
For each deleted file: drop all its chunks.

Usage:
    python3 scripts/sync_changed.py \
        --repo-prefix {{PROJECT_NAME}} \
        --changed "docs/a.md docs/b.html" \
        --deleted "docs/c.md"

Empty `--changed` / `--deleted` are accepted as no-ops. Either may be a
single space-separated string (matching the GitHub Action step output
shape) or repeated --changed args.

Environment:
    DATABASE_URL    Postgres connection string
    OPENAI_API_KEY  (only required when `--changed` is non-empty)
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_core import (
    delete_chunks_for_files,
    process_html_file,
    process_markdown_file,
)
from rag_core.embed import get_client as get_openai_client


def _committed_at_for_file(path: Path) -> str | None:
    """ISO-8601 commit timestamp of the file's most recent commit. None on failure."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%cI", "--", str(path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return out.stdout.strip()
    except (FileNotFoundError, OSError):
        return None


def _split_files(arg: str | None) -> list[str]:
    """Split a space-separated file list, dropping empties."""
    if not arg:
        return []
    return [p for p in arg.split() if p.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-prefix", default="{{PROJECT_NAME}}",
                        help="Prefix for source_file values (e.g. 'myapp' or 'myapp-api')")
    parser.add_argument("--changed", default="",
                        help="Space-separated changed/added file paths (repo-relative)")
    parser.add_argument("--deleted", default="",
                        help="Space-separated deleted file paths (repo-relative)")
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA"),
                        help="Commit SHA to stamp on every chunk (defaults to GITHUB_SHA env var)")
    args = parser.parse_args()

    git_sha = args.git_sha or None

    changed = _split_files(args.changed)
    deleted = _split_files(args.deleted)

    if not changed and not deleted:
        print("No changed or deleted files. Nothing to do.")
        return

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        sys.exit(1)
    if changed and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set (required for embedding)", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = True
    cur = conn.cursor()

    total_upserted = 0

    # ── Process changed files ────────────────────────────────────────────
    if changed:
        openai_client = get_openai_client()
        for rel in changed:
            p = Path(rel)
            if not p.exists():
                print(f"  Skip (missing): {rel}")
                continue

            source_file = f"{args.repo_prefix}/{rel}"
            git_committed_at = _committed_at_for_file(p)

            try:
                if p.suffix == ".html":
                    upserted, _ = process_html_file(
                        cur,
                        file_path=p,
                        source_file=source_file,
                        openai_client=openai_client,
                        existing_hashes=None,  # incremental mode: always re-embed
                        delete_before_upsert=True,
                        git_sha=git_sha,
                        git_committed_at=git_committed_at,
                    )
                else:
                    upserted, _ = process_markdown_file(
                        cur,
                        file_path=p,
                        source_file=source_file,
                        openai_client=openai_client,
                        existing_hashes=None,
                        delete_before_upsert=True,
                        git_sha=git_sha,
                        git_committed_at=git_committed_at,
                    )
            except Exception as exc:
                print(f"  Error processing {rel}: {exc}")
                continue

            total_upserted += upserted
            print(f"  {rel}: upserted {upserted} chunks")

    # ── Process deleted files ────────────────────────────────────────────
    if deleted:
        sources = [f"{args.repo_prefix}/{rel}" for rel in deleted]
        deleted_count = delete_chunks_for_files(cur, sources)
        for s in sources:
            print(f"  Deleted chunks for {s}")
        print(f"  Total deleted: {deleted_count}")

    cur.close()
    conn.close()

    print(f"\nDone. Total chunks upserted: {total_upserted}")


if __name__ == "__main__":
    main()
