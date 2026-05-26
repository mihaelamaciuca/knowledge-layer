---
file: 05-pol-data-retention
area: 5
area-name: Legal & Compliance
type: pol
title: Data retention policy
status: complete
date: 2026-05-26
depends-on: []
feeds-into:
  - area-3-engineering
also-touches: [4, 6]
---

# Data retention policy

> **Example document.** Bundled with the template to show what a `pol` (policy) doc looks like with valid frontmatter, scoped rules, enforcement, exceptions, and a version log. Replace or delete when you write your own.
>
> This is an internal operating policy, not legal advice. Regulatory citations are supporting context; consult counsel before applying any of this to a live product.

## Purpose, why this policy exists

Bounds how long the system stores user data, derived data, and operational logs.

Retention longer than necessary increases the blast radius of a breach, expands the scope of regulatory obligations (GDPR Art. 5(1)(e) storage limitation, CCPA §1798.105 right to delete), and slows recovery. Retention shorter than necessary breaks user expectations and audit obligations. The eight rules below pick a defensible point for each data class.

## Scope, who and what this policy applies to

Covers user-created content, account metadata, API request logs, audit logs, operational metrics, exports, and database backups. Excludes vendor-managed backups outside the system's control, fully aggregated analytics with no tenant attribution, and the knowledge-layer corpus under `docs/`.

Applies to every service that reads, writes, or copies tenant data, including background jobs, analytics pipelines, and ad-hoc scripts.

## Rules, the eight specific commitments

Eight rules covering: active-account preservation, deletion with a 30-day grace then hard delete, four log-class retention windows (API logs, audit logs, operational metrics, database backups), the 24-hour exports window, and the requirement that every tenant-data store appears in the approved-store registry.

### Rule 1, active account data

**Statement.** Active account data MUST be retained while the account is in good standing (`status='active'`). No scheduled job MAY purge rows where `status='active'`.

**Rationale.** Active accounts are in-use data; removing them is data loss, not retention. Any "purge inactive accounts after N months" policy belongs in the product spec, not this policy.

**Counterexample.** A nightly job that drops accounts with no login for 12 months violates this rule.

### Rule 2, deleted account data, 30-day grace then hard delete

**Statement.** On account-deletion request, the account MUST be marked `deletion_pending` immediately. After exactly 30 days, every row tagged with the account's `tenant_id` MUST be hard-deleted across every table in the approved-store registry (Rule 8).

**Rationale.** The 30-day window satisfies GDPR's Art. 17 "without undue delay" for erasure while allowing user-initiated recovery for the common case of accidental deletion.

**Example (correct).** Day 0: status → `deletion_pending`. Day 30: `DELETE FROM ... WHERE tenant_id = $1` across every registered table.

**Example (incorrect).** Soft-delete (`deleted=true` flag, rows retained). Soft-delete is not erasure.

### Rule 3, API request logs, 90 days

**Statement.** Per-request API logs MUST be deleted 90 days after the request timestamp.

**Rationale.** 90 days is long enough to debug user-reported issues across a quarterly review cycle; longer windows raise breach exposure without proportionate operational value.

### Rule 4, audit logs, 2 years

**Statement.** Audit logs (authentication events, permission changes, admin actions) MUST be retained for 2 years from event timestamp, then deleted.

**Rationale.** Two years covers SOC 2 evidence windows (CC6.5, CC7.2) and most contractual audit-window requirements.

### Rule 5, operational metrics, 13 months

**Statement.** Aggregated operational metrics (latency, error rate, throughput, per `service` and `endpoint`) MUST be retained for 13 months, then deleted or downsampled.

**Rationale.** 13 months supports year-over-year comparison with one month of overlap. Beyond that, storage cost outweighs analytical value.

### Rule 6, database backups, 7 days

**Statement.** Database backups MUST be retained for 7 days, then deleted. Point-in-time recovery windows beyond 7 days are not supported.

