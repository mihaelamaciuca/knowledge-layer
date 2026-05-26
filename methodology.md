# Methodology

## Why retrieval quality is a writing problem

Most RAG systems treat documents as static input. You have files, you chunk them, you embed them, you search. When retrieval quality is bad, the typical response is to improve the pipeline: add a reranker, try hybrid search, use a bigger embedding model, build an agentic retrieval layer.

This knowledge layer starts from a different premise. If the documents are written well, basic cosine similarity over a standard embedding model works. If they are written poorly, retrievers cannot recover meaning that is not in the text. Pipeline tuning helps but cannot substitute for source quality.

This is not a theoretical claim. It is backed by research:

- **RAGChecker (NeurIPS 2024)** found that retriever quality is the dominant lever in RAG system performance, with generator improvements producing smaller effects across multiple systems on their benchmark.
- **"Seven Failure Points When Engineering a RAG System" (arXiv, 2024)** lists seven failure modes. Three of them are document-level: Missing Content (FP1), Not in Context (FP3), and Incorrect Specificity (FP6). Each is a problem in the document, not the pipeline.
- **AWS prescriptive guidance on writing for RAG** recommends descriptive headings as embedding anchors, brief summaries after headings, one concept per section, and concrete searchable terms. The same four moves anchor `docs/00-pol-document-standards.md` in this repo.

Taken together: writing quality is a necessary condition for good retrieval. Pipeline improvements (better embedding models, rerankers, hybrid search) help, but cannot substitute for source content the embeddings can grip. See the README's Citations section for the full references.

## The five writing rules

These are the rules `docs/00-pol-document-standards.md` declares. Structural compliance with them is enforced mechanically by `scripts/audit_docs_standards.py` on every PR (filename pattern, frontmatter fields, section length, heading depth, cross-reference resolution). The four prose rules below (summaries, inline cross-references, concrete terms, one concept per section) are not mechanically auditable; they are enforced by Claude Code reading the root `CLAUDE.md` at the start of every authoring session.

### 1. Section summaries after every heading

After every `##` heading, add a one-line plain-language summary of what the section covers. Include the key terms someone would search for.

```markdown
## Error states, payment failure, billing retry, grace period

Covers what happens when billing fails: grace period (16 days, full
access), billing retry (blocked), recovery, and final expiry after
60 days.
```

The summary gets embedded with the section content and gives the embedding model a strong signal to match against. Without it, a generic heading like "Error states" produces a weak embedding that could match hundreds of unrelated queries. With it, a search for "what happens when payment fails" hits this section directly.

### 2. Inline cross-references

Never use bare cross-references. Always inline what the referenced section says.

```markdown
<!-- weak: the embedding model doesn't know what section 9 says -->
The library renders per the UX spec section 9 for the expired state.

<!-- strong: the meaning is in the chunk -->
The library renders for the expired state with the floating action
button hidden and a resubscribe prompt at the bottom of the grid,
as defined in the UX spec section 9.
```

Each chunk is embedded independently. A bare reference like "see section 9" creates a chunk that points somewhere but contains no searchable meaning. When you inline the referenced content, the chunk is self-contained: it can be found and understood without following the reference.

### 3. One concept per section

A section about "Subscription lifecycle" that also covers push notifications, grace periods, and deletion cascades produces a blurry embedding. It partially matches many queries but strongly matches none. Split into focused sections. Each section should be about one thing.

Embedding models produce a single vector per chunk. That vector is an average of the meanings in the text. The more concepts you pack into one section, the more diluted the vector becomes. Focused sections produce sharp embeddings that match the right queries.

### 4. Concrete searchable terms

Use the terms someone would actually search for, not abstract jargon.

```markdown
<!-- weak: abstract -->
Configurable access retention window during payment recovery.

<!-- strong: searchable -->
16-day grace period where the user keeps full access while the
payment provider retries the failed payment.
```

Embedding models match on meaning. Both phrases describe the same idea, but a person searching for the concept will use the concrete version. Write the way people search.

### 5. Keep sections under 4000 characters

`scripts/rag_core/chunker.py` splits on `##` headings. Sections over 4000 characters get split mechanically and lose coherence: two incomplete chunks, neither one a complete thought, neither one embedding well. If a section is long, break it into subsections with `###` headings before the chunker does it for you. The chunker's fallback prefers paragraph and word boundaries, but that should not be a substitute for writing the right size in the first place.

4000 characters is roughly 1000 tokens for English prose (the rule-of-thumb conversion most embedding documentation uses). Longer chunks dilute the embedding; shorter chunks lose context.

## The automation loop

The rules above are effective because they are enforced automatically. Nobody has to remember them or check for compliance manually.

### CLAUDE.md as the contract

The repo's root `CLAUDE.md` is the constraint sheet Claude Code reads at the start of every session. It points at the document standards and at any project-specific invariants (field exclusions, SQL rules, branching). When the AI writes or edits any document, it follows the rules: adding section summaries, inlining cross-references, splitting oversized sections, using concrete terms.

### Per-PR audit

`.github/workflows/audit-docs.yml` runs `scripts/audit_docs_standards.py` on every pull request that touches `docs/`. The audit script validates frontmatter, resolves every cross-reference, checks section sizes, audits heading depth, and runs the governance scrub fixture test. A PR that breaks the standards cannot merge once branch protection is configured.

### CI sync on every push

`.github/workflows/sync-to-rag.yml` triggers on every push to main when files in `docs/` change. It diffs the changed files against the previous commit, deletes stale chunks for each changed file, chunks the new content by `##` headings, embeds each chunk via OpenAI in batches, and upserts the result with provenance (`git_sha`, `git_committed_at`) into `doc_chunks`. New documents are queryable on the next successful workflow run.

### The drift loop

The five writing rules keep documents searchable. The drift loop keeps them honest. Once a week, an owner runs `get_drift_report(top=10)` and triages the top items. The detector surfaces four signals: `stale-string` (retired terms that still appear), `dangling-ref` (frontmatter targets that no longer resolve), `dep-out-of-date` (a `depends-on` target committed later than the depending document), and `decision-contradict` (chunks whose prose disagrees with a current decision). See `docs/00-fwk-doc-hygiene-loop.md` for the full process.

## Why this works

Each rule targets a specific vector-retrieval failure mode:

- Section summaries fix the weak-heading failure (a heading too generic to anchor an embedding).
- Inline cross-references fix the orphan-chunk failure (a chunk references content it does not contain).
- One concept per section fixes the diluted-vector failure (multiple meanings averaged into one).
- Concrete terms fix the abstract-jargon failure (the chunk uses words nobody searches for).
- The size limit fixes the mechanical-split failure (the chunk gets truncated mid-thought).

The rules are the writing pass. The audit script and the drift loop are the maintenance passes. Together they keep the index searchable as the corpus grows.
