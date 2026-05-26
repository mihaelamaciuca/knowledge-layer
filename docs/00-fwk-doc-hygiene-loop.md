---
file: 00-fwk-doc-hygiene-loop
area: 0
area-name: Project Management
type: fwk
title: Doc Hygiene Loop
status: complete
date: 2026-05-13
depends-on:
  - 00-pol-document-standards
feeds-into:
  - area-0-project-management
---

# Doc Hygiene Loop

## Purpose

The 15-minutes-per-week process for clearing doc drift. The system surfaces flagged claims via `get_drift_report`; you fix one, fix two, or skip. Never a full doc review. This is the recurring process that keeps the corpus honest as it grows.

## When this runs

Weekly. Pick a fixed slot (Monday morning, end of week, after the Friday review, whichever sticks). The loop is designed to fit in 15 minutes; if it stretches longer, the queue has built up and the cadence needs to be more frequent, not the session longer.

## Pre-requisites

The four drift signals (stale-string, dangling-ref, dep-out-of-date, decision-contradict) are computed by `scripts/detect_drift.py` and exposed via the MCP tool `get_drift_report(top=N, signal=…, area=…)`. No setup required, just call the tool.

## The loop

Every week, run this in Claude Code (one chat, sequential):

1. **Pull the queue.**
   `get_drift_report(top=10)` returns the highest-priority items. Each item has a file, line (when applicable), signal, reason, authoritative source, and suggested replacement.

2. **Triage each item, in order.** For each item, decide:

   a. **Fix it** if the suggested replacement is right and the change is self-contained: open the file, make the edit, commit with `docs: drift-fix, <one-line-description>`, push.
   b. **Skip it** if the item is a false positive (e.g., a stale-string regex hit on a markdown label like `**Email:**`): record the skip in the next session's log, no commit.
   c. **Defer it** if the fix needs a real decision (e.g., a dependency-out-of-date that needs a content review, not a mechanical edit): mark the doc with `status: needs-review` in its frontmatter and move on. The next reindex re-flags it; the next loop catches it again.

3. **Stop after 15 minutes**. Whatever's left in the queue waits for next week. Do NOT extend the session: the discipline of bounded time is what makes the loop sustainable.

## What "needs-review" means

`needs-review` is a status value in the `00-pol-document-standards` vocabulary. A doc with `needs-review` is searchable but bannered in `search_docs` results. The drift report keeps surfacing it until the status flips back to `complete` (or `superseded` etc.). It's the system's way of saying "I know this doc is drifting; I haven't fixed it yet."

## Per-signal triage notes

Concrete guidance for each signal type, what's usually a true positive and what's usually noise.

### `stale-string`

Mostly true positives. The exclude patterns in `scripts/stale_strings.py` are tuned but not perfect. If a hit fires repeatedly on the same legitimate content, add the substring to the pattern's `excludes` list (one-line edit + PR + merge). Updated patterns flow into the next loop automatically.

### `dangling-ref`

True positive when the target doc was renamed (look in `scripts/doc_rename_map.json` for known renames; if the target is in the map but the audit script didn't auto-fix, the loop runs `python3 scripts/audit_docs_standards.py --fix`). True positive when the target was deleted (mark the citing doc's status to `needs-review` and update its frontmatter to point at a real file). False positive when the target is a planned-but-unwritten doc, in that case add an entry to `area_redirects` in `scripts/doc_rename_map.json` so the reference resolves to the capability area instead of dangling.

### `dep-out-of-date`

Lower confidence. A newer commit on doc B doesn't always mean A is stale (B's commit might be a typo fix). Triage rule: open both diffs side-by-side; if B's recent commit changed any settled claim, A needs a review. If B's commit was cosmetic, skip.

### `decision-contradict`

Highest priority. If a chunk mentions decision topic X but doesn't mention the current_value Y, it might still be saying something correct (the chunk might be discussing X in a different context). The triage step is to read the chunk: does it explicitly state a value that contradicts Y? If yes, fix the chunk. If no (e.g., it's a historical note that says "we previously did X"), skip: the chunk is correctly contextualised.

## The loop's success metric

Queue size, week over week. The first few loops typically clear most of the initial backlog as patterns get tuned and dangling refs get fixed. After that, the queue stays small: a handful of items per week, all from the most recent docs touched.

If the queue grows for 3 consecutive weeks, increase the cadence to twice-weekly OR investigate WHY drift is accelerating (often: a slice of new specs being merged without dependency updates).

## Logging

Once a month, update your project's tracker log with a summary entry: items cleared, items deferred, signal patterns updated. Don't log every weekly session; the git history is the record.

## What this does not do

- **It does not block merges.** The audit-docs CI gate uses a separate threshold (counted violations); the drift report is for human review, not automatic blocking.
- **It does not replace doc reviews on PRs.** Real content reviews still happen during PR review. The hygiene loop catches drift that slips through.
- **It does not auto-fix.** Every fix is a human decision in this loop. Auto-fix tooling (rename map, scrub) runs at index time and PR time; the loop is for the cases the auto-fixers can't safely handle alone.
