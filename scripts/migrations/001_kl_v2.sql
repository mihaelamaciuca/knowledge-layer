-- Knowledge Layer v2. Schema migration
--
-- Idempotent: safe to run multiple times. All new columns are nullable, all
-- new tables are created only if absent. Existing v1 behaviour is preserved.
--
-- Runbook:
--   1. Connect to your Supabase project.
--   2. Run this file via the Supabase SQL editor OR:
--        psql "$DATABASE_URL" -f scripts/migrations/001_kl_v2.sql
--   3. Verify with the queries at the bottom of this file.
--
-- After this migration:
--   - doc_chunks gains 9 new nullable columns; the indexer populates them later.
--   - 4 new tables exist; the v2 indexer pipeline populate them.
--   - Existing search_docs and check_index_health continue to work unchanged.
--
-- Field-exclusion enforcement (governance scrub) is added separately.

-- ─── doc_chunks v2 columns ────────────────────────────────────────────────
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS supersedes text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS doc_date date;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS git_sha text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS git_committed_at timestamptz;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS depends_on text[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS feeds_into text[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS also_touches int[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS tsv tsvector;

CREATE INDEX IF NOT EXISTS doc_chunks_tsv_idx
  ON doc_chunks USING GIN(tsv);

CREATE INDEX IF NOT EXISTS doc_chunks_status_idx
  ON doc_chunks(status) WHERE status IS NOT NULL;

CREATE INDEX IF NOT EXISTS doc_chunks_area_idx
  ON doc_chunks(area_number) WHERE area_number IS NOT NULL;

-- ─── doc_outlines ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doc_outlines (
    source_file text PRIMARY KEY,
    outline     jsonb       NOT NULL,
    updated_at  timestamptz DEFAULT now()
);

-- ─── doc_relationships ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS doc_relationships (
    source_file text NOT NULL,
    relation    text NOT NULL CHECK (relation IN
        ('depends_on', 'feeds_into', 'also_touches', 'supersedes')),
    target      text NOT NULL,
    PRIMARY KEY (source_file, relation, target)
);

CREATE INDEX IF NOT EXISTS doc_relationships_target_idx
  ON doc_relationships(target);

-- ─── decisions ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decisions (
    id            serial      PRIMARY KEY,
    decision_key  text        UNIQUE NOT NULL,
    area          int         NOT NULL,
    decision      text        NOT NULL,
    current_value text        NOT NULL,
    source_doc    text        NOT NULL,
    decided_on    date,
    cross_refs    text[],
    superseded_by int         REFERENCES decisions(id),
    updated_at    timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS decisions_area_idx ON decisions(area);
CREATE INDEX IF NOT EXISTS decisions_source_idx ON decisions(source_doc);

-- ─── query_log ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_log (
    id              bigserial   PRIMARY KEY,
    query_scrubbed  text,
    top_k_ids       uuid[],
    latency_ms      int,
    caller          text,
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_log_created_idx ON query_log(created_at DESC);

-- ─── RLS enablement (idempotent, re-running is a no-op) ──────────────────
-- The knowledge-layer tables are not user-data-keyed. The MCP server and
-- the indexer both connect via DATABASE_URL (service-role connection) which
-- bypasses RLS. Enabling RLS with no policies prevents anon/authenticated
-- PostgREST API clients from reading or writing these tables, the safer
-- default given the project has no legitimate anon-key caller for them.
--
-- This applies to doc_chunks (v1 table that pre-existed this migration)
-- and the four v2 tables.
ALTER TABLE doc_chunks         ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_outlines       ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_relationships  ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_log          ENABLE ROW LEVEL SECURITY;

-- ─── Verification queries (run after migration) ───────────────────────────
-- Expect each of the v2 columns to be present:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name='doc_chunks' AND column_name IN
--     ('status','supersedes','doc_date','git_sha','git_committed_at',
--      'depends_on','feeds_into','also_touches','tsv');
--
-- Expect 4 rows:
--   SELECT table_name FROM information_schema.tables
--    WHERE table_schema='public'
--      AND table_name IN ('doc_outlines','doc_relationships','decisions','query_log');
--
-- v1 behaviour check, existing search should still return rows:
--   SELECT count(*) FROM doc_chunks;
