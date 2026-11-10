# Reject missing attribute reads before Cell execution

Baseline: `98e0ffd3`, after correcting synthetic collision deltas. This changes
the standalone Cell CPU, not native egglog. It records bounded work and
semantic checks; no new full throughput result or general sparsity proof.

Configuration clarification: the historical canonical Raytrace prefix below
did not enable `--repair-ports --entry-publications`; both sides used the same
legacy setup. Its work reductions remain valid for that setup, but its repair
and publication counts do not describe the main throughput configuration.
See the [aligned diagnostic](../cell-prefix-configuration/README.md). The
sum-bits main-CLI lanes already enabled those options.

## Opportunity from actual executions

Fresh attribution of the first 1,280 Raytrace Runs shows 17,578 `Expr-size`
bindings, 11,774 actual function updates and 5,804 unchanged writes. Bop's
1,480 matches all change its result; Single changes 2,956 of 2,991. Skipping
those successful rules wholesale would be wrong. Get changes 2,769 of 7,311
writes, but an absorbed min write alone still does not prove its query or
completion can be discarded.

There is a more direct opportunity: Cell Entries preparing failed attribute
reads. A Get constructor Entry supplies its tuple key; its first query reads
`Expr-size(tuple)`. The previous support gate only admitted one-read unary
constructor queries, so it could not reject that missing mutable attribute.

The gate now reads the **first existing Cell query instruction** and its Entry
operand directly. It no longer searches a second Entry projection to recover
that same mapping. If a bound Eq key column has no candidates in the already
built, current query index, the first read cannot succeed. The Entry returns
before Cursor expansion, route materialization and query/worker preparation.
Multi-read point queries and multi-column keys use the same proof.

This is a current-Run necessary test, not a cross-Run negative fact or a
completed-state certificate. A fingerprint hit still requires the full exact
query. An unavailable or stale column keeps the old path. No index is built,
no negative cache is retained, and no additional per-instance state is stored.
The first instruction must be a table point read: primitives and earlier reads
cannot be reordered. Residual expansions retain their existing Free Join
admission instead of repeating that filter in front of it.

The source Run boundary and actual returned witnesses remain authoritative.
There is no new scheduled block switch or successful-RHS takeover here. The
shared typed Cell instructions prove only which unsuccessful preparation can
be deleted; late values, deletion/recreation, union, exact keys, delta ownership
and visibility still use the existing lifecycle.

## Bounded work

| Work, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Actual table queries | 12,526 → 12,085 | 609,685 → 578,591 |
| Routed Spine Entries | 3,682 → 3,241 | 188,637 → 157,543 |
| Query worker Spine Entries | 1,188 → 1,007 | 51,537 → 39,389 |
| Support plan inspections | 573 → 573 | 1,543 → 1,543 |
| Support attempts | 1,409 → 2,552 | 83,145 → 141,730 |
| Unavailable-index attempts | 259 → 325 | 13,646 → 24,776 |

Queries decrease 3.52% / 5.10%. Each newly rejected Entry reconciles to one
eliminated table query and one avoided Spine dispatch. Get's Raytrace Spine
Entries decrease from 11,000 to 411, Concat's from 4,582 to 161. Ordinary Free
Join probe counts remain identical. These are not counts of committed changes.

All matching results, actual writes/unions, completed steps, publications and
Ripsat completions remain equal. The new cost is 1,143 / 58,585 additional
support attempts, including 66 / 11,130 unavailable-index attempts. The existing
`current-column/v1` work ledger charges plan inspections and all attempts;
rejection totals earn no second credit. Counting a support probe and a complete
query as equal latency would be unjustified, so this does not establish speedup.

The normal, stable-port and completed-catalog sum-bits lanes preserve their
exact graphs and every ordered Run record. The bounded Raytrace lane does too.
The completed catalog still exercises direct Ripsat completion. See results.json
for all counters and input/binary/report hashes. The prefix includes early
attribute propagation, not the complete Raytrace distribution.

## Validation and reproduction

The new mutable-read regression requires this gate to reject Entries, then
checks late values, deletion and recreation against native checks and every
Run's graph/ordered bindings in serial, inline and pooled execution, using both
backends. A separate multiple-result fixture keeps ordinary residual admission
and verifies late constructors, union, deletion/recreation and nonzero key
columns. Existing forced-collision and stale-index tests remain authoritative.
Runtime unit, worker, publication, stable-port, collision and query-receipt
regressions pass, as do the Bake work-credit tests. Sum-bits native choice
diagnosis returns pass / 0 without changing its contract. README compile/run/
bench and minimal/all-feature compilation pass; bench repeat 1 is only a smoke
check, not a performance campaign.

```sh
cargo test --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports --test query_workers
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH_SUM --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_PREFIX 1280 4 64 canonical
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-attribute-locality/semantic out/cell-attribute-locality/semantic-acceptance.json
python3 benchmarks/cell-attribute-locality/collect.py out/cell-attribute-locality benchmarks/cell-attribute-locality/results.json
```

Use the cell-fixed-reads frozen inputs and cell-collision-delta baseline exports.
Repeat sum-bits with `--local-congruence` and the completed catalog for the
remaining lanes. The collector reads saved exports and launches no workloads.
