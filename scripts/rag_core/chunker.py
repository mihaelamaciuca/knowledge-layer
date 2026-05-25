"""Markdown chunking by `##` section header, with `###` and char-split fallbacks.

Matches the v1 chunker semantics exactly so the corpus does not need to be
re-embedded after the refactor. Sections over MAX_CHUNK_CHARS are split first
by `###` sub-headers, then by character count.

Header naming for sub-chunks: when a `##` section is split by `###`, the
sub-chunks are labelled `<h2> > <h3>`. When further split by size, suffix
`(part N)` is appended.
"""

MAX_CHUNK_CHARS = 4000


def _split_by_heading(body: str, prefix: str) -> list[tuple[str, str]]:
    """Split markdown body into (header, content) pairs on lines starting with `prefix`.

    Content before the first matching heading is assigned header "(intro)".
    Headings of deeper levels (prefix + "#") are not treated as splits.
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


def _split_by_size(header: str, text: str) -> list[tuple[str, str]]:
    """Split a single string into sequential pieces of at most MAX_CHUNK_CHARS."""
    pieces: list[tuple[str, str]] = []
    for i in range(0, len(text), MAX_CHUNK_CHARS):
        part = text[i:i + MAX_CHUNK_CHARS].strip()
        if part:
            suffix = f" (part {len(pieces) + 1})" if len(text) > MAX_CHUNK_CHARS else ""
            pieces.append((header + suffix, part))
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
