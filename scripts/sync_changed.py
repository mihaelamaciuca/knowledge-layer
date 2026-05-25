#!/usr/bin/env python3
"""Incremental indexer entry point, called by the GitHub Action on push to main.

For each changed file: delete its existing chunks, re-process, embed, upsert.
For each deleted file: drop all its chunks.

Usage:
    python3 scripts/sync_changed.py \\
        --repo-prefix {{PROJECT_NAME}} \\
        --changed "docs/a.md docs/b.html" \\
        --deleted "docs/c.md"

Empty `--changed` / `--deleted` are accepted as no-ops. Either may be a
single space-separated string (matching the GitHub Action step output
shape) or repeated --changed args.

Environment:
    DATABASE_URL    Postgres connection string
    OPENAI_API_KEY  (only required when `--changed` is non-empty)

Exit codes:
    0 - all changed/deleted files processed cleanly
    1 - one or more files failed; details printed above
    2 - environment or argument error (incl. unsubstituted {{PROJECT_NAME}})
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

REPO_ROOT = Path(__file__).resolve().parent.parent


def _committed_at_for_file(path: Path) -> str | None:
    """ISO-8601 commit timestamp of the file's most recent commit. None on failure.

    Runs `git log` with cwd set to the repo root so callers can invoke
    this script from anywhere and still get correct provenance.
    """
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%cI", "--", str(path)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        return out.stdout.strip()
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None


def _split_files(arg: str | None) -> list[str]:
    """Split a space-separated file list, dropping empties."""
    if not arg:
        return []
    return [p for p in arg.split() if p.strip()]


def main() -> int:
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

    if "{{" in args.repo_prefix or "}}" in args.repo_prefix:
        print(
            f"Error: --repo-prefix still contains the literal placeholder "
            f"({args.repo_prefix!r}). Run `scripts/init.sh` to set your project "
            f"name before syncing.",
            file=sys.stderr,
        )
        return 2

    git_sha = args.git_sha or None

    changed = _split_files(args.changed)
    deleted = _split_files(args.deleted)

    if not changed and not deleted:
        print("No changed or deleted files. Nothing to do.")
        return 0

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2
    if changed and not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set (required for embedding)", file=sys.stderr)
        return 2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    # Explicit transaction control: each file is one transaction so a
    # mid-run failure doesn't leave partial state in the index.
    conn.autocommit = False

    failures: list[str] = []
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
                with conn.cursor() as cur:
                    if p.suffix == ".html":
                        upserted, _ = process_html_file(
                            cur,
                            file_path=p,
                            source_file=source_file,
                            openai_client=openai_client,
                            existing_hashes=None,
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
                conn.commit()
            except Exception as exc:
                conn.rollback()
                failures.append(rel)
                print(f"  [FAIL] {rel}: {exc}")
                continue

            total_upserted += upserted
            print(f"  {rel}: upserted {upserted} chunks")

    # ── Process deleted files ────────────────────────────────────────────
    if deleted:
        sources = [f"{args.repo_prefix}/{rel}" for rel in deleted]
        try:
            with conn.cursor() as cur:
                deleted_count = delete_chunks_for_files(cur, sources)
            conn.commit()
            for s in sources:
                print(f"  Deleted chunks for {s}")
            print(f"  Total deleted: {deleted_count}")
        except Exception as exc:
            conn.rollback()
            failures.append("(delete batch)")
            print(f"  [FAIL] delete batch: {exc}")

    conn.close()

    print()
    print(f"Done. Total chunks upserted: {total_upserted}")
    if failures:
        print(f"Files failed: {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
