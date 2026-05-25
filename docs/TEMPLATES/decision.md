---
file: XX-dec-TOPIC
area: X
area-name: AREA_NAME
type: dec
title: TITLE
status: draft
date: YYYY-MM-DD
depends-on: []
feeds-into: []

# `decisions:` is the structured form scripts/build_decision_registry.py
# reads to populate the decisions table (which `get_decision` and
# `get_impact_targets` query). Every decision document SHOULD carry at
# least one entry. Drop the block if the doc records context only.
decisions:
  - key: example-decision-key       # stable slug, UNIQUE across the corpus
    decision: Short human-readable description of what is being decided
    current_value: "the chosen value"
    decided_on: YYYY-MM-DD
    cross_refs:                     # optional, other doc slugs that ground or reference this
      - XX-spec-related
    # supersedes: previous-key      # optional, set if this replaces another decision
---

# TITLE

<!-- Decision documents record a choice. They must include what was rejected
     and why, and what would trigger a change. -->

## Context

What question needs to be resolved? Why now?

## Options Considered

### Option A, [Name]

- **Description:** What this option entails
- **Pros:** What it gets right
- **Cons:** What it gets wrong or risks
- **Effort:** Rough cost/complexity

### Option B, [Name]

- **Description:** What this option entails
- **Pros:** What it gets right
- **Cons:** What it gets wrong or risks
- **Effort:** Rough cost/complexity

## Decision

**Chosen: Option [X]**

Why this option was selected over the alternatives.

## Rejected Alternatives

Why each rejected option was not chosen, specific, not generic.

## Change Triggers

What conditions would cause this decision to be revisited?

| Trigger | Signal | Action |
|---------|--------|--------|
| | | |

## Sign-off

Who approved this decision and when.
