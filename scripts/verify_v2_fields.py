#!/usr/bin/env python3
"""Verify the v2 indexer fields are populated after a full reindex.

Three checks:

    1. Every chunk has a chunk preamble, content starts with "File: "
    2. Every chunk has tsv populated (Postgres-side to_tsvector)
    3. At least 80% of chunks have git_sha + git_committed_at set
       (a small fraction of untracked / brand-new files may lack git
       provenance, full block is suspicious, partial coverage is fine)

Exit 0 on pass, 1 on any failure. Runs after the reindex workflow as
the post-reindex gate.
"""
import os
import sys

import psycopg2

MIN_PROVENANCE_FRACTION = 0.80


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM doc_chunks")
    (total,) = cur.fetchone()
    if total == 0:
        print("Error: doc_chunks is empty, has the reindex run?", file=sys.stderr)
        return 1

    print(f"Total chunks: {total}")

    # ── 1. Chunk preamble on every chunk ─────────────────────────────────
    cur.execute("SELECT count(*) FROM doc_chunks WHERE content NOT LIKE 'File: %'")
    (no_preamble,) = cur.fetchone()
    print(f"Chunks missing preamble:           {no_preamble}")
    if no_preamble:
        cur.execute("""
            SELECT source_file, section_header, substring(content from 1 for 80)
            FROM doc_chunks
            WHERE content NOT LIKE 'File: %'
            LIMIT 5
        """)
        for row in cur.fetchall():
            print(f"  {row[0]} → {row[1]}")
            print(f"    starts: {row[2]!r}")

    # ── 2. tsv populated on every chunk ──────────────────────────────────
    cur.execute("SELECT count(*) FROM doc_chunks WHERE tsv IS NULL")
    (no_tsv,) = cur.fetchone()
    print(f"Chunks missing tsv:                {no_tsv}")

    # ── 3. Provenance coverage ───────────────────────────────────────────
    cur.execute("SELECT count(*) FROM doc_chunks WHERE git_sha IS NOT NULL")
    (with_sha,) = cur.fetchone()
    cur.execute("SELECT count(*) FROM doc_chunks WHERE git_committed_at IS NOT NULL")
    (with_committed_at,) = cur.fetchone()
    sha_fraction = with_sha / total
    committed_fraction = with_committed_at / total
    print(f"Chunks with git_sha:               {with_sha} ({sha_fraction:.1%})")
    print(f"Chunks with git_committed_at:      {with_committed_at} ({committed_fraction:.1%})")

    # ── 4. v2 field coverage (informational) ─────────────────────────────
    cur.execute("SELECT count(*) FROM doc_chunks WHERE status IS NOT NULL")
    (with_status,) = cur.fetchone()
    cur.execute("SELECT count(*) FROM doc_chunks WHERE doc_date IS NOT NULL")
    (with_date,) = cur.fetchone()
    cur.execute("SELECT count(*) FROM doc_chunks WHERE depends_on IS NOT NULL AND array_length(depends_on, 1) > 0")
    (with_deps,) = cur.fetchone()
    print(f"Chunks with status:                {with_status} ({with_status/total:.1%})")
    print(f"Chunks with doc_date:              {with_date} ({with_date/total:.1%})")
    print(f"Chunks with depends_on (non-empty):{with_deps} ({with_deps/total:.1%})")

    cur.close()
    conn.close()

    failures = []
    if no_preamble:
        failures.append(f"{no_preamble} chunks missing the preamble line")
    if no_tsv:
        failures.append(f"{no_tsv} chunks missing tsv")
    if sha_fraction < MIN_PROVENANCE_FRACTION:
        failures.append(f"git_sha coverage {sha_fraction:.1%} below threshold {MIN_PROVENANCE_FRACTION:.0%}")
    if committed_fraction < MIN_PROVENANCE_FRACTION:
        failures.append(f"git_committed_at coverage {committed_fraction:.1%} below threshold {MIN_PROVENANCE_FRACTION:.0%}")

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nv2 verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
