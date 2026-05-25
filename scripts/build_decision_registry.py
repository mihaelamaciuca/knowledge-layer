#!/usr/bin/env python3
"""Build the decisions registry table from *-dec-*.md frontmatter.

Scans docs/*-dec-*.md for a `decisions:` block in YAML frontmatter and
upserts each entry into the `decisions` table
(see migrations/001_schema.sql).

Expected shape in a decision document's frontmatter:

    decisions:
      - key: trial-length
        decision: Free trial length
        current_value: "14 days"
        decided_on: 2026-03-10
        cross_refs:
          - 02-spec-pricing-ux
          - 05-spec-api-contract
        supersedes: trial-length-v1   # optional, key of the decision this one replaces

A file may contain multiple decisions in its `decisions:` list. The `key`
is the natural identifier (UNIQUE in the table); use stable, slug-form
strings.

Upsert strategy:
    1. Pass 1, upsert each decision by `decision_key`, leaving
       `superseded_by` NULL.
    2. Pass 2, for every decision whose frontmatter declared
       `supersedes`, look up the predecessor's id by key and set the
       predecessor's `superseded_by` to point at this decision.

Usage:
    DATABASE_URL=postgres://... python3 scripts/build_decision_registry.py

Exits 0 on success. Exits 1 on malformed frontmatter, duplicate key, or
unresolvable `supersedes` target.
"""
import os
import re
import sys
from pathlib import Path

import psycopg2
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs"
DEC_FILENAME_RE = re.compile(r"^\d{2}-dec-[a-z0-9-]+\.md$")
REQUIRED_FIELDS = ("key", "decision", "current_value")


def parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    return yaml.safe_load(text[4:end])


def collect_decisions() -> tuple[list[dict], dict[str, dict]] | None:
    decisions: list[dict] = []
    by_key: dict[str, dict] = {}

    for path in sorted(DOCS_DIR.glob("*-dec-*.md")):
        if not DEC_FILENAME_RE.match(path.name):
            continue
        fm = parse_frontmatter(path)
        if not fm:
            continue
        entries = fm.get("decisions") or []
        if not entries:
            continue
        area = fm.get("area")
        if area is None:
            print(
                f"ERROR {path.stem}: frontmatter has no `area` field; "
                f"the decisions table requires an int area.",
                file=sys.stderr,
            )
            return None
        if not isinstance(area, int):
            try:
                area = int(area)
            except (TypeError, ValueError):
                print(
                    f"ERROR {path.stem}: frontmatter `area` ({area!r}) is "
                    f"not an integer.",
                    file=sys.stderr,
                )
                return None
        source_doc = path.stem
        for entry in entries:
            missing = [f for f in REQUIRED_FIELDS if not entry.get(f)]
            if missing:
                print(
                    f"ERROR {source_doc}: decision missing required fields "
                    f"{missing}: {entry}",
                    file=sys.stderr,
                )
                return None
            key = entry["key"]
            if key in by_key:
                print(
                    f"ERROR {source_doc}: duplicate decision_key {key!r} "
                    f"(also in {by_key[key]['source_doc']})",
                    file=sys.stderr,
                )
                return None
            row = {
                "decision_key": key,
                "area": area,
                "decision": entry["decision"],
                "current_value": str(entry["current_value"]),
                "source_doc": source_doc,
                "decided_on": entry.get("decided_on"),
                "cross_refs": entry.get("cross_refs") or [],
                "supersedes": entry.get("supersedes"),
            }
            decisions.append(row)
            by_key[key] = row

    return decisions, by_key


