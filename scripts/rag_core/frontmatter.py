"""YAML frontmatter parsing without a PyYAML dependency.

Two parsing functions:

    parse_frontmatter(text)
        Returns (scalar_metadata_dict, body). Scalar keys only, matches
        the v1 line-based parser used by populate.py and the Action.

    parse_frontmatter_v2(text)
        Returns (full_metadata_dict, body) where list-valued keys
        (depends-on, feeds-into, also-touches) are returned as Python
        lists. Added for the indexer columns.

Both functions are line-based to keep the package dependency-free.
"""
import re

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

LIST_FIELDS = ("depends-on", "feeds-into", "also-touches")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and return (scalar_metadata_dict, body).

    Scalar keys only. List items (lines starting with `- `) are skipped.
    Use parse_frontmatter_v2 to get list-valued fields.

    If no frontmatter block is found, returns ({}, text).
    """
    metadata: dict = {}
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return metadata, text

    body = text[match.end():]
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            continue
        kv = line.split(":", 1)
        if len(kv) == 2:
            metadata[kv[0].strip()] = kv[1].strip()

    return metadata, body


def parse_frontmatter_v2(text: str) -> tuple[dict, str]:
    """Like parse_frontmatter but also returns list-valued fields.

    List-valued fields recognised: depends-on, feeds-into, also-touches.

    Supports two YAML list shapes:
        depends-on:
          - filename-1
          - filename-2

        also-touches: [1, 2, 3]

    For inline arrays the brackets and commas are stripped; numeric
    elements (also-touches) are coerced to int when possible.

    Empty lists (`[]` or just the key with no entries) yield [].
    """
    metadata, body = parse_frontmatter(text)
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return metadata, body

    raw_block = match.group(1)
    list_metadata = _parse_list_fields(raw_block)
    metadata = {**metadata, **list_metadata}
    return metadata, body


def _parse_list_fields(raw_block: str) -> dict:
    """Walk the frontmatter block and pull out list-valued fields."""
    result: dict = {}
    current_key: str | None = None
    current_list: list = []

    def _commit():
        nonlocal current_key, current_list
        if current_key is not None:
            result[current_key] = _coerce(current_key, current_list)
        current_key = None
        current_list = []

    for line in raw_block.splitlines():
        if not line.strip():
            continue

        # Continuation of a list block: `  - value`
        stripped = line.strip()
        if current_key is not None and stripped.startswith("- "):
            value = stripped[2:].strip().strip('"\'')
            if value:
                current_list.append(value)
            continue

        # New top-level key.
        m = re.match(r"^([a-zA-Z][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            _commit()
            continue

        key, value = m.group(1), m.group(2).strip()
        _commit()

        if key not in LIST_FIELDS:
            continue

        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            entries = [e.strip().strip('"\'') for e in inner.split(",") if e.strip()]
            result[key] = _coerce(key, entries)
            continue

        if value == "" or value == "[]":
            current_key = key
            current_list = []
            continue

        result[key] = _coerce(key, [value])

    _commit()
    return result


def _coerce(key: str, values: list[str]) -> list:
    """Coerce list entries to int for fields that expect numbers."""
    if key == "also-touches":
        coerced: list[int] = []
        for v in values:
            try:
                coerced.append(int(v))
            except (TypeError, ValueError):
                continue
        return coerced
    return list(values)
