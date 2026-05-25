#!/usr/bin/env python3
"""Surface stale strings across docs/, currency drift, dropped vendors, retired terms.

A maintained pattern list. Each pattern carries a reason and the authoritative
replacement (when one exists). Reports hits in PR-fixable form. Does not edit
files, review and fix manually, or compose with `sed` / `Edit` per hit.

Usage:
    python3 scripts/stale_strings.py
    python3 scripts/stale_strings.py --json
    python3 scripts/stale_strings.py --pattern subscription   # filter to one category

To add a pattern, append to PATTERNS below. Keep regexes anchored where possible
to avoid false positives in narrative text (e.g. citing a competitor's price in
a research doc is legitimate; your own retired price is not).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

# Subdirs to skip entirely (session logs and audit artefacts mutate too often
# to be useful drift signals).
SKIP_DIRS = {"session-logs", "shift-and-drift", "handoff", "assets"}


@dataclass
class Pattern:
    """A stale-string pattern.

    `regex` is matched case-insensitively against each line.
    `category` groups related patterns (e.g. "subscription", "vendor").
    `reason` explains *why* this is stale.
    `replacement` is the canonical correct value, or None if context-dependent.
    `excludes` is a list of substrings; a line matching any of them is skipped
    (use for false-positive suppression, e.g. competitor citations).
    """

    regex: str
    category: str
    reason: str
    replacement: str | None = None
    excludes: list[str] = field(default_factory=list)


# Maintained pattern list. Add one Pattern per stale string your project needs
# to keep out of the docs (dropped vendor names, retired pricing, renamed
# fields, deprecated features). Each pattern is independent.
#
# Example (commented out, uncomment and adapt to your project):
#
# PATTERNS: list[Pattern] = [
#     Pattern(
#         regex=r"\bOldVendorName\b",
#         category="vendor",
#         reason="Vendor switched in 2026-Q1 per <decision-doc>; mentions should refer to NewVendor instead.",
#         replacement="NewVendor",
#         excludes=["historical", "previously", "rejected"],
#     ),
# ]
PATTERNS: list[Pattern] = []


@dataclass
class Hit:
    file: str
    line: int
    text: str
    pattern: Pattern


def scan_file(path: Path, patterns: list[Pattern]) -> list[Hit]:
    hits: list[Hit] = []
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return hits

    for line_no, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if any(ex.lower() in line.lower() for ex in pat.excludes):
                continue
            if re.search(pat.regex, line, re.IGNORECASE):
                hits.append(Hit(file=str(path.relative_to(DOCS_DIR.parent)),
                                line=line_no, text=line.strip(), pattern=pat))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit JSON for machine consumption")
    parser.add_argument("--pattern", help="Filter to a single category (e.g. 'subscription')")
    parser.add_argument("--docs-dir", default=str(DOCS_DIR), help="Override docs root")
    args = parser.parse_args()

    docs_root = Path(args.docs_dir)
    patterns = PATTERNS
    if args.pattern:
        patterns = [p for p in PATTERNS if p.category == args.pattern]
        if not patterns:
            print(f"No patterns in category '{args.pattern}'.", file=sys.stderr)
            return 2

    files = [p for p in docs_root.rglob("*.md")
             if not any(part in SKIP_DIRS for part in p.parts)]

    all_hits: list[Hit] = []
    for f in sorted(files):
        all_hits.extend(scan_file(f, patterns))

    if args.json:
        print(json.dumps([
            {"file": h.file, "line": h.line, "text": h.text,
             "category": h.pattern.category, "reason": h.pattern.reason,
             "replacement": h.pattern.replacement}
            for h in all_hits
        ], indent=2))
        return 0

    if not all_hits:
        print("No stale-string hits.")
        return 0

    by_cat: dict[str, list[Hit]] = {}
    for h in all_hits:
        by_cat.setdefault(h.pattern.category, []).append(h)

    for cat in sorted(by_cat):
        hits = by_cat[cat]
        print(f"\n=== {cat} ({len(hits)}) ===")
        for h in hits:
            print(f"{h.file}:{h.line}  {h.text}")
            print(f"    → {h.pattern.reason}")
            if h.pattern.replacement:
                print(f"    ↳ Suggested: {h.pattern.replacement}")

    print(f"\nTotal: {len(all_hits)} hits across {len(by_cat)} categories.")
    return 1 if all_hits else 0


if __name__ == "__main__":
    sys.exit(main())
