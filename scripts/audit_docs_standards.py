#!/usr/bin/env python3
"""Audit docs/ against 00-pol-document-standards.md.

Mechanical checks only. Writes a report to docs-standards-audit.md.
Scans docs/ at a single level; subdirectories (e.g. session-logs/) are
not walked.

Usage:
    python3 scripts/audit_docs_standards.py           # audit only (default)
    python3 scripts/audit_docs_standards.py --fix     # apply mechanical fixes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml not installed. pip install pyyaml", file=sys.stderr)
    sys.exit(1)


DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"
REPORT_PATH = Path(__file__).resolve().parent.parent / "docs-standards-audit.md"
RENAME_MAP_PATH = Path(__file__).resolve().parent / "doc_rename_map.json"

STATUS_NORMALISE = {
    # Map legacy / sloppy status values to the canonical vocabulary in
    # 00-pol-document-standards.md. Extend if your project migrates from
    # another convention; otherwise leave as-is.
    "in progress": "in-progress",
    "active": "complete",  # legacy tracker convention; complete is the standards value
}

VALID_TYPES = {"spec", "res", "str", "dec", "pol", "fwk"}
VALID_STATUS = {"draft", "in-progress", "complete", "superseded", "needs-review"}
REQUIRED_FIELDS = [
    "file",
    "area",
    "area-name",
    "type",
    "title",
    "status",
    "date",
    "depends-on",
    "feeds-into",
]

FILENAME_RE = re.compile(r"^(\d{2})-(spec|res|str|dec|pol|fwk)-[a-z0-9-]+\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Files exempt from oversized-section checks per 00-pol-document-standards §Exemptions.
# Add filenames here only with a comment explaining why the file legitimately
# cannot meet the 4000-char section limit (e.g. living issue lists, long-form
# narrative artefacts). The standing target is the empty set.
EXEMPT_OVERSIZED: set[str] = set()

# Files exempt from deep-nesting checks per 00-pol-document-standards §Exemptions.
# Add filenames here only with a comment explaining why the file legitimately
# nests deeper than ### (e.g. per-issue anchors in a living tracker doc).
EXEMPT_DEEP_NESTING: set[str] = set()

# Files exempt from no-h2 checks per 00-pol-document-standards §Exemptions.
# Single-chunk narrative artefacts where section headers would fragment a
# piece written as one continuous prose voice.
EXEMPT_NO_H2: set[str] = set()


@dataclass
class DocIssues:
    filename: str
    violations: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.violations.append(msg)

    @property
    def ok(self) -> bool:
        return not self.violations


def parse_frontmatter(text: str) -> tuple[dict | None, str | None]:
    if not text.startswith("---"):
        return None, "no frontmatter block (file does not start with '---')"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "frontmatter block not closed with '---'"
    fm_text = text[3:end].strip()
    try:
        data = yaml.safe_load(fm_text)
    except yaml.YAMLError as e:
        return None, f"frontmatter YAML parse error: {e}"
    if not isinstance(data, dict):
        return None, "frontmatter is not a mapping"
    return data, None


def check_filename(name: str, issues: DocIssues) -> tuple[int | None, str | None]:
    m = FILENAME_RE.match(name)
    if not m:
        issues.add(f"filename does not match `[NN]-[type]-[name].md` pattern")
        return None, None
    return int(m.group(1)), m.group(2)


def check_frontmatter(
    data: dict, filename: str, fn_area: int | None, fn_type: str | None, issues: DocIssues
) -> None:
    for field_name in REQUIRED_FIELDS:
        if field_name not in data:
            issues.add(f"missing required frontmatter field `{field_name}`")

    # file matches filename
    if "file" in data:
        expected = filename[:-3] if filename.endswith(".md") else filename
        if data["file"] != expected:
            issues.add(f"`file` field `{data['file']}` does not match filename `{expected}`")

    # type valid
    if "type" in data:
        if data["type"] not in VALID_TYPES:
            issues.add(f"`type` `{data['type']}` not in allowed set {sorted(VALID_TYPES)}")
        elif fn_type and data["type"] != fn_type:
            issues.add(f"`type` `{data['type']}` does not match filename type `{fn_type}`")

    # status valid
    if "status" in data:
        if data["status"] not in VALID_STATUS:
            issues.add(f"`status` `{data['status']}` not in allowed set {sorted(VALID_STATUS)}")

    # area valid
    if "area" in data:
        area_val = data["area"]
        if not isinstance(area_val, int):
            issues.add(f"`area` must be integer, got `{area_val!r}`")
        elif not (0 <= area_val <= 12):
            issues.add(f"`area` `{area_val}` out of range 0, 12")
        elif fn_area is not None and area_val != fn_area:
            issues.add(f"`area` `{area_val}` does not match filename area `{fn_area}`")

    # date format
    if "date" in data:
        date_val = data["date"]
        # YAML parses YYYY-MM-DD as datetime.date
        if hasattr(date_val, "isoformat"):
            pass
        elif isinstance(date_val, str) and DATE_RE.match(date_val):
            pass
        else:
            issues.add(f"`date` `{date_val!r}` not in YYYY-MM-DD format")

    # depends-on / feeds-into should be lists
    for rel in ("depends-on", "feeds-into"):
        if rel in data and data[rel] is not None and not isinstance(data[rel], list):
            issues.add(f"`{rel}` must be a list (use `[]` if empty)")


def check_headers_and_sections(body: str, issues: DocIssues, filename: str = "") -> None:
    lines = body.splitlines()
    # Headers
    h2_count = sum(1 for line in lines if line.startswith("## ") and not line.startswith("### "))
    h4_plus = [line for line in lines if re.match(r"^#{4,}\s", line)]
    if h2_count == 0 and filename not in EXEMPT_NO_H2:
        issues.add("no `##` section headers (document is a single chunk)")
    if h4_plus and filename not in EXEMPT_DEEP_NESTING:
        issues.add(f"has {len(h4_plus)} header(s) nested deeper than `###`")

    # Section length: split on ## headers, check each chunk
    if h2_count > 0 and filename not in EXEMPT_OVERSIZED:
        # split body into chunks at each ## header
        chunks: list[tuple[str, str]] = []
        current_header = "(preamble)"
        current_buf: list[str] = []
        for line in lines:
            if line.startswith("## ") and not line.startswith("### "):
                chunks.append((current_header, "\n".join(current_buf)))
                current_header = line.strip()
                current_buf = [line]
            else:
                current_buf.append(line)
        chunks.append((current_header, "\n".join(current_buf)))
        oversized = [(h, len(c)) for h, c in chunks if len(c) > 4000]
        if oversized:
            details = ", ".join(f"{h[:60]!r}={n}ch" for h, n in oversized[:3])
            more = f" (+{len(oversized)-3} more)" if len(oversized) > 3 else ""
            issues.add(f"{len(oversized)} section(s) exceed 4000 chars: {details}{more}")


def check_dependencies(
    data: dict, all_filenames: set[str], issues: DocIssues
) -> None:
    for rel in ("depends-on", "feeds-into"):
        if rel not in data or data[rel] is None:
            continue
        if not isinstance(data[rel], list):
            continue
        for ref in data[rel]:
            if not isinstance(ref, str):
                issues.add(f"`{rel}` entry `{ref!r}` is not a string")
                continue
            if ref.startswith("area-"):
                # area-N-name form; accept without further validation
                if not re.match(r"^area-\d+-[a-z0-9-]+$", ref):
                    issues.add(f"`{rel}` area ref `{ref}` malformed (expected `area-N-name`)")
                continue
            if ref not in all_filenames:
                issues.add(f"`{rel}` ref `{ref}` does not match any existing doc")


def load_rename_map() -> dict:
    """Load doc_rename_map.json, returning empty defaults on error.

    Validates the shape so a malformed map (e.g. `area_redirects` set to
    a string instead of an object) doesn't crash `rewrite_ref` deep in
    the audit loop.
    """
    empty = {"renames": {}, "per_file_renames": {}, "area_redirects": {}, "delete_refs": []}
    if not RENAME_MAP_PATH.exists():
        return empty
    try:
        with RENAME_MAP_PATH.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: doc_rename_map.json could not be loaded ({exc}); using empty defaults.")
        return empty

    if not isinstance(data, dict):
        print("Warning: doc_rename_map.json is not a JSON object; using empty defaults.")
        return empty

    expected = {
        "renames": dict,
        "per_file_renames": dict,
        "area_redirects": dict,
        "delete_refs": list,
    }
    for k, t in expected.items():
        if not isinstance(data.get(k, t()), t):
            print(
                f"Warning: doc_rename_map.json field `{k}` is not a "
                f"{t.__name__}; using empty default for it."
            )
            data[k] = t()
        elif k not in data:
            data[k] = t()
    return data


def rewrite_ref(ref, filename: str, rmap: dict) -> str | None:
    """Apply rename map to a single ref. Returns new value, or None to delete."""
    if not isinstance(ref, str):
        return ref
    if ref in rmap.get("delete_refs", []):
        return None
    per_file = rmap.get("per_file_renames", {}).get(filename, {})
    if ref in per_file:
        return per_file[ref]
    if ref in rmap.get("renames", {}):
        return rmap["renames"][ref]
    if ref in rmap.get("area_redirects", {}):
        return rmap["area_redirects"][ref]
    return ref


LIST_ITEM_RE = re.compile(r"^(\s*-\s+)(.*?)(\s*)$")


def apply_fixes(rmap: dict) -> dict:
    """Apply mechanical fixes to docs with surgical string edits.

    Preserves original YAML formatting. Only touches lines we need to change.
    """
    stats = {
        "files_changed": 0,
        "status_normalised": 0,
        "file_field_fixed": 0,
        "refs_renamed": 0,
        "refs_deleted": 0,
    }
    for path in sorted(DOCS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end == -1:
            continue
        fm_end = end + 4  # position after closing '---\n'
        fm_block = text[: end + 4]  # includes closing '---'
        body = text[fm_end:]

        lines = fm_block.splitlines(keepends=True)
        new_lines: list[str] = []
        current_rel: str | None = None  # active 'depends-on' or 'feeds-into' block
        changed = False

        for line in lines:
            stripped = line.rstrip("\n")

            # Status normalisation
            if stripped.startswith("status:"):
                val = stripped.split(":", 1)[1].strip()
                # strip trailing quotes for comparison
                raw = val.strip('"\'')
                if raw in STATUS_NORMALISE:
                    new_lines.append(f"status: {STATUS_NORMALISE[raw]}\n")
                    stats["status_normalised"] += 1
                    changed = True
                    current_rel = None
                    continue

            # File field mismatch
            if stripped.startswith("file:"):
                val = stripped.split(":", 1)[1].strip()
                if val != path.stem:
                    new_lines.append(f"file: {path.stem}\n")
                    stats["file_field_fixed"] += 1
                    changed = True
                    current_rel = None
                    continue

            # Track active depends-on / feeds-into block
            if stripped.startswith("depends-on:"):
                current_rel = "depends-on"
                new_lines.append(line)
                continue
            if stripped.startswith("feeds-into:"):
                current_rel = "feeds-into"
                new_lines.append(line)
                continue

            # Any other top-level key ends the active rel block
            if re.match(r"^[a-zA-Z][\w-]*:", stripped):
                current_rel = None
                new_lines.append(line)
                continue

            # List item within a rel block
            if current_rel is not None:
                m = LIST_ITEM_RE.match(stripped)
                if m:
                    prefix, ref, _ = m.group(1), m.group(2), m.group(3)
                    # strip surrounding quotes if any
                    ref_stripped = ref.strip().strip('"\'')
                    new = rewrite_ref(ref_stripped, path.name, rmap)
                    if new is None:
                        stats["refs_deleted"] += 1
                        changed = True
                        continue  # drop the line
                    if new != ref_stripped:
                        stats["refs_renamed"] += 1
                        changed = True
                        new_lines.append(f"{prefix}{new}\n")
                        continue
                    new_lines.append(line)
                    continue

            new_lines.append(line)

        if changed:
            new_fm_block = "".join(new_lines)
            path.write_text(new_fm_block + body, encoding="utf-8")
            stats["files_changed"] += 1

    return stats


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fix", action="store_true", help="Apply mechanical fixes before auditing")
    args = parser.parse_args()

    if args.fix:
        rmap = load_rename_map()
        stats = apply_fixes(rmap)
        print(f"Applied fixes: {stats}")

    md_files = sorted(
        p for p in DOCS_DIR.glob("*.md") if p.is_file()
    )
    all_filenames = {p.stem for p in md_files}

    per_doc: list[DocIssues] = []
    for path in md_files:
        # Per-track session-log artefacts follow a different naming
        # convention (track-<X>-*.md or track-<X>-log.md) and are not
        # spec docs, skip them silently from all checks and from the
        # Clean files list.
        if path.name.startswith("track-"):
            continue
        # Wiki-style index files don't follow the doc pattern.
        if path.name == "index.md":
            continue
        issues = DocIssues(filename=path.name)
        text = path.read_text(encoding="utf-8")

        fn_area, fn_type = check_filename(path.name, issues)
        fm, err = parse_frontmatter(text)
        if err:
            issues.add(err)
        if fm is not None:
            check_frontmatter(fm, path.name, fn_area, fn_type, issues)
            check_dependencies(fm, all_filenames, issues)

        # body = text after closing '---'
        body = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                body = text[end + 4 :]
        check_headers_and_sections(body, issues, filename=path.name)
        per_doc.append(issues)

    total = len(per_doc)
    violating = [d for d in per_doc if not d.ok]
    clean = total - len(violating)

    # Tally by violation category
    categories: dict[str, int] = {}
    for d in violating:
        seen_cats = set()
        for v in d.violations:
            cat = categorize(v)
            seen_cats.add(cat)
        for cat in seen_cats:
            categories[cat] = categories.get(cat, 0) + 1

    write_report(total, clean, violating, categories, per_doc)
    print(f"Audited {total} docs. {clean} clean, {len(violating)} with violations.")
    print(f"Report: {REPORT_PATH}")
    return 0


def categorize(msg: str) -> str:
    if "filename" in msg:
        return "filename-pattern"
    if "frontmatter" in msg and "parse" in msg:
        return "frontmatter-parse"
    if "no frontmatter" in msg or "not closed" in msg:
        return "frontmatter-missing"
    if msg.startswith("missing required frontmatter"):
        return "missing-fields"
    if "`file` field" in msg:
        return "file-mismatch"
    if "`type`" in msg:
        return "type-invalid"
    if "`status`" in msg:
        return "status-invalid"
    if "`area`" in msg:
        return "area-invalid"
    if "`date`" in msg:
        return "date-format"
    if "must be a list" in msg:
        return "field-type"
    if "no `##`" in msg:
        return "no-h2"
    if "deeper than" in msg:
        return "deep-nesting"
    if "exceed 4000" in msg:
        return "oversized-section"
    if "does not match any existing" in msg:
        return "dangling-ref"
    if "area ref" in msg:
        return "area-ref-malformed"
    return "other"


def write_report(
    total: int,
    clean: int,
    violating: list[DocIssues],
    categories: dict[str, int],
    per_doc: list[DocIssues],
) -> None:
    lines: list[str] = []
    lines.append("# Document Standards Audit")
    lines.append("")
    lines.append("Mechanical audit of `docs/*.md` against `00-pol-document-standards.md`.")
    lines.append("Subdirectories under `docs/` are not walked.")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total docs audited: **{total}**")
    lines.append(f"- Clean (no mechanical violations): **{clean}**")
    lines.append(f"- Violating: **{len(violating)}**")
    lines.append("")
    lines.append("### Violations by category")
    lines.append("")
    lines.append("| Category | Files affected |")
    lines.append("|---|---|")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {count} |")
    lines.append("")
    lines.append("Category key:")
    lines.append("")
    lines.append("- `filename-pattern`, filename not `[NN]-[type]-[name].md`")
    lines.append("- `frontmatter-missing`, no YAML frontmatter block")
    lines.append("- `frontmatter-parse`, frontmatter YAML invalid")
    lines.append("- `missing-fields`, required frontmatter field absent")
    lines.append("- `file-mismatch`, `file` field does not match filename stem")
    lines.append("- `type-invalid`, `type` not in {spec, res, str, dec, pol, fwk} or mismatches filename")
    lines.append("- `status-invalid`, `status` not in {draft, in-progress, complete, superseded, needs-review}")
    lines.append("- `area-invalid`, `area` not int 0, 12 or mismatches filename prefix")
    lines.append("- `date-format`, `date` not `YYYY-MM-DD`")
    lines.append("- `field-type`, `depends-on`/`feeds-into` not a list")
    lines.append("- `no-h2`, no `##` section headers")
    lines.append("- `deep-nesting`, headers deeper than `###`")
    lines.append("- `oversized-section`, `##` section over 4000 chars")
    lines.append("- `dangling-ref`, `depends-on`/`feeds-into` points to non-existent doc")
    lines.append("- `area-ref-malformed`, `area-N-name` form malformed")
    lines.append("")
    lines.append("## Per-file violations")
    lines.append("")
    if not violating:
        lines.append("_None._")
    for d in sorted(violating, key=lambda x: x.filename):
        lines.append(f"### `{d.filename}`")
        lines.append("")
        for v in d.violations:
            lines.append(f"- {v}")
        lines.append("")
    lines.append("## Exemptions")
    lines.append("")
    lines.append("The following files are exempt from specific checks per")
    lines.append("`00-pol-document-standards.md` §Exemptions.")
    lines.append("")
    lines.append("### Oversized-section exemptions")
    lines.append("")
    for f in sorted(EXEMPT_OVERSIZED):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("### Deep-nesting exemptions")
    lines.append("")
    for f in sorted(EXEMPT_DEEP_NESTING):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("### No-h2 exemptions")
    lines.append("")
    for f in sorted(EXEMPT_NO_H2):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("## Clean files")
    lines.append("")
    clean_files = [d.filename for d in per_doc if d.ok]
    if clean_files:
        for f in sorted(clean_files):
            lines.append(f"- `{f}`")
    else:
        lines.append("_None._")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
