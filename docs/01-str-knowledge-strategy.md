---
file: 01-str-knowledge-strategy
area: 1
area-name: Strategy & Identity
type: str
title: Knowledge strategy, write before acting
status: complete
date: 2026-05-26
depends-on:
  - 00-pol-document-standards
  - 00-fwk-doc-hygiene-loop
feeds-into:
  - 03-dec-tech-stack
---

# Knowledge strategy, write before acting

> **Example document.** Bundled with the template to show what a `str` (strategy) doc looks like with valid frontmatter, principles, key bets, and downstream constraints. Replace or delete when you write your own strategy.

## Strategic context, where our knowledge lives today and why that breaks

Settled knowledge spread across chat, decks, and senior engineers' heads is expensive to retrieve, costly to re-litigate, and slow to onboard against.

For most teams, settled knowledge lives in chat threads, slide decks, and senior engineers' heads. That distribution has three problems. (a) Decisions get re-litigated because nobody can find the original. (b) AI assistants pull from their training data and the public web rather than the team's actual position. (c) Onboarding takes weeks because the institutional context cannot be cheaply queried.

We are choosing not to solve this with a wiki, a Notion workspace, or a per-team RAG bolt-on. The substrate is already covered by the knowledge layer in this repo.

## Strategic position, what our corpus commits to

One markdown corpus at `docs/`, indexed automatically on every push, queryable by humans and agents through the same MCP surface.

Everything written before any action is taken. Writing is part of the work, not an artifact produced after it. Both humans and agents query the same store through the seven MCP tools. Settled decisions live in a structured registry. Drift is paid down on a bounded weekly cadence.

## Principles, the four commitments that guide every doc decision

Four commitments: write-first, self-contained chunks, settled decisions first-class, drift bounded weekly.

1. **Write before you act.** Every spec, decision, and policy is captured in `docs/` before code or change ships. Writing is part of the work, not an artifact produced after.
2. **Self-contained chunks.** Every section is meaningful without cross-references. Inlined context, not bare pointers.
3. **Settled decisions are first-class.** A choice is settled when it has a `*-dec-*.md` file with `status: complete`. Until then it is not citable as the team's position. The `decisions` table is the queryable surface for settled choices, populated from `*-dec-*.md` frontmatter via `scripts/build_decision_registry.py`.
4. **Drift is paid weekly, never accumulated.** The hygiene loop, a 15-minute weekly triage of `get_drift_report(top=10)` documented in `docs/00-fwk-doc-hygiene-loop.md`, clears flagged items before they compound.

## Key bets, what we are committing to and how each could be wrong

Four bets we are making, each with the signal that would tell us we are wrong.

| Bet | Assumption | Invalidation signal |
|-----|------------|---------------------|
| The team will write before acting | Authors trust the loop enough to invest the writing time | Ratio of code commits to doc commits drifts toward code-only |
| Well-written documents beat retrieval sophistication | RAGChecker-style metrics over a write-first corpus exceed a sophisticated pipeline over a raw one | Hit@10 below 0.7 with the writing rules enforced |
| Weekly hygiene is enough to keep drift bounded | A 15-minute loop clears the queue faster than drift accumulates | Drift queue grows for three consecutive weeks |
| Postgres + pgvector is sufficient at our scale | Our corpus stays under the chunk count where ivfflat recall degrades | Search latency p95 over 200ms on production hardware |

## What this means for decisions

How the write-first commitment constrains downstream area-03 decisions and build sessions.

- Tech-stack decisions in area 03 (the engineering decisions about runtime, database, embedding model) must align with this substrate. The first such decision, recorded in `03-dec-tech-stack.md` (Postgres + pgvector, OpenAI text-embedding-3-small, FastAPI + FastMCP), sets the implementation; future area-03 decisions inherit its constraints.
- Every build session begins by searching the corpus, not by reading external sources.
- Tooling that bypasses the corpus (private notebooks, undocumented decisions, "let's discuss in chat") is out of scope. If it cannot be written, it does not ship.

## What this strategy does not cover

Product positioning, feature roadmap, hiring, and Postgres migration are explicitly out of scope.

- Product positioning, brand voice, or audience targeting (those belong in different area-01 strategy docs, not this one).
- Which features to build or which markets to enter (area 02 and beyond).
- Hiring, org structure, or compensation strategy (out of the knowledge-layer's scope entirely).
- Long-term migration off Postgres + pgvector. That decision will be recorded as its own engineering decision document with `status: complete` if and when the invalidation signal in the bets table fires.
