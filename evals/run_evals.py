#!/usr/bin/env python3
"""Retrieval eval harness for the knowledge layer.

Loads `evals/goldens.yaml`, runs each query through `search_docs`, and
reports four retrieval-side diagnostic metrics inspired by RAGChecker
(Ru et al., NeurIPS 2024, https://arxiv.org/abs/2408.08067):

    Hit@k, 1 if every expected source_file appears in top-k.
    Recall@k, fraction of expected source_files present in top-k.
    MRR, mean reciprocal rank of the first expected hit.
    Top-status precision, fraction of goldens whose top hit's status is
                           in the expected set (default: skipped if not
                           declared on the golden).

Generation-side metrics (faithfulness, hallucination) are out of scope
here, the knowledge layer is the retrieval substrate, not a generator.

Usage:
    DATABASE_URL=... OPENAI_API_KEY=... python3 evals/run_evals.py
    DATABASE_URL=... OPENAI_API_KEY=... python3 evals/run_evals.py --json

Exit codes:
    0, all goldens passed (Hit@k == 1.0 for every entry).
    1, at least one golden failed.
    2, environment or configuration error (missing env vars, malformed
        goldens, etc.).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("pyyaml not installed. pip install pyyaml", file=sys.stderr)
    sys.exit(2)

# search_docs is imported lazily inside main() so the no-op path doesn't
# require psycopg2 to be installed.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

GOLDENS_PATH = Path(__file__).resolve().parent / "goldens.yaml"


def _matches(expected_slug: str, source_file: str) -> bool:
    """Match an expected slug against a full source_file value.

    `source_file` in the DB is typically the bare slug (no `.md`); we
    also accept full paths and `.md`-suffixed values for flexibility.

    Matching is exact or "expected_slug followed by a hyphen" so a
    versioned rename (`02-dec-trial-length` -> `02-dec-trial-length-v2`)
    still matches, but substrings (`-old`, `prior-`) don't produce
    false positives.
    """
    s = source_file
    if s.endswith(".md"):
        s = s[:-3]
    s = s.rsplit("/", 1)[-1]
    return s == expected_slug or s.startswith(expected_slug + "-")


def score_one(golden: dict, results: list[dict]) -> dict:
    expected: list[str] = list(golden.get("expect", {}).get("source_files", []))
    hits_ranks: dict[str, int | None] = {}
    for slug in expected:
        rank = next(
            (i + 1 for i, r in enumerate(results) if _matches(slug, r.get("source_file", ""))),
            None,
        )
        hits_ranks[slug] = rank

    n_found = sum(1 for r in hits_ranks.values() if r is not None)
    n_expected = len(expected)
    hit_at_k = 1.0 if n_expected > 0 and n_found == n_expected else 0.0
    recall_at_k = (n_found / n_expected) if n_expected else 1.0
    first_rank = min((r for r in hits_ranks.values() if r is not None), default=None)
    rr = (1.0 / first_rank) if first_rank else 0.0

    # Top-status precision, only scored if the golden declared it.
    expected_top_status = golden.get("expect", {}).get("top_status")
    top_status_ok: bool | None = None
    if expected_top_status and results:
        top_status_ok = results[0].get("status") in set(expected_top_status)

    return {
        "id": golden.get("id", "<unnamed>"),
        "query": golden.get("query", ""),
        "k": golden.get("k", 10),
        "expected_source_files": expected,
        "hits_ranks": hits_ranks,
        "hit_at_k": hit_at_k,
        "recall_at_k": recall_at_k,
        "reciprocal_rank": rr,
        "top_status_ok": top_status_ok,
        "top_status_expected": expected_top_status,
        "top_status_actual": (results[0].get("status") if results else None),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text report.")
    args = parser.parse_args()

    if not GOLDENS_PATH.exists():
        print(f"Error: {GOLDENS_PATH} not found", file=sys.stderr)
        return 2

    with open(GOLDENS_PATH) as fh:
        data = yaml.safe_load(fh) or {}

    goldens: list[dict] = data.get("goldens") or []
    if not goldens:
        print("No goldens defined in evals/goldens.yaml, eval harness is a no-op.")
        print("Add entries under `goldens:` to start measuring retrieval quality.")
        return 0

    if not os.environ.get("DATABASE_URL"):
        print("Error: DATABASE_URL is not set", file=sys.stderr)
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY is not set (needed to embed the query)", file=sys.stderr)
        return 2

    from src.search import search_docs  # imported lazily, needs psycopg2

    per_golden: list[dict] = []
    for g in goldens:
        if "query" not in g:
            print(f"Error: golden {g.get('id', '<unnamed>')!r} has no `query`", file=sys.stderr)
            return 2
        try:
            k = int(g.get("k", 10))
        except (TypeError, ValueError):
            print(f"Error: golden {g.get('id', '<unnamed>')!r} has non-integer `k`", file=sys.stderr)
            return 2
        if k < 1 or k > 20:
            print(
                f"Error: golden {g.get('id', '<unnamed>')!r} has k={k}; "
                f"valid range is 1..20 (search_docs clamps server-side).",
                file=sys.stderr,
            )
            return 2
        filters = g.get("filters") or {}
        results = search_docs(
            g["query"], k,
            status=filters.get("status"),
            area=filters.get("area"),
            doc_type=filters.get("doc_type"),
            include_superseded=bool(filters.get("include_superseded", False)),
            caller="eval",
        )
        per_golden.append(score_one(g, results))

    aggregate: dict[str, Any] = {
        "n": len(per_golden),
        "hit_at_k": sum(p["hit_at_k"] for p in per_golden) / len(per_golden),
        "recall_at_k": sum(p["recall_at_k"] for p in per_golden) / len(per_golden),
        "mrr": sum(p["reciprocal_rank"] for p in per_golden) / len(per_golden),
    }
    scored_top = [p for p in per_golden if p["top_status_ok"] is not None]
    if scored_top:
        aggregate["top_status_precision"] = (
            sum(1 for p in scored_top if p["top_status_ok"]) / len(scored_top)
        )

    if args.json:
        print(json.dumps({"aggregate": aggregate, "per_golden": per_golden}, indent=2))
    else:
        print("=" * 64)
        print(f"  Goldens scored:        {aggregate['n']}")
        print(f"  Hit@k (all expected):  {aggregate['hit_at_k']:.2%}")
        print(f"  Recall@k:              {aggregate['recall_at_k']:.2%}")
        print(f"  MRR:                   {aggregate['mrr']:.3f}")
        if "top_status_precision" in aggregate:
            print(f"  Top-status precision:  {aggregate['top_status_precision']:.2%}")
        print("=" * 64)
        print()
        for p in per_golden:
            ok = "PASS" if p["hit_at_k"] == 1.0 else "FAIL"
            print(f"  [{ok}] {p['id']}  (k={p['k']})")
            print(f"         query: {p['query']!r}")
            for slug, rank in p["hits_ranks"].items():
                marker = f"rank {rank}" if rank else "NOT FOUND"
                print(f"         expected {slug}: {marker}")
            if p["top_status_ok"] is False:
                print(
                    f"         top status {p['top_status_actual']!r} not in "
                    f"{p['top_status_expected']}"
                )
            print()

    failed = [p for p in per_golden if p["hit_at_k"] != 1.0]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
