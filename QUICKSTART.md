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

1. Create a free Supabase project at [supabase.com](https://supabase.com)
2. Enable the pgvector extension: go to SQL Editor and run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

3. Create the doc_chunks table:

```sql
-- v1 base table
CREATE TABLE doc_chunks (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    source_file text NOT NULL,
    section_header text,
    area_number text,
    doc_type text,
    content text NOT NULL,
    content_hash text NOT NULL UNIQUE,
    embedding vector(1536),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX ON doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON doc_chunks (source_file);
CREATE INDEX ON doc_chunks (content_hash);
```

Then apply the v2 migration (adds authority + provenance + graph + outline columns and the four supporting tables):

```bash
psql "$DATABASE_URL" -f scripts/migrations/001_kl_v2.sql
```

The migration is idempotent, safe to re-run. It also enables Row Level Security on every new table (no policies, so the anon/authenticated PostgREST keys can't touch them; the service-role `DATABASE_URL` bypasses RLS).

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

## Phase 1: Foundation Documents

Write these documents first, in this order. Use the templates in `docs/TEMPLATES/`.

### 1. Vision and Mission (`01-str-vision-mission.md`)
What does the world look like if your product succeeds? What is the product's job? Keep it to one page. This is the document everything else aligns to.

### 2. User Personas (`02-res-personas.md`)
Who are your users? What do they need? What frustrates them? Research-type document, state your confidence levels and what you're assuming vs. what you've validated.

### 3. Risk Appetite (`01-str-risk-appetite.md`)
What are your hard stops? What risks are you willing to take? Distinguish between structural limitations and non-negotiable constraints. This shapes every decision that follows.

### 4. Document Standards (`00-pol-document-standards.md`)
Already included in this template. Review it, customize the capability areas for your product.

### 5. Assumptions Register (`01-fwk-assumptions-register.md`)
Every assumption you're making, about users, market, technology, regulations. Each with a confidence level and a testable signal that would invalidate it.

After writing each document, push to main. The GitHub Action will sync them to the vector index. Verify with a search in Claude Code.

---

## Phase 2: Research

Now research the spaces your product operates in. Write research documents (`res` type) for:

- **Competitive landscape**, who else is building in this space, what they do well, where they fall short
- **Domain research**, the subject matter your product deals with (psychology, finance, education, etc.)
- **Regulatory analysis**, what laws and regulations apply (GDPR, COPPA, HIPAA, PCI-DSS, etc.)
- **Technology evaluation**, which frameworks, services, and tools to consider for each component
- **User behaviour**, how your target users currently solve the problem

Each research document should explicitly state:
- Confidence levels (high/medium/low) for each finding
- Known gaps, what you haven't been able to validate yet
- Sources and methodology

---

## Phase 3: Decisions

Research feeds decisions. Write decision documents (`dec` type) for:

- **Stack decisions**, language, framework, database, hosting, CI/CD
- **Architecture decisions**, monolith vs microservices, API style, auth approach
- **Compliance approach**, how you'll meet regulatory requirements
- **Data handling**, what you collect, where you store it, how long you keep it
- **AI strategy**, which models, what they do, how they're governed

Each decision document must include:
- What you chose
- What you rejected and why
- What conditions would trigger a change
- Who signed off

---

## Phase 4: Specifications

Decisions constrain specs. For each service or component, write:

1. **Definition** (`spec`), what the service is, inputs, outputs, modes, constraints
2. **Architecture** (`spec`), package layout, workflow steps, database schema
3. **API contract** (`spec`), every endpoint with method, path, request/response shape, auth, error codes
4. **Test plan** (`spec`), every test case with unique ID, category, inputs, expected outputs, pass/fail criteria
5. **Build guides** (`spec`), session-by-session Claude Code prompts with prerequisites, file paths, code blocks, pass criteria

Build guides are where Claude writes the code blocks during spec creation. You select, validate, and constrain them.

---

## Phase 5: Build

### Set up the constraint sheet

The repo's root `CLAUDE.md` is the file Claude Code reads at the start of every session in this codebase. Populate it with:
- Stack and package layout
- Import rules and architectural boundaries
- Field exclusion rules (data that must never be logged or returned)
- Query scoping requirements (tenant isolation)
- SQL rules (parameterized queries, ownership WHERE clauses)
- CI pipeline steps
- Commit message format
- Build session references

### Run build sessions

Each session is atomic: read scope from the build guide, run the Claude Code prompt, run CI gates, review the output, fix findings, audit the spec against the implementation, commit, update the tracker. Don't start session N+1 until session N passes all criteria. The exact review steps and personas are project-specific, define them in your own build-guide template.

---

## Ongoing: The Feedback Loop

After every build session:
1. **Update the constraint sheet** with any new invariants discovered
2. **Run the spec audit**, classify every difference between guide and implementation
3. **Update the tracker**, mark completed items, add new gaps
4. **Push to main**. GitHub Action syncs everything to the index

The system gets stronger with every session. Corrections become permanent. The constraint sheet grows. The index stays current. Every new session starts with full context.
