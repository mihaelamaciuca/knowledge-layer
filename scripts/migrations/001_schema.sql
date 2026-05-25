-- Knowledge Layer schema migration.
--
-- One self-contained, idempotent file: creates pgvector + every table
-- and index the indexer and the MCP server need. Safe to re-run.
--
-- Runbook:
--   1. Connect to your Supabase (or other Postgres + pgvector) instance.
--   2. Run this file via the SQL editor OR:
--        psql "$DATABASE_URL" -f scripts/migrations/001_schema.sql
--   3. Verify with the queries at the bottom.

-- ─── pgvector extension ───────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── doc_chunks (the indexed substrate) ───────────────────────────────────
CREATE TABLE IF NOT EXISTS doc_chunks (
    id               uuid        DEFAULT gen_random_uuid() PRIMARY KEY,
    source_file      text        NOT NULL,
    section_header   text,
    area_number      text,
    doc_type         text,
    content          text        NOT NULL,
    content_hash     text        NOT NULL UNIQUE,
    embedding        vector(1536),
    updated_at       timestamptz DEFAULT now(),
    -- authority + provenance + graph + outline fields (populated by the indexer):
    status           text,
    supersedes       text,
    doc_date         date,
    git_sha          text,
    git_committed_at timestamptz,
    depends_on       text[],
    feeds_into       text[],
    also_touches     int[],
    tsv              tsvector
);

-- For an existing doc_chunks table (e.g. an older fork without the extra
-- fields), ADD COLUMN IF NOT EXISTS keeps the file idempotent for upgrades.
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS status text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS supersedes text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS doc_date date;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS git_sha text;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS git_committed_at timestamptz;
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS depends_on text[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS feeds_into text[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS also_touches int[];
ALTER TABLE doc_chunks ADD COLUMN IF NOT EXISTS tsv tsvector;

CREATE INDEX IF NOT EXISTS doc_chunks_embedding_idx
  ON doc_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS doc_chunks_source_idx     ON doc_chunks(source_file);
CREATE INDEX IF NOT EXISTS doc_chunks_hash_idx       ON doc_chunks(content_hash);
CREATE INDEX IF NOT EXISTS doc_chunks_tsv_idx        ON doc_chunks USING GIN(tsv);
CREATE INDEX IF NOT EXISTS doc_chunks_status_idx     ON doc_chunks(status)      WHERE status      IS NOT NULL;
CREATE INDEX IF NOT EXISTS doc_chunks_area_idx       ON doc_chunks(area_number) WHERE area_number IS NOT NULL;

-- ─── doc_outlines (section tree per doc, for get_doc_outline) ─────────────
CREATE TABLE IF NOT EXISTS doc_outlines (
    source_file text        PRIMARY KEY,
    outline     jsonb       NOT NULL,
    updated_at  timestamptz DEFAULT now()
);

-- ─── doc_relationships (frontmatter graph, for get_doc_neighborhood) ──────
CREATE TABLE IF NOT EXISTS doc_relationships (
    source_file text NOT NULL,
    relation    text NOT NULL CHECK (relation IN
        ('depends_on', 'feeds_into', 'also_touches', 'supersedes')),
    target      text NOT NULL,
    PRIMARY KEY (source_file, relation, target)
);

CREATE INDEX IF NOT EXISTS doc_relationships_target_idx
  ON doc_relationships(target);

-- ─── decisions (registry, for get_decision and get_impact_targets) ────────
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

CREATE INDEX IF NOT EXISTS decisions_area_idx   ON decisions(area);
CREATE INDEX IF NOT EXISTS decisions_source_idx ON decisions(source_doc);

-- ─── query_log (telemetry; written by search_docs) ────────────────────────
CREATE TABLE IF NOT EXISTS query_log (
    id              bigserial   PRIMARY KEY,
    query_scrubbed  text,
    top_k_ids       uuid[],
    latency_ms      int,
    caller          text,
    created_at      timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS query_log_created_idx ON query_log(created_at DESC);

-- ─── Row Level Security ──────────────────────────────────────────────────
-- All five tables are not user-data-keyed. The MCP server and the indexer
-- both connect via DATABASE_URL (service-role connection) which bypasses
-- RLS. Enabling RLS with no policies blocks anon/authenticated PostgREST
-- clients from reading or writing these tables; this is the safer default
-- since the project has no legitimate anon-key caller for them.
ALTER TABLE doc_chunks         ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_outlines       ENABLE ROW LEVEL SECURITY;
ALTER TABLE doc_relationships  ENABLE ROW LEVEL SECURITY;
ALTER TABLE decisions          ENABLE ROW LEVEL SECURITY;
ALTER TABLE query_log          ENABLE ROW LEVEL SECURITY;

-- ─── Verification (run after migration) ───────────────────────────────────
-- All expected columns on doc_chunks:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_name='doc_chunks'
--    ORDER BY ordinal_position;
--
-- Expect 4 supporting tables:
--   SELECT table_name FROM information_schema.tables
--    WHERE table_schema='public'
--      AND table_name IN ('doc_outlines','doc_relationships','decisions','query_log');
