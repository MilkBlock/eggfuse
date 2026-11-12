# Batch review before structural changes

Use `python3 benchmarks/cell-trail-depth/review.py HISTORY CATALOG PROGRAM OUTPUT_DIR`.
It writes every retained event, its full retained parent chain and witness, a
rule dictionary, and ALL path patterns of lengths 2–6. No new runtime execution
is needed. Coverage counts overlap and are not saved operations.

The saved sum-bits round-0 trace yields 141 patterns across 18 rules:
39 length-2, 44 length-3, 37 length-4, 20 length-5, and one length-6 pattern.
174 parent events fork; maximum fanout is nine. The frequent 143->137 suffix
occurs 196 times across 120 retained roots, covering 355 distinct events.
143->55->143->137 occurs 33 times across 33 retained roots. Different events
can share prefixes; frequency, independent roots and covered events differ.

Of 723 known parent edges, 457 span four Runs and 131 span three Runs. Some
span hundreds (maximum 776). Same ruleset must not be confused with adjacent
Runs. Retained ancestry is incomplete, the catalog has no composed joins, and
neither candidate losses nor actual Cursor depths are recorded.

## One coordinated optimization batch

1. Shared suffixes and forks: build reusable continuation states around actual
   high-coverage suffixes, retaining branch-specific output incidence. Compare
   final-state behavior, not just rule sequences. Avoid allocating copied
   prefix bindings for each fork.
2. Recurrent fragments: analyze 143/55/137/145 together, including staged
   LazyUnion effects. Derive the minimum result interface required by exits.
   Repeated rule IDs do not prove equal input ports; do not merge instances on
   that basis or erase source effects.
3. Lifetime compression: separate continuation identity from retained Results.
   Keep only demanded result slots across long Run gaps, with existing
   visibility/generation/deletion checks. Cursor depth is not retention cost.
4. Joint admission: compile this batch from the same trace, count overlapping
   avoided work once, and compare total storage, queries and publication work.
   One final performance comparison follows the batch's semantic checks.

Before that implementation, collect a trained-catalog trace ONCE with candidate
min/max/selected Cursor depth per equal-input group, before/after switch pc,
transition/reset reason, live retained-slot layout, completion validation result,
and completed rule/Run/output ancestry. This is the missing evidence for winner
bias and actual misses; the current round-0 archive cannot answer those questions.
Keep diagnostics opt-in and avoid duplicating runtime bindings.

The unfinished staged-route index change and its not-yet-compiling regression
remain uncommitted pending this analysis. They are not accepted results. No
speedup or runtime takeover is claimed by this review.
