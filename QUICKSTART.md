# Quick Start Guide

This guide walks you through setting up the knowledge layer for your own product. Follow in order, each phase builds on the previous one.

---

## Phase 0: Infrastructure

### 1. Clone and parameterize

```bash
git clone <this-repo> my-project-tools
cd my-project-tools
chmod +x scripts/init.sh
./scripts/init.sh
```

The init script asks for your project name and replaces all `{{PROJECT_NAME}}` placeholders across the codebase.

### 2. Create the Supabase database

1. Create a free Supabase project at [supabase.com](https://supabase.com).
2. Copy your connection string from Settings > Database > Connection string (URI format) into `DATABASE_URL`. If you are on IPv4, use the **Session Pooler** connection string instead of the direct connection.
3. Apply the schema migration. It enables the `pgvector` extension, creates `doc_chunks` and the four supporting tables (`doc_outlines`, `doc_relationships`, `decisions`, `query_log`), adds the indexes, and enables Row Level Security on every table. One file, idempotent, safe to re-run:

```bash
psql "$DATABASE_URL" -f scripts/migrations/001_schema.sql
```

RLS is enabled with no policies, so anon/authenticated PostgREST keys can't read or write these tables; the service-role `DATABASE_URL` used by the indexer and the MCP server bypasses RLS.

### 3. Get an OpenAI API key

You need `text-embedding-3-small` access. Get a key at [platform.openai.com](https://platform.openai.com).

### 4. Deploy the MCP server

1. Create a [Railway](https://railway.app) project
2. Connect your GitHub repo
3. Set environment variables in Railway:
   - `DATABASE_URL`, your Supabase connection string (direct, or Session Pooler if you're on IPv4)
   - `OPENAI_API_KEY`, your OpenAI key
   - `MCP_TOKEN_1`, generate a random token (e.g. `openssl rand -base64 32`). Add `MCP_TOKEN_2`, `MCP_TOKEN_3`, ... if you want per-user tokens (`src/auth.py` reads `MCP_TOKEN_1` through `MCP_TOKEN_9`).
   - `BASE_URL`, the public URL of your Railway deployment (e.g. `https://<your-app>.up.railway.app`). Required only if you connect from claude.ai (it probes `/.well-known/oauth-*` discovery endpoints). Claude Code uses bearer auth directly and does not need this.
4. Deploy. Railway auto-detects the Procfile

### 5. Configure Claude Code

Update `.claude/settings.json` with your Railway URL and bearer token:

```json
{
  "mcpServers": {
    "{{PROJECT_NAME}}-docs": {
      "type": "http",
      "url": "https://your-railway-url.up.railway.app/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_MCP_TOKEN_1"
      }
    }
  }
}
```

### 6. Set up GitHub Actions secrets

In your GitHub repo settings, add these secrets (consumed by `.github/workflows/sync-to-rag.yml` and `.github/workflows/reindex.yml`):
- `DATABASE_URL`, same value as the Railway env var
- `OPENAI_API_KEY`, same value as the Railway env var

### 7. Test the pipeline

```bash
# Set up local env
cp .env.example .env
# Fill in .env with your credentials

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the initial population (batched embeddings)
python scripts/populate.py --docs-dir docs --full-reindex

# Verify the scrub policy (CI also runs this on every PR)
python scripts/scrub_test.py

# Verify the MCP server works locally
uvicorn src.main:app --host 0.0.0.0 --port 9090
# In another terminal: curl http://localhost:9090/health
# (the /health endpoint is intentionally unauthenticated)
```

You should see `{"status": "ok"}`. The RAG infrastructure is live, and Claude Code now sees **seven MCP tools** (note: until you've populated `docs/` and run the indexer, the tools will register but return empty results, start with Phase 1 below to write your first document):

- `search_docs`, hybrid vector+lexical, filterable, authority-aware
- `get_decision`, settled-decision lookup (requires a decisions table; see "Decision registry" below)
- `get_impact_targets`, impact-target packet
- `get_doc_neighborhood`, frontmatter graph
- `get_doc_outline`, section tree for long docs
- `get_drift_report`, hygiene-loop queue
- `check_index_health`, operational status

### Decision registry (optional but recommended)

The `decisions` table is populated by `scripts/build_decision_registry.py`, which scans `docs/*-dec-*.md` files for a `decisions:` block in YAML frontmatter and upserts each entry into the `decisions` table. See the script's docstring for the expected frontmatter shape. Run it once you have decision documents:

```bash
DATABASE_URL=$DATABASE_URL python3 scripts/build_decision_registry.py
```

Without any decisions, `get_decision` and `get_impact_targets` return empty gracefully, the other five tools work fully.

### Governance scrub

Add your project's excluded fields (PII, secrets, anything that must not appear in `doc_chunks.content`) to `scripts/rag_core/scrub.py` `EXCLUDED_FIELDS`. The fixture test `scripts/scrub_test.py` runs in CI on every PR touching `docs/`. Default is empty list, the scrub is a no-op until you customise it.

### Weekly hygiene loop

Once you have docs flowing through the system: `get_drift_report(top=10)` returns a prioritised queue of flagged claims. 15 min/week to triage. See `docs/00-fwk-doc-hygiene-loop.md` for the full process.

---

## Phase 1: Write your first documents

### What's required vs what's yours

Only one document is load-bearing for the system: **`docs/00-pol-document-standards.md`**. The audit script (`scripts/audit_docs_standards.py`) enforces its rules on every PR. Open it and customize:

- **Capability areas.** The shipped table lists generic areas (Strategy, Product, Engineering, Data, etc.). Replace with the areas that actually divide *your* project.
- **Document types.** The six types (`spec`, `res`, `str`, `dec`, `pol`, `fwk`) are the controlled vocabulary `audit_docs_standards.py` validates against. Don't add or remove without also updating `VALID_TYPES` in the audit script.
- **Frontmatter fields.** The audit script's `REQUIRED_FIELDS` matches this doc's "Required: Yes" rows. Keep them in sync.

Two other shipped docs are useful but optional:

- `docs/00-fwk-doc-hygiene-loop.md` defines the weekly 15-minute maintenance cadence. The drift detector works without it; the process doc is what tells humans how to use the drift detector.
- `docs/00-fwk-project-tracker.md` and `docs/00-fwk-open-gaps.md` are empty skeletons for tracking deliverables and unresolved questions. Keep, customize, or delete.

Everything else under `docs/` is yours to write.

### Scaffolds

`docs/TEMPLATES/` ships six scaffolds, one per doc type. Copy a template, rename to `[area]-[type]-[name].md`, fill it in. The TEMPLATES files are not part of the indexed corpus; they exist to be copied.

### Examples of a starter document

The right first document depends on what your project is. Here are three shapes:

- **A SaaS or product team:** start with a *decision* (e.g. `02-dec-tech-stack.md`) recording the stack you're committing to. The decision has natural `cross_refs` to other docs you'll write later, so the dependency graph grows from a real anchor.
- **An open-source library or service:** start with a *spec* (e.g. `03-spec-public-api.md`) documenting your public API contract. Future spec changes cascade through `get_impact_targets` once you have downstream specs.
- **A research project or knowledge base:** start with a *research* doc (e.g. `02-res-prior-art.md`) summarising the literature. Decisions and specs you write later can cite it via `depends-on`.

In every case: write the doc with valid frontmatter, push to main, watch `sync-to-rag.yml` index it, then call `search_docs("<your doc's title>")` from Claude Code. If the doc comes back with provenance, the layer is working. Now write the second.

### The doc-hygiene loop

Once the corpus has anything in it: `get_drift_report(top=10)` returns a prioritised queue of flagged claims. 15 minutes a week to triage. See `docs/00-fwk-doc-hygiene-loop.md` for the full process.

### Evals (optional but recommended)

Once you have a handful of docs, populate `evals/goldens.yaml` with the questions you most often ask the layer and the docs you expect back. `python3 evals/run_evals.py` measures Hit@k, Recall@k, MRR, and top-status precision (see `evals/README.md`). The harness is a no-op until you add goldens; once you do, run it locally before any change to the chunker, the embedder, or the scrub.

### The constraint sheet (`CLAUDE.md`)

The repo's root `CLAUDE.md` is what Claude Code reads at the start of every session in this codebase. It ships as a skeleton of commented-out prompts. Fill in only the sections relevant to your project: stack and package layout, import rules, field-exclusion rules (the same fields you add to `rag_core/scrub.py`), and whatever invariants you want Claude to honour without being reminded.
