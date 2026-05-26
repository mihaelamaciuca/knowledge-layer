# myapp. Claude Code Constraints

**Worked example.** Filled-in version of the empty `CLAUDE.md` skeleton at the root of this repo. The hypothetical project is a multi-tenant SaaS named `myapp` whose auth middleware is specified in `examples/sample-docs/after-authentication.md`. Use this file as a reference for what each section looks like populated; copy it into a fork and replace the project-specific content with your own.

**Filename note.** This file is `CLAUDE.example.md`, not `CLAUDE.md`, on purpose. Claude Code reads `CLAUDE.md` from whatever directory the session is rooted at; a literal `examples/CLAUDE.md` could silently activate as the constraint sheet for anyone opening an editor session at `examples/`. The `.example.md` suffix prevents that.

**What to keep, what to replace.** The section headings, the table shapes (advisory locks, build sessions), the format of each rule (`field, restriction, restriction`), and the order of sections are the template. The specific values (Python 3.12, the four lock numbers, the four S-sessions, the field names) are myapp-specific. Replace the values; keep the structure.

This file is read automatically by Claude Code at the start of every session. It is a constraint sheet, not a spec. Read the linked documents for full detail.

---

## Stack

- Language: Python 3.12+
- Framework: FastAPI 0.115+
- DB driver: asyncpg
- Migrations: Alembic
- Test runner: pytest with `-W error`
- Linter: ruff
- Type checker: mypy (strict mode)

---

## Package layout

```
src/
  api/        FastAPI route handlers, one module per resource
  auth/       JWT middleware, token refresh, key rotation
  billing/    subscription, grace period, retry logic
  db/         asyncpg pool, tenant-scoped query helpers
  jobs/       background workers
  notify/     email + push pipeline
  shared/     pure utilities, no I/O

migrations/   Alembic versions
tests/        pytest, mirrors src/ layout
testutil/     fixtures and factories, test-only
```

---

## Import rules

- No circular imports.
- `api/` may import `db/`, `auth/`, `billing/`, `notify/`. Reverse direction is forbidden.
- `db/` may import `shared/` only.
- `testutil/` is test-only, never imported by production code.
- All external packages must already be in `requirements.txt`. Ask before adding new dependencies.

---

## Field exclusion rules. HARD CONSTRAINTS

These fields must NEVER appear in log output, APM span tags, error messages, or API responses:

- `customer_email`, never logged, never returned outside the authenticated account-info endpoint
- `payment_token`, never logged, never returned in any response
- `refresh_token`, never logged, returned only in the immediate `/auth/refresh` response body
- `api_key`, never logged, never returned, never written to plain-text storage
- `password_hash`, never logged, never returned, hashed write only

Permitted with restrictions:

- `customer_id`, DEBUG level only, structured form (`{customer_id: <value>}` not bare string interpolation), never in span tags

The same field names also belong in the docs-repo's `scripts/rag_core/scrub.py` `EXCLUDED_FIELDS` list. The two surfaces enforce different things: this CLAUDE.md governs the application's runtime surface (logs, spans, error messages, API responses), while `scrub.py` redacts value-bearing assignments (quoted values, `=`-with-bare-token) that survive into doc chunks at index time. Copy the field list across; do not assume scrub.py enforces the runtime rule.

Violations found during code review are fixed in the same session.

---

## Data isolation. MANDATORY

Every handler that reads, writes, or deletes user data must scope its query with a `WHERE tenant_id = $1` clause using the value extracted from request context by the auth middleware. There is no Postgres RLS; application-layer scoping is the only enforcement mechanism. Missing `WHERE tenant_id` is a critical bug. The test suite includes a `test_tenant_scoping.py` fixture set that exercises every public handler with a foreign tenant id and asserts a 404 response.

---

## SQL rules

- Parameterised queries only with asyncpg's `$1`, `$2`, etc. No string concatenation in SQL.
- Every tenant-scoped query carries `WHERE tenant_id = $1`.
- Every function that does I/O takes `conn: Connection` (or `pool: Pool`) as its first parameter. No global pool access.
- Transactions are explicit: `async with conn.transaction():`. No autocommit-by-default code paths.

---

## Advisory lock registry

| Lock number | Job                                  |
|-------------|--------------------------------------|
| 1001        | daily billing reconciliation         |
| 1002        | weekly subscription-state sweep      |
| 1003        | hourly notification fan-out batch    |
| 1004        | nightly orphan-storage sweep         |

Adding a lock: pick the next free number, document the job here in the same PR.

---

## Migration discipline

- Naming: `{4-digit}_{snake_case}.sql`, sequential. This is a project override of Alembic's default 12-character hash IDs, traded for legibility in `migrations/` listings.
- Forward-only at MVP. No down migrations.
- One migration per logical change. Test locally with `alembic upgrade head` against a fresh DB before committing.
- Every migration that adds a NOT NULL column includes a backfill step in the same file.

---

## Branching and CI

- Trunk-based: all commits push to `main`. Feature branches only when a change needs more than one session of review.
- CI steps in order: build, `ruff check`, `mypy --strict`, `pytest -W error`, codegen validation, docker build, deploy to staging.
- Failing CI is fixed in the same session. Do not merge red.

---

## OpenAPI / API spec sync

- `api/openapi.yaml` is the source of truth for the public HTTP surface.
- The spec update and the code change must be merged in the same session.
- A handler whose responses diverge from the spec is a defect; the spec-vs-route check in CI flags it.

---

## Commit message format

`<type>(<scope>): <description>`

Types: `feat`, `fix`, `refactor`, `test`, `chore`, `docs`, `db`.

Scopes: `api`, `auth`, `billing`, `db`, `jobs`, `notify`, `shared`.

Lowercase, imperative mood, no period, under 72 characters.

---

## Log file discipline

At the end of every session, update `docs/track-build-log.md` in the docs repo with:

- What was built (one line per spec or build-guide section completed)
- Any deviations from the spec, or an explicit statement of none
- Decisions made during the session that should be recorded as a `*-dec-*.md` document
- Bugs found and how they were resolved
- What the next session should start with

---

## Build sessions

| Session | Build guide                                                                                    |
|---------|------------------------------------------------------------------------------------------------|
| S1      | `docs/05-spec-build-guide-s1-scaffold.md`                                                      |
| S2      | `docs/05-spec-build-guide-s2-auth.md` (target shape: `examples/sample-docs/after-authentication.md`) |
| S3      | `docs/05-spec-build-guide-s3-billing.md`                                                       |
| S4      | `docs/05-spec-build-guide-s4-notifications.md`                                                 |

Pass criteria for session N must be green before session N+1 starts.
