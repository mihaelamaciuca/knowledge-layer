#!/usr/bin/env python3
"""Fixture-based test for rag_core.scrub.

Runs in CI on every PR touching docs/. Exits non-zero on any fixture
mismatch.

When you populate `EXCLUDED_FIELDS` in rag_core/scrub.py, add fixtures
below that prove the scrub behaves as you expect. Three classes of
fixture exist:

    1. POSITIVES, content containing value-bearing assignments of
       excluded fields. After scrub_content runs, find_violations must
       return [], and the redacted output must contain the [REDACTED:*]
       marker for every excluded field that was present.

    2. NEGATIVES, content that mentions excluded field names in prose
       or as a doc reference (no value assigned). scrub_content must
       leave them untouched.

    3. IDEMPOTENCY, running scrub_content twice on the same input must
       produce the same output (no double-redaction).

Until EXCLUDED_FIELDS is populated and fixtures are added, this script
is a no-op that returns 0. CI gates pass without exercising the scrub.

Example fixtures (commented out, uncomment when you add fields like
"ssn", "api_key", etc. to EXCLUDED_FIELDS):

    POSITIVE_FIXTURES = [
        ("yaml-style quoted assignment", 'ssn: "123-45-6789"', ["ssn"]),
        ("json-style quoted", '{"api_key": "sk-abc123"}', ["api_key"]),
        ("log-style compact (bare value after =)",
         "INFO request=abc user.api_key=sk-xyz", ["api_key"]),
    ]
    NEGATIVE_FIXTURES = [
        ("doc-style reference",
         "The `api_key` field stores the customer's secret."),
        ("markdown bold label, prose, not assignment",
         "**SSN:** required for identity verification."),
    ]
    IDEMPOTENCY_FIXTURES = ['ssn: "111-22-3333"', "no excluded fields here"]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_core.scrub import EXCLUDED_FIELDS, find_violations, scrub_content


# Add (label, content, expected_redacted_fields) tuples here.
POSITIVE_FIXTURES: list[tuple[str, str, list[str]]] = []

# Add (label, content) tuples here.
NEGATIVE_FIXTURES: list[tuple[str, str]] = []

# Add raw content strings here.
IDEMPOTENCY_FIXTURES: list[str] = []


def run() -> int:
    if not EXCLUDED_FIELDS:
        print("No EXCLUDED_FIELDS configured in rag_core.scrub, scrub_test is a no-op.")
        print("Populate EXCLUDED_FIELDS and add fixtures to lock in the behaviour.")
        return 0

    if not (POSITIVE_FIXTURES or NEGATIVE_FIXTURES or IDEMPOTENCY_FIXTURES):
        print(
            f"EXCLUDED_FIELDS has {len(EXCLUDED_FIELDS)} field(s) configured but no fixtures are defined.\n"
            "Add fixtures to POSITIVE_FIXTURES / NEGATIVE_FIXTURES / IDEMPOTENCY_FIXTURES\n"
            "to verify the scrub catches what you expect."
        )
        return 1

    failures: list[str] = []

    # ── Positives ─────────────────────────────────────────────────────
    for label, content, expected_fields in POSITIVE_FIXTURES:
        scrubbed = scrub_content(content)
        remaining = find_violations(scrubbed)
        if remaining:
            failures.append(
                f"POSITIVE  {label}: violations survived scrub: "
                f"{[v[1] for v in remaining]}\n    input:    {content!r}"
                f"\n    scrubbed: {scrubbed!r}"
            )
            continue
        missing = [f for f in expected_fields if f"[REDACTED:{f}]" not in scrubbed]
        if missing:
            failures.append(
                f"POSITIVE  {label}: expected [REDACTED:*] for {missing} but "
                f"absent from output\n    scrubbed: {scrubbed!r}"
            )

    # ── Negatives ─────────────────────────────────────────────────────
    for label, content in NEGATIVE_FIXTURES:
        scrubbed = scrub_content(content)
        if scrubbed != content:
            failures.append(
                f"NEGATIVE  {label}: content was modified\n"
                f"    before: {content!r}\n"
                f"    after:  {scrubbed!r}"
            )

    # ── Idempotency ───────────────────────────────────────────────────
    for content in IDEMPOTENCY_FIXTURES:
        once = scrub_content(content)
        twice = scrub_content(once)
        if once != twice:
            failures.append(
                f"IDEMPOTENT  scrub_content is not idempotent\n"
                f"    input: {content!r}\n"
                f"    once:  {once!r}\n"
                f"    twice: {twice!r}"
            )

    total = len(POSITIVE_FIXTURES) + len(NEGATIVE_FIXTURES) + len(IDEMPOTENCY_FIXTURES)
    if failures:
        print(f"FAIL: {len(failures)} of {total} fixtures failed\n")
        for f in failures:
            print(f)
            print()
        return 1

    print(
        f"OK: {total} fixtures passed "
        f"({len(POSITIVE_FIXTURES)} positive + {len(NEGATIVE_FIXTURES)} negative + "
        f"{len(IDEMPOTENCY_FIXTURES)} idempotency)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
