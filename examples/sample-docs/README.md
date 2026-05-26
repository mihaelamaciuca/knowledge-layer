# Sample documents

A before/after pair showing the four prose writing rules in action on a complete document. Both files describe the same authentication middleware; only the writing differs.

Read `before-authentication.md` first, then `after-authentication.md`. The rules being applied (or violated) live in `docs/00-fwk-writing-guide.md`; the rationale behind each rule lives in `methodology.md` at the repo root.

Rule 5 (the 4000-character section-size limit) is checked mechanically by the audit script and does not need a side-by-side teaching example; the demonstration here is the four prose rules: section summaries, inline cross-references, one concept per section, and concrete searchable terms.

Neither file is part of the indexed corpus. Both live under `examples/sample-docs/` so the indexer's `docs/` glob does not pick them up, and the audit script does not flag the "before" file's deliberate violations.
