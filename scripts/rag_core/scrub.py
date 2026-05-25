"""Governance scrub for project-specific excluded fields.

Enforces field-exclusion rules at index time, before any embedding call
is made. Customise `EXCLUDED_FIELDS` for your project, these are the
fields that MUST NOT appear in indexed `doc_chunks.content` in their
value-bearing form (typically: PII, secrets, anything you'd never want
to leak through a search result).

The scrub redacts VALUES, not field-name mentions. Doc text that explains
the system ("the `account_id` field stores …") is preserved.
Value-bearing assignments are redacted ("account_id: abc-123" →
"account_id: [REDACTED:account_id]").

Match strategy: literal field name (case-insensitive), structured-data
signal required (quoted value with any separator, OR `=` separator with
bare token). Bare `:` + bare value is treated as prose (markdown labels
like `**Email:** description` are left alone), quote the value to force
redaction.

Customise:
    1. Add field names to `EXCLUDED_FIELDS` below.
    2. Document them in your CLAUDE.md / data governance doc.
    3. Add fixtures to scripts/scrub_test.py to lock in the behaviour.
    4. CI fails on any doc that would emit an excluded field through the
       fixture test (PR-time) and the indexer skip-list (sync-time).
"""
import re

EXCLUDED_FIELDS: list[str] = [
    # Add your project's excluded fields here. Example:
    # "ssn", "credit_card", "personal_email", "api_key",
]

_FIELD_ALTERNATION = "|".join(re.escape(f) for f in EXCLUDED_FIELDS) if EXCLUDED_FIELDS else r"(?!)"

# Two regexes match value-bearing assignments. Splitting them avoids the
# prose false-positive where a markdown label like "**Email:** description"
# would be misread as a field-value pair.

_BASE_PREFIX = (
    r"(?<![a-zA-Z0-9_])"
    r"(" + _FIELD_ALTERNATION + r")"
    r"([\"\']?)"
)

_QUOTED_VALUE_RE = re.compile(
    _BASE_PREFIX
    + r"(\s*[:=]\s*)"
    + r"("
    + r'"(?:[^"\\]|\\.)*"'
    + r"|'(?:[^'\\]|\\.)*'"
    + r")",
    re.IGNORECASE,
)

_EQUALS_BARE_RE = re.compile(
    _BASE_PREFIX
    + r"(\s*=\s*)"
    + r"([^\s,;}\]\[\n\"']+)",
    re.IGNORECASE,
)


def _redact(m: re.Match) -> str:
    value = m.group(4)
    if value.startswith("[REDACTED:") or "[REDACTED:" in value:
        return m.group(0)
    field = m.group(1).lower()
    return f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED:{field}]"


def scrub_content(content: str) -> str:
    """Redact value-bearing assignments of excluded fields.

    Idempotent. Returns content unchanged if no `EXCLUDED_FIELDS` are set
    or if no matches. To force a redaction on a `:`-separator field-value
    pair, quote the value: `field: "value"`.
    """
    if not EXCLUDED_FIELDS:
        return content
    content = _QUOTED_VALUE_RE.sub(_redact, content)
    content = _EQUALS_BARE_RE.sub(_redact, content)
    return content


def find_violations(content: str) -> list[tuple[int, str, str]]:
    """Return (offset, field_name, full_match) for any unscrubbed
    value-bearing assignments. Empty list when content is clean OR when
    `EXCLUDED_FIELDS` is empty.
    """
    if not EXCLUDED_FIELDS:
        return []
    violations: list[tuple[int, str, str]] = []
    for regex in (_QUOTED_VALUE_RE, _EQUALS_BARE_RE):
        for m in regex.finditer(content):
            value = m.group(4)
            if value.startswith("[REDACTED:") or "[REDACTED:" in value:
                continue
            violations.append((m.start(), m.group(1).lower(), m.group(0)))
    return sorted(violations, key=lambda v: v[0])
