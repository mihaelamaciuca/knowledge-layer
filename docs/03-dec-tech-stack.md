---
file: 03-dec-tech-stack
area: 3
area-name: Engineering
type: dec
title: Knowledge-layer tech stack
status: complete
date: 2026-05-25
depends-on:
  - 03-res-vector-stores
feeds-into:
  - 03-spec-search-api

decisions:
  - key: vector-store
    decision: Vector store for embeddings
    current_value: "Postgres with the pgvector extension"
    decided_on: 2026-05-25
    cross_refs:
      - 03-res-vector-stores
  - key: embedding-model
    decision: Embedding model
    current_value: "OpenAI text-embedding-3-small at 1536 dimensions"
    decided_on: 2026-05-25
  - key: api-framework
    decision: HTTP framework for the MCP server
    current_value: "FastAPI with FastMCP for the Streamable HTTP transport"
    decided_on: 2026-05-25
---

# Knowledge-layer tech stack

> **Example document.** Demonstrates a `dec` (decision) doc with a multi-entry `decisions:` block that `scripts/build_decision_registry.py` parses into the `decisions` table. Replace or delete when you make your own choices.

## Context

The knowledge layer needs three things settled before any code goes in: where embeddings live, which model produces them, and what serves the MCP tools. Each choice constrains the others.

## Options considered

### Option A. Postgres + pgvector + OpenAI + FastAPI

- One database for embeddings and metadata, joined in SQL.
- OpenAI's `text-embedding-3-small` is the current price/quality sweet spot (1536 dims, $0.02 / 1M tokens at time of decision).
- FastAPI + FastMCP is the documented path for the MCP Streamable HTTP transport.

### Option B. Managed vector DB + open-source embedding + Flask

- Pinecone or Weaviate for the index, sentence-transformers locally for the embedding, Flask for the API.
- Lowest API cost; full control of the embedding model.
- Two operational stores; embedding latency depends on local GPU availability.

### Option C. Self-hosted Qdrant + open-source embedding + FastAPI

- Qdrant for the index, sentence-transformers for the embedding.
- Zero per-call vendor cost; full control end to end.
- Substantial extra operational surface area.

## Decision

**Chosen: Option A.**

`03-res-vector-stores` lays out the trade-off between an integrated store and a managed vector DB. For a team that already operates Postgres, pgvector keeps the substrate to one system. OpenAI's hosted embedding API removes a tuning burden in the early stages; switching to a self-hosted model is straightforward later (the indexer reads `EMBEDDING_MODEL` from a single constant). FastAPI is non-negotiable given FastMCP requires it.

## Rejected alternatives

- **Option B**: the second store doubles ops and forces every search response to do a metadata join over a different network. Worth revisiting once embedding volume makes the API cost noticeable.
- **Option C**: every reason to pick Qdrant over pgvector also applies to going back to pgvector once HNSW recall is enough. Defer until the corpus is well past 100k chunks.

## Change triggers

| Trigger | Signal | Action |
|---------|--------|--------|
| Embedding cost > $X / mo | OpenAI invoice | Evaluate self-hosted embedding |
| pgvector recall below acceptable floor | RAGChecker Hit@k drops | Switch to HNSW index or move to managed store |
| Multi-tenant requirement appears | Product decision | Re-evaluate Option B for per-tenant namespace support |

## Sign-off

Decision is illustrative. In a real project, record who approved and when.