def detect_cycles(decisions: list[dict]) -> list[str] | None:
    """Return the cycle path if the supersedes graph contains a cycle, else None.

    Uses iterative DFS with a recursion stack so the chain `A supersedes B,
    B supersedes A` (and longer variants) is flagged before we try to
    write the cycle to Postgres.
    """
    successors: dict[str, str] = {}
    keys: set[str] = set()
    for d in decisions:
        keys.add(d["decision_key"])
        if d["supersedes"]:
            successors[d["decision_key"]] = d["supersedes"]

    color: dict[str, int] = {k: 0 for k in keys}  # 0 white, 1 grey, 2 black

    for start in keys:
        if color[start] != 0:
            continue
        stack: list[tuple[str, str | None]] = [(start, successors.get(start))]
        path: list[str] = []
        while stack:
            node, target = stack[-1]
            if color[node] == 0:
                color[node] = 1
                path.append(node)
            if target is None or target not in keys:
                color[node] = 2
                stack.pop()
                path.pop()
                continue
            if color[target] == 1:
                cycle_start = path.index(target)
                return path[cycle_start:] + [target]
            if color[target] == 0:
                stack.append((target, successors.get(target)))
                continue
            # target is black: already explored, no cycle through it
            color[node] = 2
            stack.pop()
            path.pop()
    return None


def main() -> int:
    if not DOCS_DIR.exists():
        print(f"Error: {DOCS_DIR} does not exist", file=sys.stderr)
        return 2

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2

    result = collect_decisions()
    if result is None:
        return 1
    decisions, by_key = result

    if not decisions:
        print("No decisions found in any docs/*-dec-*.md frontmatter.")
        return 0

    cycle = detect_cycles(decisions)
    if cycle is not None:
        print(
            "ERROR unresolvable supersedes cycle: "
            + " -> ".join(f"`{k}`" for k in cycle),
            file=sys.stderr,
        )
        return 1

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    cur = conn.cursor()

    try:
        _upsert_pass(cur, decisions)
        _wire_supersedes(cur, decisions, by_key)
    except Exception as exc:
        conn.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    conn.commit()
    cur.execute("SELECT count(*) FROM decisions")
    (total,) = cur.fetchone()
    cur.close()
    conn.close()
    print(
        f"Upserted {len(decisions)} decision(s) across "
        f"{len({d['source_doc'] for d in decisions})} file(s). "
        f"decisions table now holds {total} row(s)."
    )
    return 0


def _upsert_pass(cur, decisions: list[dict]) -> None:
    """Pass 1, upsert each decision; reset superseded_by until pass 2."""
    for d in decisions:
        cur.execute(
            """
            INSERT INTO decisions (
                decision_key, area, decision, current_value, source_doc,
                decided_on, cross_refs, superseded_by, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, now())
            ON CONFLICT (decision_key) DO UPDATE SET
                area          = EXCLUDED.area,
                decision      = EXCLUDED.decision,
                current_value = EXCLUDED.current_value,
                source_doc    = EXCLUDED.source_doc,
                decided_on    = EXCLUDED.decided_on,
                cross_refs    = EXCLUDED.cross_refs,
                superseded_by = NULL,
                updated_at    = now()
            """,
            (
                d["decision_key"], d["area"], d["decision"], d["current_value"],
                d["source_doc"], d["decided_on"], d["cross_refs"],
            ),
        )

def _wire_supersedes(cur, decisions: list[dict], by_key: dict[str, dict]) -> None:
    """Pass 2, wire up superseded_by pointers. Cycle detection has
    already run, so any unresolved predecessor is a genuine error."""
    for d in decisions:
        pred_key = d["supersedes"]
        if not pred_key:
            continue
        cur.execute("SELECT id FROM decisions WHERE decision_key = %s", (pred_key,))
        row = cur.fetchone()
        if row is None:
            raise RuntimeError(
                f"{d['source_doc']}: decision {d['decision_key']!r} "
                f"declares supersedes={pred_key!r} but no such decision exists"
            )
        cur.execute(
            """
            UPDATE decisions SET superseded_by = (
                SELECT id FROM decisions WHERE decision_key = %s
            )
            WHERE decision_key = %s
            """,
            (d["decision_key"], pred_key),
        )


if __name__ == "__main__":
    sys.exit(main())
