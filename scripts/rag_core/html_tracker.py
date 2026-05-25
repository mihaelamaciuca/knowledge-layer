"""HTML capability-area tracker parser.

The project tracker is published as an HTML file that embeds a JS
literal `var A = [...]` describing every area, phase, item, and decision.
The parser converts this array into chunkable text so the tracker is
searchable in the RAG.

This is verbatim-equivalent to the v1 logic in populate.py, pulled into
rag_core so the Action and the bulk indexer share one implementation.

Input contract: an HTML file body containing `var A = [...];` somewhere.
Output contract: a list of dicts with keys
    source_file, section_header, area_number, doc_type, content, content_hash
"""
import hashlib
import json
import re
from pathlib import Path


def _js_to_json(js_text: str) -> str:
    """Convert JS object notation to valid JSON by quoting bare keys.

    Processes character-by-character to avoid modifying content inside strings.
    Handles backslash escapes inside strings.
    """
    result: list[str] = []
    i = 0
    in_string = False
    escape_next = False

    while i < len(js_text):
        c = js_text[i]

        if escape_next:
            result.append(c)
            escape_next = False
            i += 1
            continue

        if c == "\\" and in_string:
            result.append(c)
            escape_next = True
            i += 1
            continue

        if c == '"' and not escape_next:
            in_string = not in_string
            result.append(c)
            i += 1
            continue

        if in_string:
            result.append(c)
            i += 1
            continue

        if c.isalpha() or c == "_":
            j = i
            while j < len(js_text) and (js_text[j].isalnum() or js_text[j] == "_"):
                j += 1
            ident = js_text[i:j]
            k = j
            while k < len(js_text) and js_text[k] in " \t":
                k += 1
            if k < len(js_text) and js_text[k] == ":":
                result.append('"' + ident + '"')
                i = j
                continue
            result.append(ident)
            i = j
            continue

        result.append(c)
        i += 1

    return "".join(result)


def _render_area(area: dict) -> str:
    """Render a single area/phase object as readable text for embedding."""
    lines: list[str] = []
    name = area.get("n", "Untitled")
    lines.append(f"# {name}")
    if area.get("tg"):
        lines.append(f"Scope: {area['tg']}")
    lines.append(f"Status: {area.get('s', 'unknown')}")
    lines.append("")

    for group in area.get("sg", []):
        group_name = group.get("n")
        if group_name:
            lines.append(f"## {group_name}")
        for item in group.get("it", []):
            parts = [f"- {item['n']}"]
            if item.get("s"):
                parts.append(f"[{item['s']}]")
            if item.get("o"):
                parts.append(f"(owner: {item['o']})")
            if item.get("y"):
                parts.append(f"(type: {item['y']})")
            line = " ".join(parts)
            if item.get("nt"):
                line += f", {item['nt']}"
            lines.append(line)
        lines.append("")

    decisions = area.get("d", [])
    if decisions:
        lines.append("## Decisions")
        for dec in decisions:
            lines.append(f"- {dec.get('x', '')}")
        lines.append("")

    deferred = area.get("df", [])
    if deferred:
        lines.append("## Deferred")
        for item in deferred:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def parse_html_tracker(html_text: str, source_file: str,
                      filename_stem: str) -> list[dict]:
    """Parse an HTML tracker body and return chunk dicts.

    Each area in the JS array becomes one chunk with source_file,
    section_header, area_number, doc_type, content, and content_hash.

    Returns an empty list if no `var A = [...]` array is found or the
    JS-to-JSON conversion fails.
    """
    m = re.search(r"var A\s*=\s*(\[.*?\]);", html_text, re.DOTALL)
    if not m:
        return []

    js_text = m.group(1)
    json_text = _js_to_json(js_text)
    json_text = re.sub(r",\s*([}\]])", r"\1", json_text)

    try:
        areas = json.loads(json_text)
    except json.JSONDecodeError:
        return []

    if "capability-areas" in filename_stem:
        doc_type = "fwk"
    elif "tracker" in filename_stem:
        doc_type = "tracker"
    else:
        doc_type = None

    chunks: list[dict] = []
    for area in areas:
        content = _render_area(area)
        if not content.strip():
            continue

        area_number = None
        raw_id = area.get("id")
        if raw_id is not None:
            try:
                area_number = int(raw_id)
            except (ValueError, TypeError):
                pass

        chunks.append({
            "source_file": source_file,
            "section_header": area.get("n", "Untitled"),
            "area_number": area_number,
            "doc_type": doc_type,
            "content": content,
            "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })

    return chunks


def parse_html_tracker_file(path: Path, docs_dir: Path,
                            repo_prefix: str = "{{PROJECT_NAME}}") -> list[dict]:
    """File-path convenience wrapper for parse_html_tracker."""
    rel_path = path.relative_to(docs_dir)
    source_file = f"{repo_prefix}/docs/{rel_path}"
    return parse_html_tracker(
        path.read_text(encoding="utf-8"),
        source_file=source_file,
        filename_stem=path.stem,
    )
