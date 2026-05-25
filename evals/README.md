# Eval Harness

A retrieval-side eval harness for the knowledge layer. Goldens describe what the system should return for a given query; the runner calls `search_docs` and scores against four diagnostic metrics inspired by RAGChecker (Ru et al., NeurIPS 2024, <https://arxiv.org/abs/2408.08067>).

Generation-side metrics (faithfulness, hallucination) are out of scope: this knowledge layer is the retrieval substrate, not a generator. Hallucination control lives downstream, in whatever agent consumes the layer.

## Metrics

- **Hit@k**, 1 if every expected `source_file` appears in `search_docs(query, k)`'s top-k results, 0 otherwise. Hard pass/fail per golden.
- **Recall@k**, fraction of expected `source_file`s present in top-k. Captures partial credit when a golden expects multiple files.
- **MRR**, mean reciprocal rank of the *first* expected hit. Captures how high the right answer comes back, not just whether it appears.
- **Top-status precision**, when a golden declares `expect.top_status`, the top hit's `status` must be in that set. Useful for asserting authority, e.g. "the top hit for this query must be `complete`, never `superseded` or `draft`."

## Defining goldens

Edit `evals/goldens.yaml`. Each entry is a query + the documents that should resurface.

```yaml
goldens:
  - id: trial-length-current-value
    query: "What is the current free trial length?"
    k: 5
    expect:
      source_files:
        - 02-dec-trial-length      # bare slug (without .md)
      top_status: [complete]       # optional
    filters:                       # optional, passed to search_docs
      status: complete
```

Notes:
- `source_files` entries match against `source_file` as slug prefixes (so `02-dec-trial-length` matches both `02-dec-trial-length` and a versioned rename like `02-dec-trial-length-v2`). Use the most stable form you can.
- `k` defaults to 10.
- `filters` accepts `status`, `area`, `doc_type`, `include_superseded`, the same parameters `search_docs` exposes to the MCP layer.

## Running

```bash
DATABASE_URL=postgres://... OPENAI_API_KEY=sk-... python3 evals/run_evals.py
```

Text report by default. Add `--json` for machine-readable output.

If `goldens.yaml` has no entries, the runner exits 0 with a message, the harness becomes a no-op until you populate it.

## Exit codes

- `0`, all goldens passed (Hit@k = 1.0 everywhere).
- `1`, at least one golden failed.
- `2`, environment or configuration error (missing env vars, malformed goldens).

## Wiring into CI

Add this to a workflow once you have stable goldens and want regressions to block merges:

```yaml
- name: Retrieval evals
  env:
    DATABASE_URL: ${{ secrets.DATABASE_URL }}
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
  run: python3 evals/run_evals.py
```

Until then, run it locally before merging significant changes to the indexer, the chunker, the scrub, or the embedding model, anywhere a regression in retrieval quality could ship without notice.

## What good looks like

For a stable corpus + indexer combination, expect Hit@k near 1.0 with k in the 3, 10 range and an MRR above 0.5. If those numbers move, something changed, embedding model, chunking, scrub, query-log re-weighting, and the eval is the first place that change shows up.
