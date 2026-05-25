"""Markdown chunking by `##` section header, with `###` and char-split fallbacks.

Sections over MAX_CHUNK_CHARS are split first by `###` sub-headers, then by
character count. The character-count fallback prefers paragraph breaks
(`\\n\\n`) within the search window, falling back to the nearest whitespace,
falling back to a hard cut at MAX_CHUNK_CHARS. This avoids splitting
mid-word in long prose or code blocks.

Header naming for sub-chunks: when a `##` section is split by `###`, the
sub-chunks are labelled `<h2> > <h3>`. When further split by size, suffix
`(part N)` is appended.
"""

MAX_CHUNK_CHARS = 4000
# Within the trailing 20% of a chunk, look for a clean break point.
_SOFT_BREAK_WINDOW = int(MAX_CHUNK_CHARS * 0.2)


def _split_by_heading(body: str, prefix: str) -> list[tuple[str, str]]:
    """Split markdown body into (header, content) pairs on lines starting with `prefix`.

    Content before the first matching heading is assigned header "(intro)".
    Headings of deeper levels (`prefix + "#"`) are ignored as splits.
    """
    chunks: list[tuple[str, str]] = []
    current_header = "(intro)"
    current_lines: list[str] = []

    for line in body.splitlines():
        if line.startswith(prefix) and not line.startswith(prefix + "#"):
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append((current_header, content))
            current_header = line.lstrip("# ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()
    if content:
        chunks.append((current_header, content))

    return chunks


def _find_soft_break(text: str, limit: int) -> int:
    """Within text[0:limit], find a break point that doesn't split a word.

    Preference order:
        1. Last paragraph break (`\\n\\n`) within the soft-break window.
        2. Last newline within the window.
        3. Last whitespace within the window.
        4. `limit` (hard cut) when no soft break is available.

    Always returns at least limit // 2 to prevent pathological tiny chunks
    on text with no whitespace.
    """
    if len(text) <= limit:
        return len(text)
    window_start = max(limit // 2, limit - _SOFT_BREAK_WINDOW)
    window = text[window_start:limit]
    for needle in ("\n\n", "\n", " "):
        idx = window.rfind(needle)
        if idx != -1:
            return window_start + idx + len(needle)
    return limit


def _split_by_size(header: str, text: str) -> list[tuple[str, str]]:
    """Split a single string into sequential pieces of at most MAX_CHUNK_CHARS,
    preserving word/paragraph boundaries where possible."""
    pieces: list[tuple[str, str]] = []
    remainder = text
    while remainder:
        if len(remainder) <= MAX_CHUNK_CHARS:
            part = remainder.strip()
            if part:
                suffix = f" (part {len(pieces) + 1})" if pieces else (" (part 1)" if len(text) > MAX_CHUNK_CHARS else "")
                pieces.append((header + suffix, part))
            break
        cut = _find_soft_break(remainder, MAX_CHUNK_CHARS)
        part = remainder[:cut].strip()
        if part:
            suffix = f" (part {len(pieces) + 1})"
            pieces.append((header + suffix, part))
        remainder = remainder[cut:]
    return pieces


def chunk_by_h2(body: str) -> list[tuple[str, str]]:
    """Split markdown body into (section_header, content) pairs on `##` headings.

    Oversized chunks are further split by `###` sub-headers, then by character limit.
    Returns an empty list for empty input or input with no content lines.
    """
    h2_chunks = _split_by_heading(body, "## ")

    final: list[tuple[str, str]] = []
    for header, content in h2_chunks:
        if len(content) <= MAX_CHUNK_CHARS:
            final.append((header, content))
            continue

        h3_chunks = _split_by_heading(content, "### ")
        for h3_header, h3_content in h3_chunks:
            sub_header = f"{header} > {h3_header}" if h3_header != "(intro)" else header
            if len(h3_content) <= MAX_CHUNK_CHARS:
                final.append((sub_header, h3_content))
            else:
                final.extend(_split_by_size(sub_header, h3_content))

    return final
