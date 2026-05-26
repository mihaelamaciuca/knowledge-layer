---
file: 00-fwk-writing-guide
area: 0
area-name: Project Management
type: fwk
title: Writing guide for vector retrieval
status: complete
date: 2026-05-25
depends-on:
  - 00-pol-document-standards
feeds-into:
  - area-0-project-management
---

# Writing guide for vector retrieval

## Purpose

Practical reference for writing documents that retrieve well, paired with two siblings. `docs/00-pol-document-standards.md` is the policy that declares the rules and lists every required frontmatter field. `methodology.md` at the repo root explains why each rule exists and what embedding-failure mode it addresses. Read those for the rationale; use this guide while authoring or revising a document.

## Terms used in this guide

A handful of nouns this guide leans on:

- **Embedding**, a numeric vector that represents the meaning of a piece of text. Similar meanings produce vectors near each other; that nearness is what search uses to rank.
- **Chunk**, the unit of retrieval. In this repo, one `##` section of a markdown doc becomes one chunk (capped at 4000 characters; see rule 5).
- **Frontmatter**, the YAML block at the top of every doc, declaring its metadata (file, type, status, dependency edges).
- **Audit script**, `scripts/audit_docs_standards.py`. Runs on every PR via `.github/workflows/audit-docs.yml`. To run it locally: `python3 scripts/audit_docs_standards.py`.
- **Claude Code**, Anthropic's IDE-integrated AI assistant. At the start of every session in this repo it reads the root `CLAUDE.md` and applies its rules when authoring documents.
- **MCP tools** (`search_docs`, `get_decision`, `get_impact_targets`, `get_doc_neighborhood`, `get_doc_outline`, `get_drift_report`, `check_index_health`), functions the MCP server exposes for AI clients (Claude Code, Claude.ai) to query the indexed corpus.

## Quick reference

The five rules, by keyword: section summaries, inline cross-references, one concept per section, concrete searchable terms, size limit.

| Rule | What to do | Why |
|---|---|---|
| Section summaries | One-line summary after every `##` heading | Gives the embedding model a strong signal to match against |
| Inline cross-references | Never write "see section X"; inline what section X says | Each chunk is embedded independently, bare references have no searchable meaning |
| One concept per section | Each section covers one topic | Focused sections produce sharp embeddings; mixed topics produce blurry ones |
| Concrete terms | Write the way people search | "16-day grace period" not "configurable retention window" |
| Size limit | Keep sections under 4000 characters | Oversized chunks get split mechanically and lose coherence |

## Section summaries, mandatory after every heading

After every `##` heading, write one line that includes the searchable terms a person would actually type. (See `methodology.md` for why this is the highest-leverage rule.)

### Good

```markdown
## Authentication middleware, JWT validation, token refresh, session expiry

Covers how the API validates JWT tokens on every request, how refresh
tokens extend sessions, and what happens when a session expires after
30 days of inactivity.
```

### Bad

```markdown
## Authentication

This section describes the authentication system.
```

The first version matches searches for "JWT validation," "token refresh," "session expiry," and "30 days." The second only matches the generic term "authentication."

## Inline cross-references, never bare pointers

Every cross-reference must carry the meaning of what it points to inside the chunk itself.

### Good

```markdown
Account deletion follows the 12-step cascade defined in the data
retention policy (section 4): R2 objects deleted first, then database
rows, then the identity provider account. A crash during deletion must
leave orphaned storage objects (recoverable) rather than orphaned
database references.
```

### Bad

```markdown
Account deletion follows the process in the data retention policy
section 4.
```

The first is findable by "account deletion," "12-step cascade," "R2 objects," or "orphaned database references." The second is only findable by "account deletion" and "data retention policy."

## One concept per section, split when topics differ

When a section covers more than one topic, split it. If you cannot summarise the section in one sentence with searchable keywords, you have more than one concept.

### Good

```markdown
## Grace period, 16 days full access during payment retry

When a subscription payment fails, the user keeps full access for
16 days while the payment provider retries...

## Billing retry, what's blocked during recovery

After the grace period, the user can still access existing content
but cannot create new content until payment succeeds...

## Subscription expiry, access revoked after 60 days

If payment is not recovered within 60 days, the subscription expires
and access is fully revoked...
```

### Bad

```markdown
## Subscription lifecycle

When payment fails there's a 16-day grace period, then billing retry
blocks new content, and after 60 days the subscription expires...
```

