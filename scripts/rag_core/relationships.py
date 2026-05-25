"""Frontmatter graph extraction + doc_relationships writes.

The corpus ships an authored dependency graph in every doc's
YAML frontmatter (depends-on, feeds-into, also-touches, supersedes).
This module exposes:

    extract_relationships(metadata)
        Returns list of (relation, target) tuples for one doc.

    replace_relationships(cur, source_file, edges)
        DELETE existing rows for source_file, then INSERT the new edges.
        Idempotent. Used by the indexer in rag_core.sync.

Target normalisation: bare filename form (no .md suffix, no path
prefix). Area-N-name refs (e.g. `area-9-responsible-ai`) and bare area
numbers (from also-touches) are kept verbatim. The neighborhood
resolver (src/neighborhood.py) is responsible for mapping bare targets
back to doc_chunks.source_file when the consumer wants chunk metadata.

Replaces the earlier placeholder with the real implementation.
"""

RELATION_TYPES = ("depends_on", "feeds_into", "also_touches", "supersedes")

_NULL_VALUES = {"null", "Null", "NULL", "~", "", "None"}


def _normalize_target(value) -> str:
    """Strip whitespace, quotes, and `.md` suffix from a frontmatter ref."""
    if value is None:
        return ""
    s = str(value).strip().strip('"\'')
    if s in _NULL_VALUES:
        return ""
    if s.endswith(".md"):
        s = s[:-3]
    return s


def extract_relationships(metadata: dict) -> list[tuple[str, str]]:
    """Return list of (relation, target) edges declared by this doc.

    `metadata` is the dict returned by frontmatter.parse_frontmatter_v2.
    Empty/missing values yield no edges. Self-loops (a doc declaring a
    dependency on itself) are filtered out by the caller.
    """
    edges: list[tuple[str, str]] = []

    for ref in metadata.get("depends-on") or []:
        target = _normalize_target(ref)
        if target:
            edges.append(("depends_on", target))

    for ref in metadata.get("feeds-into") or []:
        target = _normalize_target(ref)
        if target:
            edges.append(("feeds_into", target))

    for area in metadata.get("also-touches") or []:
        if isinstance(area, int) or (isinstance(area, str) and area.isdigit()):
            edges.append(("also_touches", str(area)))

    supersedes = metadata.get("supersedes")
    if supersedes is not None:
        target = _normalize_target(supersedes)
        if target:
            edges.append(("supersedes", target))

    return edges


def replace_relationships(cur, source_file: str,
                          edges: list[tuple[str, str]]) -> None:
    """Replace all rows for source_file with the given edges. Idempotent."""
    cur.execute(
        "DELETE FROM doc_relationships WHERE source_file = %s",
        (source_file,),
    )
    if not edges:
        return

    # Dedupe, frontmatter authors sometimes duplicate entries.
    deduped = sorted(set(edges))
    cur.executemany(
        "INSERT INTO doc_relationships (source_file, relation, target) "
        "VALUES (%s, %s, %s)",
        [(source_file, relation, target) for relation, target in deduped],
    )


def delete_relationships_for_source(cur, source_file: str) -> int:
    """Delete all rows for a single source_file. Returns count deleted."""
    cur.execute(
        "DELETE FROM doc_relationships WHERE source_file = %s",
        (source_file,),
    )
    return cur.rowcount


def to_bare(source_file: str) -> str:
    """Convert doc_chunks-style source_file to bare frontmatter form.

    Examples:
        {{PROJECT_NAME}}/docs/03-dec-tech-stack.md → 03-dec-tech-stack
        {{PROJECT_NAME}}/docs/00-fwk-project-tracker.md → 00-fwk-project-tracker
    """
    bare = source_file.rsplit("/", 1)[-1]
    if bare.endswith(".md"):
        bare = bare[:-3]
    return bare


def to_full(bare: str, repo: str = "{{PROJECT_NAME}}") -> str:
    """Convert bare frontmatter form to doc_chunks-style source_file."""
    return f"{repo}/docs/{bare}.md"
