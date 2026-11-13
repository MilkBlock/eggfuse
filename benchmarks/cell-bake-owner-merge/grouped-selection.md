# Share static witness selection across operations and Entries

The expanded prefix catalog removed real generic lookups but increased repeated
route probes. The old compiled representation repeated a static source-address
key under each RHS operation. Runtime separately searched that key for each
constructor, even when the query anchor and component shape were unchanged.

Compilation now groups targets by `(rule, Entry index, source shape, source
ordinal, source code, source operation)`. Each group contains its ordered RHS
operation/target lists. The former operation-specific address maps are consumed
and dropped during compilation, rather than retained beside the new groups.
The per-operation Entry list still excludes operations without a compiled route.

The coordinator keeps one last selected group (including a negative selection).
It is bounded scratch in the existing ownership runtime, not a field in each
Cell, Entry, suspended RHS or worker result. The key includes rule and Entry index,
and the catalog is immutable during execution, so the same pure lookup may be
reused across different Entries or Runs. Each access reads the current
anchor/frame/component; any changed static key causes a fresh selection. Multiple Entry anchors may
replace one another in this single scratch slot; it is not an unbounded cache.

Only static dispatch is cached. A group contains no actual result values or
instance addresses. A hit resolves the target in the **current** component and
still performs the same ownership, visibility, current-key and final admission
checks. Union alone need not invalidate static wiring, but cached Eq/liveness
proofs would be unsound and are not stored. Component growth changes the shape
key; anchor retirement fails the current frame lookup; target retirement and
forwarding remain final-admission failures. Worker readers never access this
coordinator scratch and acquire no new synchronization.

## Validation and accounting

The new multi-operation fixture constructs Start, Pair and Wrap across stages,
then reuses Start and Pair in one Entry before a new suffix. It observes selection
reuse, fewer generic queries than the uncataloged control, identical exports,
stage snapshots and binding audit. All 59 ownership integration tests pass.
Existing prefix cases retain nontrivial union, deletion and residual construction.

Counters distinguish:

- `constructor_cell_route_anchor_reads`: current anchor/component reads, still paid.
- `constructor_cell_route_probes`: actual static-address map searches.
- `constructor_cell_route_selection_reuses`: searches eliminated by a matching selection.
- `constructor_cell_route_operation_checks`: the new group-local operation lookup.

Anchor reads must equal searches plus selection reuses. Candidate field checks,
accepted witnesses and generic lookup counts must remain identical to the prior
same-catalog run. These constraints prevent a counter rename, silently lost
routes or weaker candidate checking from masquerading as removed work.

`grouped_selection.py` freezes a newly built executable and replays the unchanged
`prefix-all` catalogs against the saved source Run/terminal checks. Its collector
also compares against the previous `prefix-all/checked.json` and rejects changes
to program identity, final state, Run count, generic lookups or candidate
admission work. It records the candidate binary and baseline report digests.

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/grouped_selection.py out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/grouped-selection.json
```

This is actual standalone Cell runtime work accounting, not native egglog
acceptance or a timing measurement. The grouped compiled layout adds an operation
index and the graph gains one bounded scratch record; full memory effects must be
measured before claiming compression. The original large-egraph compression goal
is not discharged by dispatch savings.

## Observed work on the unchanged expanded catalogs

All 2,652 saved Run checks and four terminal checks pass. Every pre-existing
runtime work counter except route searches is identical to the previous binary;
this includes accepted witnesses, candidate comparisons and generic lookup work.
All-features and no-default-features runtime checks also pass.

| case | address-map searches before → after | searches eliminated | new operation-index checks |
| --- | ---: | ---: | ---: |
| fact | 472 → 241 | 231 (48.9%) | 193 |
| loopfact | 410 → 230 | 180 (43.9%) | 133 |
| sum-bits | 4,405 → 3,310 | 1,095 (24.9%) | 1,376 |
| dot-product | 3,033 → 2,118 | 915 (30.2%) | 1,230 |

The first prototype cleared the static selection at each Entry boundary. It
removed only 108/107/482/329 searches. Inspection showed that this was unnecessarily
restrictive: the complete dispatch key and immutable catalog make the selection
independent of actual instance identity. The final implementation shares that
pure selection across Entries, while resolving and validating current target
facts on every use. The multi-operation test uses different bound values in two
instances and specifically requires selection reuse beyond per-Entry reuse.

Anchor reads are unchanged. The new operation-index lookups and full-key cache
comparisons still cost work, so the reductions above are not speedup percentages.
The experiment has not measured total compiled-table bytes or latency. The
catalog remains experimental; this is a verified reduction in repeated dispatch,
not evidence that the requested large runtime compression is complete.

Use `--collect-only` with the analysis script to recheck these saved reports
without building or replaying the workloads.
