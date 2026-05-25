---
file: 00-pol-document-standards
area: 0
area-name: Project Management
type: pol
title: Document Standards
status: complete
date: 2026-04-09
depends-on: []
feeds-into:
  - area-0-project-management
---

# Document Standards

## Capability Area Numbering

Every document belongs to a primary capability area. Areas are numbered 00 upward across tiers. Define your own areas below, these are examples.

### Meta

| # | Area | Scope |
|---|---|---|
| 00 | Project Management | Capability area definitions, document standards, playbook, project-level governance |

### Foundation

| # | Area | Scope |
|---|---|---|
| 01 | Strategy & Identity | Vision, mission, values, strategic positioning, naming |
| 02 | Product | Personas, feature spec, UX, user journeys, wireframes, roadmap |

### Build

| # | Area | Scope |
|---|---|---|
| 03 | Engineering | Architecture, backend, frontend, database, auth, infra, CI/CD |
| 04 | Data | Data strategy, governance, analytics, signals |

### Protect

| # | Area | Scope |
|---|---|---|
| 05 | Legal & Compliance | GDPR, privacy policy, terms, DPIA, IP, entity formation |
| 06 | Security & Trust | Content safety, access control, audit trail |

### Sustain & Grow

| # | Area | Scope |
|---|---|---|
| 07 | Business & Finance | Unit economics, pricing, financial model, cost management |
| 08 | Operations & Growth | Risk register, incident response, vendors, monitoring, GTM, launch |

Adding areas: new areas get the next number. Area 00 is reserved for project management. Never renumber existing areas.

---

## Document Types

Six types. Controlled vocabulary, no exceptions.

| Type | Code | What it is | How to read it |
|---|---|---|---|
| Specification | `spec` | Prescriptive. Tells you what to build or how something works. | Follow it. |
| Research | `res` | Informational. Analysis of a question. Findings, not instructions. | Learn from it. |
| Strategy | `str` | Directional. Where we're going and why. Long-lived reference. | Align to it. |
| Decision | `dec` | Records a choice, its options, rationale, and what it settled. | Respect it. |
| Policy | `pol` | Rules to follow. Enforceable, versioned. | Comply with it. |
| Framework | `fwk` | A reusable structure for making decisions or evaluations. | Apply it. |

Choosing a type: if a document records a settled choice -> `dec`. If it defines rules -> `pol`. If it sets long-term direction -> `str`. If it prescribes how something is built -> `spec`. If it analyses a question -> `res`. If it's a reusable tool for assessment -> `fwk`. Every document fits exactly one type.

---

## File Naming Convention

Pattern: `[area]-[type]-[name].md`

- **area**: two-digit number (00, 01, 02, ...)
- **type**: three-letter code from the type vocabulary (spec, res, str, dec, pol, fwk)
- **name**: lowercase, hyphenated, descriptive

Examples:
- `03-spec-architecture.md`
- `02-res-competitive-landscape.md`
- `01-str-vision-mission.md`
- `03-dec-tech-stack.md`
- `05-pol-data-retention.md`
- `07-fwk-pricing-model.md`

Rules:
- No version numbers in filenames. Version history lives in git.
- No spaces, no underscores, no uppercase.
- Name should be short and recognisable. Target 2-4 words.
- Cross-cutting documents live under their primary area. The `also-touches` metadata field captures secondary areas.

---

## Metadata (YAML Frontmatter)

Every document in `docs/` begins with this frontmatter block:

```yaml
---
file: 03-spec-architecture
area: 3
area-name: Engineering
type: spec
title: System Architecture
status: draft | in-progress | complete | superseded | needs-review
date: 2026-01-15
depends-on:
  - 03-dec-tech-stack
  - 01-str-vision-mission
feeds-into:
  - 03-spec-build-guide-s1
  - area-4-data
also-touches: [4, 6]
supersedes: null
---
```

### Field definitions

| Field | Required | Description |
|---|---|---|
| `file` | Yes | Matches filename without `.md` |
| `area` | Yes | Primary area number |
| `area-name` | Yes | Human-readable area name |
| `type` | Yes | Document type code (spec, res, str, dec, pol, fwk) |
| `title` | Yes | Human-readable document title |
| `status` | Yes | One of: `draft`, `in-progress`, `complete`, `superseded`, `needs-review` |
| `date` | Yes | Date of last substantive update (YYYY-MM-DD) |
| `depends-on` | Yes | List of document filenames (without `.md`) this document reads from. Empty list `[]` if none. |
| `feeds-into` | Yes | List of document filenames or `area-[N]-[name]` references this document feeds. Empty list `[]` if none. |
| `also-touches` | No | List of area numbers this document affects beyond its primary area. |
| `supersedes` | No | Filename of the document this one replaced. |

### Status definitions

- **draft**: Work in progress. Incomplete. May change substantially.
- **in-progress**: Structure set, content being filled in. Core decisions may still shift.
- **complete**: Done for the current stage. May be updated but the substance is settled.
- **superseded**: Replaced by another document. The `supersedes` field in the replacement points here.
- **needs-review**: The doc-hygiene loop flagged this doc as potentially drifting. It stays searchable but is bannered in `search_docs` results until reviewed and re-marked `complete` (or `superseded`).

---

## Section Header Conventions

The retrieval system splits documents into chunks at `##` section headers. Header quality directly determines retrieval quality.

Write headers as specific, searchable phrases:

| Weak | Strong |
|---|---|
| `## Notes` | `## Known Limitations` |
| `## Background` | `## Why This Decision Was Made` |
| `## Details` | `## API Rate Limit Behaviour` |

Rules:
- Every document must have at least one `##` header.
- Keep sections to a focused topic.
- Do not nest beyond `###`. Content under `###` stays within its parent `##` chunk.

---

## Writing for Vector Search

Every document in `docs/` is chunked and embedded into the pgvector index. These rules are mandatory.

### Section summaries

After every `##` heading, add a one-line plain-language summary with searchable terms.

### Inline cross-references

Never use bare cross-references. Always inline what the referenced section says before citing the source.

### Section length limit

Keep sections under 4000 characters. The chunker splits on `##` headings. Long sections get split mechanically at character boundaries, losing coherence.

### Concrete terms

Use the terms someone would actually search for, not abstract jargon.

### One concept per section

A section covering many unrelated points retrieves well for none of them. Split into focused sections.

---

## Sync Workflow

GitHub `docs/` is the source of truth. The RAG index is auto-updated on every push to main.

| Parameter | Value |
|-----------|-------|
| Embedding model | OpenAI `text-embedding-3-small`, 1536 dimensions |
| Max chunk size | 4000 characters |
| Similarity threshold | 0.35 minimum |
| Default results per query | 10 (max 20) |
