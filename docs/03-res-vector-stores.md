---
file: 03-res-vector-stores
area: 3
area-name: Engineering
type: res
title: Vector store options for the knowledge layer
status: complete
date: 2026-05-25
depends-on: []
feeds-into:
  - 03-dec-tech-stack
---

# Vector store options for the knowledge layer

> **Example document.** Bundled with the template to show what a `res` (research) doc looks like with valid frontmatter, section summaries, and downstream `feeds-into` links. Replace or delete when you start writing your own corpus.

## Question

What should host the embeddings the knowledge layer indexes: an existing Postgres with `pgvector`, a managed vector database like Pinecone or Weaviate, or a self-hosted Qdrant / Milvus instance?

## Methodology

Surveyed three options on five axes: operational footprint, query shape support, ecosystem maturity, cost model, and lock-in. Sources: vendor docs (Pinecone, Supabase, Qdrant) and the pgvector GitHub repo. No load testing performed; this doc is decision-input, not benchmarking.

## Finding 1: pgvector on managed Postgres

**Confidence: High.** Embeddings live in the same relational store as the metadata that describes them (status, provenance, frontmatter graph). A single SQL query can filter by `status = 'complete'`, rank by cosine similarity, and join to the `decisions` table. No second system to operate; Supabase ships pgvector enabled by default.

Trade-off: ivfflat recall is sensitive to the `lists` parameter and degrades on very small corpora until the index is rebuilt after population. HNSW is available from pgvector 0.5 onward but uses more memory.

## Finding 2: Managed vector DB (Pinecone, Weaviate Cloud)

**Confidence: High.** Best-in-class recall, hybrid search out of the box, generous free tiers. Operationally a single API call to upsert; nothing to provision.

Trade-off: metadata lives in two stores (your Postgres + their index). Every search response that needs authority or provenance needs a follow-up SQL roundtrip. Cost ramps with QPS and storage; small projects can sit comfortably under free-tier limits.

## Finding 3: Self-hosted (Qdrant, Milvus)

**Confidence: Medium.** Strong feature set (filtered search, payload indexing, hybrid). Free, open-source.

Trade-off: another service to deploy, monitor, back up, and upgrade. For a team that already runs Postgres, the marginal cost of pgvector is near zero; the marginal cost of standing up Qdrant is non-trivial.

## Known gaps

| Gap | Impact | How to close |
|-----|--------|--------------|
| No load test of pgvector at 100k+ chunks | Medium | Run a benchmark before scaling past 50k |
| HNSW vs ivfflat trade-off not measured | Low | Defer until ivfflat recall is the bottleneck |

## Implications

This research feeds `03-dec-tech-stack`, which records the chosen store. The decision document is the contract; this file is the trail behind it.
