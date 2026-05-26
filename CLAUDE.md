# {{PROJECT_NAME}}. Claude Code Constraints

This file is read automatically by Claude Code at the start of every session.
It is a constraint sheet, not a spec. Read the linked documents for full detail.

---

## Stack

<!-- Define your technology choices here. Examples:
- Language: Go 1.23+ / Python 3.12+ / TypeScript 5.x
- Router/Framework: chi / FastAPI / Express
- DB driver: pgx v5 / asyncpg / prisma
- Migrations: Goose / Alembic / Prisma Migrate
- API codegen: oapi-codegen / openapi-generator
-->

---

## Package layout

<!-- Define your canonical package/folder structure here.
List every top-level directory and what it contains.
This prevents Claude from creating files in the wrong location. -->

---

## Import rules

<!-- Define dependency direction between packages.
Which packages may import which? What cycles are forbidden?
Examples:
- No circular imports.
- `handlers` may import `db` but not vice versa.
- `middleware` must not import `handlers`.
- `testutil/` is test-only, never imported by production code.
- All external packages must already be in go.mod / requirements.txt / package.json. Ask before adding new dependencies.
-->

---

## Field exclusion rules. HARD CONSTRAINTS

<!-- List fields that must NEVER appear in log output, APM span tags,
error messages, or API responses. This is your data protection layer.

Format:
  field_name, never logged, never returned in any response
  field_name, never written to DB, never logged

Add permitted-with-restrictions fields:
  field_name. DEBUG level only, structured form, never in span tags

Violations found during code review are fixed immediately in the same session. -->

---

## Data isolation. MANDATORY

<!-- Define your tenant isolation strategy.
Example: Every handler that reads, writes, or deletes user data must scope
its query with a WHERE tenant_id = $1 clause using the value extracted from
context by the auth middleware. There is no RLS. Application-layer scoping
is the only enforcement mechanism. Missing WHERE clauses are a critical bug. -->

---

## SQL rules

<!-- Define SQL safety rules. Typical examples:
- Parameterised queries only, $1, $2, etc. No string concatenation in SQL.
- Every tenant-scoped query carries WHERE tenant_id = $1.
- context.Context is the first parameter of every function that does I/O.
-->

---

## Advisory lock registry

<!-- If you use advisory locks for background jobs, register them here
to prevent collisions.

  | Lock number | Job                              |
  |-------------|----------------------------------|
  | 1001        | (describe job)                   |
-->

---

## Migration discipline

<!-- Define your migration naming and execution rules.
Examples:
- Sequential integer naming: {7-digit}_{snake_case}.sql
- Forward-only at MVP. No down migrations.
- One migration per logical change. Test locally before committing.
-->

---

## Branching and CI

<!-- Define your branching strategy and CI pipeline.
Examples:
- Main-only. All commits push directly to main.
- CI steps in order: build, test (with race detection), lint, codegen validation, docker, deploy
- Failing CI is fixed in the same session.
-->

---

## OpenAPI / API spec sync

<!-- If you have an API spec (OpenAPI, GraphQL schema, etc.):
- The spec is the source of truth.
- The spec update and the code change must be merged in the same session.
- A handler that diverges from the spec is a defect.
-->

---

## Commit message format

<!--
  <type>(<scope>): <description>

Types: feat, fix, refactor, test, chore, docs, db

Scopes: (list your package/domain scopes here)

Lowercase, imperative mood, no period, under 72 characters.
-->

---

## Log file discipline

<!-- At the end of every session, update the build log with:
- What was built
- Any deviations from the spec (or explicit statement of none)
- Decisions made during the session
- Bugs found and how they were resolved
- What the next session should start with
-->

---

## Build sessions

<!-- List your build sessions in order. Each session document contains
the exact Claude Code prompt to run. Pass criteria for session N must
be green before session N+1 starts.

  S1, docs/05-spec-build-guide-s1-scaffold.md
  S2, docs/05-spec-build-guide-s2-auth.md
  ...
-->
