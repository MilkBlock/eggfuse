# Duplicate retirement is not a new query delta

Baseline: `d1fba785`. This fixes the standalone Cell CPU's source execution
semantics; the vendored native egglog implementation is unchanged. Bounded
work reductions below are not a throughput result or a graph sparsity proof.

## Cause and correction

The previous [Entry support experiment](../cell-point-support/README.md)
preserved a native/Cell discrepancy in `baseline-refill.egg`. Three inputs
suffice to reproduce it:

1. `Start(x)` fills `Cost(x)` with 1; another rule overwrites it with 2.
2. Union merges two inputs and their duplicate `Start` constructors.
3. Run the original fill rule again.

Native keeps 2. Before this fix, Cell changes it back to 1. The surviving
constructor did not change, but collision retirement unconditionally refreshed
its epoch and published a new delta. That extra semi-naive match reran an
order-sensitive `:merge new` effect. Function collisions had the same problem
even when their merge left the surviving value unchanged.

Constructor collision now updates the survivor's epoch only when visibility
changes. Its queued output union still performs all actual equality changes
through the existing completion paths. Function collision publishes the
survivor only when the merged value changes. Duplicate retirement, witness
forwarding, index invalidation and pending key/output completion remain live.

This follows native `MergeFn::to_callback`, which replaces the surviving row
and timestamp only when the return value or subsumption changes. It also agrees
with the Cell runtime's ordinary `set_function_from` behavior. It adds no Cell
catalog, fact graph, binding copy, subscription or retained execution state.
The function path adds a result comparison and retains a copy of the old value
across merge evaluation; these are costs, not credited savings.

## Relevance to Cell locality

The last catalog's executions exposed expensive matching and publication,
while the saved refill fixture exposed a synthetic source of that work.
An already completed Cell need not be reactivated merely because another row
was absorbed. This correction removes those false activations before asking
Bake to share them. It is not a newly compiled cross-Run block switch.

Successful matches and maintenance events must not be confused with actual
new information. The remaining obligations are real key/output changes,
visibility, changed function values, late rows and the original source Runs.
No completed-state proof is extended across an unvalidated mutable read.

## Bounded work against the current branch

| Work, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Table queries | 17,661 → 12,526 | 690,981 → 609,685 |
| Executed rule bindings | 10,226 → 7,265 | 403,192 → 357,982 |
| Single-write attempts | 1,422 → 1,121 | 32,109 → 28,853 |
| Actual function updates | 1,450 → 1,450 | 24,935 → 24,935 |
| Actual unions | 1,039 → 1,039 | 33,888 → 33,888 |
| Repaired dependencies | 1,496 → 1,496 | 50,374 → 50,374 |

Queries decrease 29.08% / 11.77%. These are the same frozen programs and
four-worker configurations used by the preceding Entry support experiment.
No fresh full Raytrace throughput campaign was run. The repaired-dependency
count is unchanged: the deleted work is downstream of false delta publication.

Both final graphs have an exact rooted bijection, including every table,
scalar, equality and visibility bit: 4,045 / 249,137 rows. Raw Cell IDs differ
because fewer executions allocate frames. All source Run ordinals, rulesets,
paths, iterations, epochs and changed flags agree. Binding counts change in
81 / 220 Runs; requiring those erroneous baseline counts to remain equal
would preserve the bug. Results include affected ruleset aggregates and hashes.

Sum-bits choice diagnosis passes against the saved native contract. Raytrace
has a bounded comparison against the previous Cell runtime, not an independent
native semantic proof. Neither case establishes general scheduling equivalence.

## Validation

Six new integration tests cover the original source checks, unchanged
constructor/function/relation collisions, changed min results, congruence
outputs enabling parent matches, and inherited subsumption. The small fixtures
compare every Run to native, including an independent Eq partition check,
using canonical/stable backends and serial/inline/pooled queries. The original
refill checks also run with audit disabled. Existing worker, stable-port and
Entry-publication tests and 96 runtime unit tests pass. Minimal/all-feature
compilation and README compile/run/bench pass; bench repeat 1 is only a smoke
check. The sum-bits acceptance rules are unchanged.

```sh
cargo test --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports --test collision_delta
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH_SUM --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_PREFIX 1280 4 64 canonical
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-collision-delta/semantic out/cell-collision-delta/semantic-acceptance.json
python3 benchmarks/cell-collision-delta/collect.py out/cell-collision-delta benchmarks/cell-collision-delta/results.json
```

Use the cell-fixed-reads frozen programs and preserve the baseline exports
under `out/cell-point-support`. The collector only reads exports; it runs no
workloads and rejects unmatched graph, schedule or actual-update counts.
