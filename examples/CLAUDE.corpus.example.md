# CLAUDE.md, corpus authoring

**Worked example.** A constraint sheet for an agent writing and maintaining documents in a knowledge-layer corpus. Copy it to `CLAUDE.md` at the root of your fork and replace the project-specific lines (the project description, the excluded-field names, the area table). Keep the structure and the rules.

**Filename note.** This file is `CLAUDE.corpus.example.md`, not `CLAUDE.md`, on purpose. Claude Code reads `CLAUDE.md` from the directory a session is rooted at; a literal `examples/CLAUDE.md` could silently activate for anyone opening a session at `examples/`. The `.example.md` suffix prevents that.

**How this relates to `CLAUDE.example.md`.** The sibling [`CLAUDE.example.md`](CLAUDE.example.md) is the other half of the job: constraints for the application a team *builds* from the specs (stack, imports, tenant isolation, migrations). This file governs the *corpus*: how to write the documents that feed the index. A corpus-only fork uses this one. A fork that also builds an app in the same tree merges both into a single root `CLAUDE.md`.

This file is read automatically by Claude Code at the start of every session. It is a constraint sheet, not a spec. The authoritative detail lives in `docs/00-pol-document-standards.md` (the policy) and `docs/00-fwk-writing-guide.md` (the guide with examples); read those when a rule needs its rationale.

---

## What this repo is

[Replace with your project. Example:]

This repo holds the knowledge layer for [project name]. The `docs/` directory is the source of truth: every document is chunked, scrubbed, embedded, and indexed into Postgres + pgvector, then served to AI clients over MCP and to humans through the docs site. If a fact is not in `docs/`, the system does not know it.

Stack: Python 3.12+, FastAPI, the MCP Streamable HTTP transport, Postgres + pgvector, OpenAI embeddings. The indexer and the MCP server live in this same tree as the corpus; documents and the code that serves them evolve together.

---

## Repo layout

```
docs/                     the corpus, one markdown file per document
  00-pol-document-standards.md   the standards every doc must meet
  00-fwk-writing-guide.md        the five writing rules, with examples
  00-fwk-doc-hygiene-loop.md     the weekly maintenance loop
  00-fwk-project-tracker.md      the tracker (see "Maintenance" below)
scripts/
  populate.py             full or incremental indexer
  audit_docs_standards.py validates frontmatter, refs, section sizes
  detect_drift.py         computes the four drift signals
  build_decision_registry.py   parses decisions: blocks into the registry
  rag_core/               chunker, embed, scrub, frontmatter, upsert
  doc_rename_map.json      old-slug to new-slug map for renames
src/                      FastAPI MCP server (the seven tools)
.github/workflows/
  audit-docs.yml          runs the audit + scrub test on every PR
  sync-to-rag.yml         incremental reindex of changed docs on push
  reindex.yml             manual full reindex (workflow-dispatch)
```

---

## Writing documents for vector search

Every document in `docs/` is split into chunks at `##` headings, embedded independently, and matched against queries by meaning. Search quality depends directly on how the prose is written. These five rules apply to every document you write or edit. Of the five, the audit machine-enforces only the size limit; the other four are yours to apply while authoring, and a reviewer rechecks them on the diff. (The same audit also checks frontmatter, filenames, and references, covered below.)

### Section summaries after every heading

After every `##` heading, write one line carrying the terms someone would actually search for. The summary is embedded with the section and gives the model a strong signal.

```markdown
## Authentication middleware, JWT validation, token refresh, session expiry

Covers how the API validates JWT tokens on every request, how refresh
tokens extend sessions, and what happens when a session expires after
30 days of inactivity.
```

A bare `## Authentication` embeds too vaguely to match anything specific.

### Inline cross-references, never bare ones

Never write "see section 9." Inline what section 9 says, so the chunk carries the meaning on its own.

```markdown
<!-- wrong: the chunk has no searchable meaning -->
Account deletion follows the process in the data retention policy section 4.

<!-- right: the chunk is findable and self-contained -->
Account deletion follows the 12-step cascade in the data retention policy
(section 4): R2 objects first, then database rows, then the identity
provider account.
```

### One concept per section

A chunk becomes a single vector, an average of the meanings in the text. If you cannot summarise a section in one sentence with searchable keywords, it holds more than one concept; split it into focused `##` sections.

### Concrete searchable terms, not abstract jargon

Write the way a person phrases the question, not the way an architect describes the design. "16-day grace period where the user keeps full access" beats "configurable access retention window." Same thing, only one is findable.

### Sections under 4000 characters