**Rationale.** 7 days covers detection of most data-corruption incidents while keeping backup storage and the deleted-data window bounded.

### Rule 7, exports and downloads, 24 hours

**Statement.** User-facing data exports (CSV, JSON, archive downloads) MUST be deleted from the export bucket 24 hours after generation. Pre-signed URLs MUST expire within the same window.

**Rationale.** Exports are short-lived artifacts. A 24-hour window is enough for the user to download and copy elsewhere; longer windows turn the export bucket into a parallel data store outside the registry (Rule 8).

### Rule 8, approved-store registry, no unregistered tenant data

**Statement.** Every table, bucket, queue, cache, or other store that holds row-level tenant data MUST be listed in `docs/04-spec-data-stores.md` (the approved-store registry). A weekly CI check MUST fail if a table or bucket holds a `tenant_id` column or key prefix and is not in the registry.

**Rationale.** Retention rules only work if the deletion sweep knows where the data lives. Unregistered stores produce shadow copies that survive Rule 2 deletion and create the exact regulatory exposure the policy exists to bound.

## Enforcement, how each rule is checked

Three mechanisms: a daily retention sweep (Rules 2 through 7), a weekly registry CI check (Rule 8), and a per-PR reviewer obligation. The engineering team owns all three.

| Rule | Check | Cadence | Mechanism |
|------|-------|---------|-----------|
| 1 | No purge job targets `status='active'` | per PR + weekly grep | reviewer + CI |
| 2 | Zero rows with `deletion_pending` age > 30 days | daily | retention sweep job |
| 3 | `MAX(age)` on API log table ≤ 90 days | daily | retention sweep job |
| 4 | `MAX(age)` on audit log table ≤ 2 years | daily | retention sweep job |
| 5 | `MAX(age)` on metrics table ≤ 13 months | daily | retention sweep job |
| 6 | Backup storage listing shows ≤ 7 days of files | daily | retention sweep job |
| 7 | Export bucket has no objects older than 24 hours | daily | retention sweep job |
| 8 | Every tenant-keyed store is in the registry | weekly | registry CI check |

The retention sweep holds Postgres advisory lock **1005** (`retention_sweep`) for the duration of its run. Lock 1005 is in addition to the four locks already in the CLAUDE.md advisory-lock registry (1001 daily billing, 1002 weekly subscription, 1003 hourly notification, 1004 nightly orphan-storage). Adding lock 1005 to the project's CLAUDE.md registry is a precondition for compliance with this policy.

A reviewer obligation applies on every PR: any PR introducing a new tenant-keyed table, bucket, or queue MUST update the approved-store registry in the same commit. CI fails the PR otherwise.

## Exceptions, when a rule can be waived

Three triggers may suspend deletion under Rule 2 (deleted-account purge), Rule 3 (API log expiry), or Rule 5 (operational-metric expiry). Each suspension MUST be recorded as a `*-dec-*.md` decision with `status: complete`, citing this policy, naming the data subject (tenant_id or scope), the start date, and the expected end date.

| Trigger | Action | Approver | Max duration |
|---------|--------|----------|--------------|
| Active litigation hold | Pause `retention_sweep` for the named `tenant_id`; record decision before next sweep run | Legal counsel | Duration of hold |
| Regulatory request | Pause `retention_sweep` for the named scope; preserve current state | Legal counsel | Duration of request |
| Active security investigation | Pause `retention_sweep` for the named `tenant_id`; preserve current state | Head of Security | 90 days; renew via new decision |

Suspensions expire automatically at the recorded end date. A renewed suspension requires a new `*-dec-*.md`; silently extending an existing one is a policy violation.

## Version history

Change log for this policy. Substantive changes update `date` in the frontmatter; this table records the diff.

| Version | Date | Change | Author |
|---------|------|--------|--------|
| 1.0 | 2026-05-26 | Initial version | (example) |
