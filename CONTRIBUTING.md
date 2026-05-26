# Contributing to knowledge-layer

This is a template repository, not a product. Most people who find this repo will fork it, adapt it, and never open a PR back. That's the intended use. This file is for the smaller group who want to upstream an improvement.

Contributions are licensed under the repository's MIT license; opening a PR is your agreement to that.

## What "the template" includes

Upstream changes that fit the template:

- The MCP server (`src/`), the indexer and scripts (`scripts/`), the GitHub Actions workflows (`.github/workflows/`).
- The framework docs that govern the corpus: `docs/00-pol-document-standards.md`, `docs/00-fwk-writing-guide.md`, `docs/00-fwk-doc-hygiene-loop.md`, `docs/00-fwk-project-tracker.md`, `docs/00-fwk-open-gaps.md`.
- The scaffold templates under `docs/TEMPLATES/` (one per doc type, with frontmatter placeholders and section headers).
- The worked example docs (the ones with the `> **Example document.**` callout). Improvements to the examples, or a missing doc-type example, are welcome.
- The eval harness under `evals/`.
- `README.md`, `methodology.md`, `QUICKSTART.md`, `CLAUDE.md` (the skeleton), `examples/CLAUDE.example.md` (the worked example).

Out of scope for upstream:

- Anything specific to one user's stack, schema, secrets, or product.
- Real corpus documents from a forked project (those belong in your fork, not here).
- User-specific Supabase project IDs, Railway service IDs, OpenAI keys, or `.claude/settings.json` values.
- Replacing the doc-naming convention, the area numbering, or the six doc types: those are load-bearing across the audit script, the indexer, and the MCP tools. Propose changes via an issue first.

## Ways to contribute

**Issues.** Bugs in the scripts or workflows, broken cross-references in the docs, unclear instructions in the README or QUICKSTART, suggestions for a new worked example. Include the file path and the exact behaviour you saw.

**Pull requests.** Small, focused, one logical change per PR. Larger changes start as an issue so the scope can be agreed before the work.

**Forks.** If you forked and published your version, open an issue with a link to your fork so other readers can see what's been tried.

## Before you open a PR

Run the audit script locally:

```
python3 scripts/audit_docs_standards.py
```

The audit writes `docs-standards-audit.md` at the repo root. The workflow at `.github/workflows/audit-docs.yml` runs the same script on PRs that touch `docs/` and fails the run if the report contains any violations; with branch protection configured, that failure blocks merge.

If your change touches `src/`, smoke-test the server locally:

```
python3 -m uvicorn src.main:app --port 8000
curl -s http://localhost:8000/health
```

This needs `DATABASE_URL` and `OPENAI_API_KEY` in your environment; QUICKSTART documents how to obtain both via Supabase and OpenAI. Setting up Postgres entirely locally is possible but not covered by QUICKSTART.

If your change touches the scrub pipeline (`scripts/scrub*.py`):

```
python3 scripts/scrub_test.py
python3 scripts/verify_scrub.py
```

If your change touches the eval harness, run it end-to-end and include the output in the PR description:

```
python3 evals/run_evals.py
```

## Doc changes

Documents under `docs/` follow the rules defined in `docs/00-pol-document-standards.md` and elaborated in `docs/00-fwk-writing-guide.md`. The audit script enforces the structural rules (filename pattern, frontmatter completeness, section-size limit, dependency-target resolution); the prose rules (section summaries, inlined cross-references, one concept per section, concrete searchable terms) are self-checked against the writing guide before requesting review.

If your change modifies the doc standards themselves, the worked examples that depend on the standards must be updated in the same PR. The hygiene loop will otherwise flag them as drift.

## Code changes

- Scripts and the MCP server target Python 3.12+, matching the version pinned in the workflows and the README badge. Standard library plus the packages in `requirements.txt`. New runtime dependencies need a justification in the PR.
- The MCP server tools are the public interface to the corpus. Adding a tool is a substantive change: open an issue first with the proposed signature, the use case, and how it interacts with the existing MCP tools (currently seven, listed in QUICKSTART).
- Workflows under `.github/workflows/` should remain runnable in a forked repo with no setup beyond the secrets documented in QUICKSTART.

## Commit messages

The project uses short, factual messages. Recent examples from the log:

```
Add docs/02-spec-onboarding-flow.md, worked example of a UX spec
Add docs/05-pol-data-retention.md, worked example of the pol type
Add methodology.md: the conceptual essay behind the document standards
```

Lowercase verb, what changed, a short qualifier. No issue numbers in the subject line (link them in the PR body instead). No emoji.

## Security

If you find a vulnerability (a script that mishandles untrusted input, a workflow that leaks a token, an MCP tool that exposes data it shouldn't), email mihaela.gheorghe@gmail.com instead of opening a public issue. A fix ships first; the disclosure follows.

## What this file does not cover

- Code of conduct: act in good faith. Reviewers will close PRs that don't.
- CLAs and DCO sign-offs: not required.
- Release process: there are no releases; the template is the `main` branch.
- Funding, sponsorship, support contracts: none, not planned.