The chunker (`scripts/rag_core/chunker.py`, `MAX_CHUNK_CHARS = 4000`) splits oversized sections on `###` subheaders first, then on paragraph boundaries, falling back to a hard cut. A hard cut produces two incoherent chunks. If a section runs long, break it into `###` subsections, move code and tables into their own sections. The audit flags any `##` section over the limit.

---

## Frontmatter, required on every document

Every file in `docs/` opens with a YAML block. The audit validates it on every PR and builds the dependency graph from it.

```yaml
---
file: 03-spec-search-api          # filename without .md, must match the file
area: 3                           # integer matching the leading two digits
area-name: Engineering            # human-readable area name
type: spec                        # one of: spec, res, str, dec, pol, fwk
title: Search API                 # human-readable title
status: draft                     # draft | in-progress | complete | superseded | needs-review
date: 2026-01-15                  # YYYY-MM-DD, last substantive update
depends-on:                       # docs this one assumes are current; [] if none
  - 03-dec-tech-stack
feeds-into:                       # docs or area-N-name this one feeds; [] if none
  - area-3-engineering
---
```

Optional: `also-touches` (secondary area numbers), `supersedes` (the filename this document replaces).

- **Filename convention:** `[area]-[type]-[name].md`, name lowercase and hyphenated, two to four words.
- **Never omit `depends-on` or `feeds-into`.** Use `[]` when there are none; they populate the graph that `get_impact_targets` and `get_doc_neighborhood` walk.
- **Superseding a document:** set the old one to `status: superseded`, add `supersedes: <old-file>` to the replacement. The old document stays searchable behind a banner.
- **Renaming a document:** record the old slug in `scripts/doc_rename_map.json`; run `python3 scripts/audit_docs_standards.py --fix` to migrate references in bulk.

---

## Query the corpus before you act

Before changing settled work, ask the corpus. The MCP server exposes seven tools:

- `search_docs` finds material by meaning, with filters on `status`, `area`, `doc_type`.
- `get_decision` returns the current position on a topic, with a `[CURRENT]` / `[SUPERSEDED]` / `[DRAFT]` banner. Act on `[CURRENT]` only.
- `get_impact_targets` returns the documents affected by a change before you make it.
- `get_doc_neighborhood` shows what a document depends on and what depends on it.
- `get_doc_outline` returns the section tree of a long document.
- `get_drift_report` lists stale claims (see Maintenance).
- `check_index_health` reports per-file chunk counts and staleness.

Quote provenance (`source_file`, `status`, `git_committed_at`) when you rely on a result. Do not act on a `[SUPERSEDED]` or `[DRAFT]` answer as if it were settled.

---

## RAG infrastructure

- **Embedding model:** OpenAI `text-embedding-3-small`, 1536 dimensions (`scripts/rag_core/embed.py`).
- **Chunk size limit:** 4000 characters, split on `##` then `###` headings.
- **Retrieval:** hybrid vector + lexical, minimum similarity 0.35, default 10 results per query (max 20) (`src/search.py`).
- **Incremental sync:** `sync-to-rag.yml` reindexes only changed `docs/**` on push.
- **Full reindex:** `python scripts/populate.py --docs-dir docs --full-reindex` (or the `reindex.yml` workflow). Use it when the chunker, the embedding model, or the excluded-field list changes.

---

## Maintenance

**The weekly hygiene loop.** Once a week, run `get_drift_report(top=10)` and triage the top items. Each arrives with file, line, signal, reason, authoritative source, and a suggested fix. Fix the self-contained ones, skip false positives, mark the rest `status: needs-review`. Stop after fifteen minutes. Full detail in `docs/00-fwk-doc-hygiene-loop.md`.

**The tracker, the final step of every session.** After committing and pushing work, update `docs/00-fwk-project-tracker.md` in the same session: mark what was completed, add tasks or gaps the work revealed, remove items that turned out unnecessary, then commit the tracker update. The session is not done until the tracker reflects what was built.

---

## What not to do

- **No secrets in `docs/`.** No API keys, tokens, passwords, connection strings, or PII. Add any value-bearing field name to `EXCLUDED_FIELDS` in `scripts/rag_core/scrub.py`; it is redacted at index time and the scrub test fails the build if anything leaks.
- **No binary files in `docs/`.** Markdown only.
- **Do not write to the database directly.** All writes go through `populate.py` or the CI workflows.
- **Do not change the chunker without a full reindex.** Editing `scripts/rag_core/chunker.py` changes chunk boundaries for every document; follow it with `reindex.yml`, or the index and the corpus drift apart.
- **Do not merge with a red audit.** A PR that breaks the standards cannot merge with branch protection on; fix the violations in the same session.
