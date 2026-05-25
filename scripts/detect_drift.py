#!/usr/bin/env python3
"""Combine all drift signals into one prioritised JSON queue.

Four signals (the first three run without DB access; the last reads
from doc_chunks / decisions populated by the indexer pipeline):

    1. stale-string, scripts/stale_strings.py patterns
    2. dangling-ref, scripts/audit_docs_standards.py output
    3. dep-out-of-date, doc A `depends-on` doc B; B's commit newer than A's
    4. decision-contradict, chunk content mentions a registry topic but
                              disagrees with the current_value

Each item has:
    file, line, signal, reason, authoritative_source,
    suggested_replacement, flagged_doc_status, authoritative_status

Sorted by priority:
    decision-contradict > dangling-ref > stale-string > dep-out-of-date

Used by:
    scripts/detect_drift.py --json   → emits drift_report.json
    src/drift.py get_drift_report    → MCP tool reads + filters

Hygiene loop: weekly 15-minute pass over `get_drift_report(top=10)`.
See docs/00-fwk-doc-hygiene-loop.md.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rag_core.frontmatter import parse_frontmatter_v2
from rag_core.relationships import extract_relationships, to_full

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"

PRIORITY = {
    "decision-contradict": 0,
    "dangling-ref": 1,
    "stale-string": 2,
    "dep-out-of-date": 3,
}


# ─── Signal 1: stale strings ────────────────────────────────────────────
def _signal_stale_strings() -> list[dict]:
    """Run scripts/stale_strings.py via JSON mode and convert to drift items.

    Subprocess is bounded with a 30s timeout. Malformed JSON output, missing
    expected fields, and non-zero exits all degrade gracefully to an empty
    result so this signal can never block the rest of the pipeline.
    """
    script = Path(__file__).resolve().parent / "stale_strings.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script), "--json"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        sys.stderr.write(f"_signal_stale_strings: subprocess failed: {exc}\n")
        return []

    if out.returncode != 0 and out.stderr:
        sys.stderr.write(f"_signal_stale_strings: stderr: {out.stderr[:500]}\n")
    if not out.stdout:
        return []
    try:
        hits = json.loads(out.stdout)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"_signal_stale_strings: malformed JSON: {exc}\n")
        return []

    items: list[dict] = []
    for h in hits:
        try:
            items.append({
                "file": h["file"],
                "line": h["line"],
                "signal": "stale-string",
                "reason": h["reason"],
                "authoritative_source": None,
                "suggested_replacement": h.get("replacement"),
                "snippet": h.get("text", "")[:200],
            })
        except (KeyError, TypeError) as exc:
            sys.stderr.write(f"_signal_stale_strings: skipping malformed hit ({exc}): {h!r}\n")
            continue
    return items


# ─── Signal 2: dangling refs from audit_docs_standards.py ──────────────
_DANGLING_RE = re.compile(
    r"### `(?P<file>[^`]+)`\s*\n\n((?:- .+\n)+)",
)
_REF_LINE_RE = re.compile(
    r"^- `(?P<rel>depends-on|feeds-into)` ref `(?P<target>[^`]+)`",
)


def _signal_dangling_refs() -> list[dict]:
    """Read docs-standards-audit.md and pull out dangling-ref violations."""
    audit_path = DOCS_DIR.parent / "docs-standards-audit.md"
    if not audit_path.is_file():
        return []
    text = audit_path.read_text(encoding="utf-8")

    items: list[dict] = []
    for block in _DANGLING_RE.finditer(text):
        file = block.group("file")
        for line in block.group(2).splitlines():
            m = _REF_LINE_RE.match(line.strip())
            if not m:
                continue
            target = m.group("target")
            items.append({
                "file": f"docs/{file}",
                "line": None,
                "signal": "dangling-ref",
                "reason": f"`{m.group('rel')}` ref `{target}` does not match any existing doc",
                "authoritative_source": None,
                "suggested_replacement": None,
                "snippet": None,
            })
    return items


# ─── Signal 3: dependency-out-of-date ──────────────────────────────────
def _file_committed_at(path: Path):
    """Return a timezone-aware datetime for the file's last commit, or None."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--pretty=format:%cI", "--", str(path)],
            cwd=str(DOCS_DIR.parent),
            capture_output=True, text=True, check=False, timeout=10,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    raw = out.stdout.strip()
    if not raw:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _signal_dep_out_of_date() -> list[dict]:
    """For every doc A with depends-on B, flag if B's commit > A's commit.

    Comparison is done on timezone-aware datetimes parsed from `git log
    --pretty=format:%cI` so commits across mixed timezones order
    correctly.
    """
    md_files = sorted(DOCS_DIR.glob("*.md"))
    commits = {p.stem: _file_committed_at(p) for p in md_files}

    items: list[dict] = []
    for path in md_files:
        text = path.read_text(encoding="utf-8")
        metadata, _ = parse_frontmatter_v2(text)
        a_ts = commits.get(path.stem)
        if a_ts is None:
            continue
        for ref in metadata.get("depends-on") or []:
            ref = str(ref).strip().strip('"\'')
            if ref.endswith(".md"):
                ref = ref[:-3]
            if not ref or ref.startswith("area-"):
                continue
            b_ts = commits.get(ref)
            if b_ts is None:
                continue
            if b_ts > a_ts:
                items.append({
                    "file": f"docs/{path.name}",
                    "line": None,
                    "signal": "dep-out-of-date",
                    "reason": (
                        f"depends-on `{ref}` was committed at "
                        f"{b_ts.isoformat()} (newer than this doc's "
                        f"{a_ts.isoformat()})"
                    ),
                    "authoritative_source": f"docs/{ref}.md",
                    "suggested_replacement": None,
                    "snippet": None,
                })
    return items


