#!/usr/bin/env python3
"""Verify the governance scrub did its job.

Counts rows in doc_chunks whose content still contains an unscrubbed
value-bearing assignment of one of the configured excluded fields.
Exit 0 if zero, exit 1 otherwise (and print sample rows).

The field list is read from `rag_core.scrub.EXCLUDED_FIELDS` at runtime,
so the verifier auto-adapts to project configuration. If EXCLUDED_FIELDS
is empty, the verifier exits 0 immediately.

Used by .github/workflows/reindex.yml as the post-reindex gate. Also
runnable manually with DATABASE_URL set.
"""
import os
import re
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rag_core.scrub import EXCLUDED_FIELDS


def main() -> int:
    if not EXCLUDED_FIELDS:
        print("No EXCLUDED_FIELDS configured in rag_core.scrub, nothing to verify.")
        return 0

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    # Postgres POSIX regex flavour (\m = word-start, ~* = case-insensitive).
    # Mirrors rag_core.scrub strict mode: quoted value with any sep, OR
    # bare token after `=`.
    alternation = "|".join(re.escape(f) for f in EXCLUDED_FIELDS)
    quoted_pattern = (
        f"\\m({alternation})"
        "[\"']?\\s*[:=]\\s*"
        "(\"[^\"]+\"|'[^']+')"
    )
    equals_bare_pattern = (
        f"\\m({alternation})"
        "[\"']?\\s*=\\s*"
        "[^\\s,;}\\]\\[\\n\"']+"
    )

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    sample_sql = """
    SELECT source_file, section_header, substring(content from 1 for 200) AS snippet
    FROM doc_chunks
    WHERE (content ~* %s OR content ~* %s)
      AND content NOT LIKE %s
    LIMIT 20;
    """
    cur.execute(sample_sql, (quoted_pattern, equals_bare_pattern, "%[REDACTED:%"))
    rows = cur.fetchall()

    count_sql = """
    SELECT count(*)
    FROM doc_chunks
    WHERE (content ~* %s OR content ~* %s)
      AND content NOT LIKE %s
    """
    cur.execute(count_sql, (quoted_pattern, equals_bare_pattern, "%[REDACTED:%"))
    (total,) = cur.fetchone()

    cur.close()
    conn.close()

    print(f"Unscrubbed field-value pairs in doc_chunks.content: {total}")
    if total > 0:
        print("\nSample violations (up to 20):")
        for source, header, snippet in rows:
            print(f"  {source} → {header}")
            print(f"    {snippet!r}")
        return 1

    print(f"Scrub verification passed, no unscrubbed values for {len(EXCLUDED_FIELDS)} configured field(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
