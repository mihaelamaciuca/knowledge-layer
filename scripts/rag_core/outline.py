"""Document outline extraction.

Parses `#`, `##`, `###` headers from a markdown body into a navigable
tree. Each entry has:

    level       : int, 1, 2, or 3
    header      : str, the heading text (no leading `#`s)
    anchor      : str. GitHub-style slug
    char_start  : int, byte offset where this section begins (the `#` line)
    char_end    : int, byte offset where the next same-or-higher-level
                        heading begins (or len(body) for the last section)

Used by:
    - rag_core.sync (writes the tree to doc_outlines on every upsert)
    - src/outline.py (the get_doc_outline MCP tool)

The 4,800-line test plans and 3,000-line build guides need this so the
model can navigate via section anchors instead of grep-searching the
full body. Closes the long-doc retrieval shortcoming surfaced when
Replaces the earlier placeholder.
"""
import re

_HEADER_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*$", re.MULTILINE)
_SLUG_STRIP_RE = re.compile(r"[^\w\s-]")
_SLUG_SPACE_RE = re.compile(r"[\s_]+")


def slugify(text: str) -> str:
    """GitHub-style slug: lowercase, non-word chars stripped, spaces → `-`."""
    cleaned = _SLUG_STRIP_RE.sub("", text.lower())
    return _SLUG_SPACE_RE.sub("-", cleaned).strip("-")


def extract_outline(body: str, max_level: int = 3) -> list[dict]:
    """Return the section tree of a markdown body.

    Walks `#` through `###` headers (capped at `max_level`). For each
    header, captures the level, text, slug, and the char range from the
    header line to the next same-or-higher-level header (or end of body).
    """
    raw_headers: list[tuple[int, str, int]] = []  # (level, header, char_start)

    for match in _HEADER_RE.finditer(body):
        hashes, header = match.group(1), match.group(2).strip()
        level = len(hashes)
        if level > max_level or not header:
            continue
        raw_headers.append((level, header, match.start()))

    if not raw_headers:
        return []

    body_len = len(body)
    out: list[dict] = []
    used_slugs: dict[str, int] = {}

    for i, (level, header, char_start) in enumerate(raw_headers):
        # Walk forward to the next header at the same or higher level.
        char_end = body_len
        for j in range(i + 1, len(raw_headers)):
            next_level, _, next_start = raw_headers[j]
            if next_level <= level:
                char_end = next_start
                break

        slug_base = slugify(header)
        if not slug_base:
            slug_base = f"section-{i}"
        count = used_slugs.get(slug_base, 0)
        if count == 0:
            anchor = slug_base
        else:
            anchor = f"{slug_base}-{count}"
        used_slugs[slug_base] = count + 1

        out.append({
            "level": level,
            "header": header,
            "anchor": anchor,
            "char_start": char_start,
            "char_end": char_end,
        })

    return out


def upsert_outline(cur, source_file: str, outline: list[dict]) -> None:
    """Replace the outline row for `source_file`. Idempotent."""
    import json
    cur.execute(
        """
        INSERT INTO doc_outlines (source_file, outline, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (source_file) DO UPDATE SET
            outline = EXCLUDED.outline,
            updated_at = now()
        """,
        (source_file, json.dumps(outline)),
    )


def delete_outline_for_source(cur, source_file: str) -> int:
    cur.execute("DELETE FROM doc_outlines WHERE source_file = %s", (source_file,))
    return cur.rowcount