# ─── Signal 4: decision contradiction (DB-backed) ──────────────────────
def _signal_decision_contradictions() -> list[dict]:
    """For each settled decision, scan chunks for contradictory mentions.

    Heuristic: if a chunk's content mentions the decision topic (decision
    text appears verbatim or close) but does NOT mention the current_value
    (any token of it), flag it. Cheap; deliberate false-positive tolerance.
    """
    if not os.environ.get("DATABASE_URL"):
        return []
    try:
        import psycopg2  # local import to avoid hard dep when DB-less

        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        cur.execute("""
            SELECT decision_key, decision, current_value, source_doc
            FROM decisions
            WHERE superseded_by IS NULL
            LIMIT 500
        """)
        decisions = cur.fetchall()

        items: list[dict] = []
        for dec_key, dec_text, current_value, source_doc in decisions:
            # Skip very short/long decision text, too noisy
            if not dec_text or len(dec_text) < 8 or len(dec_text) > 80:
                continue

            # Find chunks that mention the decision text but NOT the current_value
            cur.execute(
                """
                SELECT source_file, section_header
                FROM doc_chunks
                WHERE content ILIKE %s
                  AND content NOT ILIKE %s
                  AND source_file <> %s
                LIMIT 5
                """,
                (f"%{dec_text}%", f"%{current_value[:40]}%",
                 f"{{PROJECT_NAME}}/docs/{source_doc}.md"),
            )
            for sf, header in cur.fetchall():
                items.append({
                    "file": sf,
                    "line": None,
                    "signal": "decision-contradict",
                    "reason": (
                        f"chunk mentions `{dec_text}` but not the current value "
                        f"(`{current_value[:60]}…` per `{source_doc}`)"
                    ),
                    "authoritative_source": f"docs/{source_doc}.md",
                    "suggested_replacement": current_value,
                    "snippet": header,
                })

        cur.close()
        conn.close()
        return items
    except Exception:
        return []


def collect() -> list[dict]:
    """Run all signals and return the prioritised, deduplicated list."""
    items: list[dict] = []
    items.extend(_signal_stale_strings())
    items.extend(_signal_dangling_refs())
    items.extend(_signal_dep_out_of_date())
    items.extend(_signal_decision_contradictions())

    # Dedupe by (file, line, signal, reason).
    seen: set = set()
    unique: list[dict] = []
    for it in items:
        k = (it["file"], it.get("line"), it["signal"], it["reason"])
        if k in seen:
            continue
        seen.add(k)
        unique.append(it)

    unique.sort(key=lambda i: (PRIORITY.get(i["signal"], 99),
                               i["file"], i.get("line") or 0))
    return unique


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true",
                        help="Emit the full queue as JSON (machine-readable).")
    parser.add_argument("--top", type=int, default=20,
                        help="Limit to top N (default 20).")
    parser.add_argument("--signal",
                        help="Filter to one signal: stale-string, dangling-ref, "
                             "dep-out-of-date, decision-contradict")
    parser.add_argument("--out", default="scripts/drift_report.json",
                        help="JSON output path (when --json)")
    args = parser.parse_args()

    items = collect()
    if args.signal:
        items = [i for i in items if i["signal"] == args.signal]

    if args.json:
        out_path = Path(args.out)
        out_path.write_text(json.dumps(items, indent=2), encoding="utf-8")
        print(f"Wrote {len(items)} items to {out_path}")
        return 0

    items = items[: args.top]
    by_signal: dict[str, int] = {}
    for it in items:
        by_signal[it["signal"]] = by_signal.get(it["signal"], 0) + 1

    print(f"Drift queue (top {len(items)}):")
    for s, n in sorted(by_signal.items(), key=lambda x: PRIORITY.get(x[0], 99)):
        print(f"  {s}: {n}")
    print()
    for it in items:
        line_part = f":{it['line']}" if it.get("line") else ""
        print(f"  [{it['signal']}] {it['file']}{line_part}")
        print(f"    {it['reason']}")
        if it.get("suggested_replacement"):
            print(f"    → {it['suggested_replacement']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