The first produces three sharp embeddings, each matched by a different query. The second produces one blurry embedding that no specific query matches well.

## Concrete searchable terms, the words people actually type

Write the way a person would phrase the question, not the way an architect would describe the design.

### Good

```markdown
The parent keeps full access for 16 days while the payment provider
retries the failed payment.
```

### Bad

```markdown
Configurable access retention window during payment recovery.
```

Both describe the same thing. Only the concrete version matches the searches people actually type ("how long is the grace period," "what happens when payment fails").

## Size limit, 4000 characters per section

The chunker (`scripts/rag_core/chunker.py`) splits on `##` headings; sections over 4000 characters get split mechanically. The fallback prefers paragraph and word boundaries, but the result is still two incomplete chunks rather than one coherent one. If a section is getting long:

1. Look for natural sub-topics and split into `###` subsections. The chunker prefers `###` over a character-window cut.
2. Move code examples into their own subsections.
3. Extract tables into their own sections with descriptive headings.

The audit script flags any `##` section over 4000 characters; the audit runs on every PR (`audit-docs.yml`) and blocks merge if branch protection is configured. To check locally before pushing: `python3 scripts/audit_docs_standards.py` (writes a report to `docs-standards-audit.md` at the repo root).

## YAML frontmatter, the structured metadata block

Every document under `docs/` begins with a YAML frontmatter block. Required fields and the controlled vocabularies the audit enforces:

- `file`, the filename without `.md`, matching the file itself
- `area`, integer matching the leading two digits of the filename
- `area-name`, human-readable name for the area; project-defined (see the area table in `00-pol-document-standards.md`)
- `type`, one of `spec`, `res`, `str`, `dec`, `pol`, `fwk`
- `title`, human-readable document title
- `status`, one of `draft`, `in-progress`, `complete`, `superseded`, `needs-review`
- `date`, `YYYY-MM-DD`, the date of the last substantive update
- `depends-on`, list of doc filenames (without `.md`) this doc reads from; `[]` if none
- `feeds-into`, list of doc filenames or `area-N-name` references this doc feeds; `[]` if none

Optional: `also-touches` (list of secondary area numbers), `supersedes` (filename of the doc this one replaced).

The minimum block:

```yaml
---
file: 03-spec-architecture
area: 3
area-name: Engineering
type: spec
title: System Architecture
status: complete
date: 2026-01-15
depends-on:
  - 03-dec-tech-stack
feeds-into:
  - area-3-engineering
---
```

The `depends-on` and `feeds-into` lists populate the dependency graph that `get_doc_neighborhood` and `get_impact_targets` traverse. Use an empty list `[]` if there are no dependencies; never omit the field.

## Document naming, the [area]-[type]-[name] pattern

Filenames follow `[area]-[type]-[name].md`. The audit script enforces the regex on every PR and flags non-matching filenames as `filename-pattern` violations.

- **area**, two-digit number matching the `area` frontmatter field (00, 01, 02, ...)
- **type**, three-letter code from the controlled set `{spec, res, str, dec, pol, fwk}`
- **name**, lowercase, hyphenated, descriptive; the standards doc targets two to four words

Examples that already live in this repo:

- `00-pol-document-standards.md`
- `00-fwk-doc-hygiene-loop.md`
- `00-fwk-project-tracker.md`
- `03-dec-tech-stack.md`
- `03-res-vector-stores.md`
- `03-spec-search-api.md`

## Checklist for reviewing a document, the gate before merge

Before committing a new or edited document, walk this list. Items 5, 6, 7, and 8 are checked by the audit script on every PR; items 1, 2, 3, and 4 are prose checks Claude Code applies during authoring (and a human reviewer should re-check on the diff).

- [ ] 1. Every `##` heading has a one-line summary with searchable terms
- [ ] 2. No bare cross-references; every reference inlines the key information
- [ ] 3. Each section covers one concept (if you can't summarise it in one sentence, split it)
- [ ] 4. No abstract jargon where concrete terms would work
- [ ] 5. No section exceeds 4000 characters (or has `###` subsections that don't)
- [ ] 6. YAML frontmatter complete: `file`, `area`, `area-name`, `type`, `title`, `status`, `date`, `depends-on`, `feeds-into`
- [ ] 7. Filename matches `[area]-[type]-[name].md`
- [ ] 8. Every `depends-on` and `feeds-into` target resolves to an existing file or to an `area-N-name` reference
