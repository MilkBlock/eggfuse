# Reject impossible Cell Entries before continuation dispatch

Baseline: `497d5300`. This is an actual takeover in the standalone Cell CPU,
not a native egglog change. It has bounded work and allocation evidence, but
no new throughput result or general sparsity proof. Query workers remain
optional; the gate also applies to serial Cell queries.

## Evidence and compiler proof

The [attribute attribution](../cell-attribute-profile/README.md) found that
98.55% of successful Single-size bindings really update their result. Skipping
all repeated attribute propagation would be incorrect. It also found over
1.13 million Single Spine entries for about 307 thousand successful bindings.
This motivates rejecting impossible inputs before preparing their execution.

The existing typed Cell query and Entry projection prove a narrow case: the
remaining query is one complete-key read of a unary constructor, and its Eq
key comes directly from the Entry's known column. If that key has no support
in an already-built, current query-index column, the query cannot succeed.
The runtime returns before expanding the Cursor, building the routed query
record, sorting/dispatching it, allocating query scratch or reading the table.

There is no new maintained index, negative cache, subscriber list, binding
copy or intermediate marker. The gate borrows the existing column only. An
unbuilt column or a mismatched table version keeps the ordinary path. A
fingerprint hit also keeps the complete exact query: collisions can admit
extra candidates, never establish equality. Row lifetimes, late inputs,
union, delta ownership and original Run visibility retain their existing
authority. Nothing is certified across Runs by this negative test.

This uses static Cell structure to delete work for known-impossible Entries;
it does not replace successful RHS effects or their required publication.

## Bounded results

| Work, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Actual table queries | 18,633 → 17,661 | 751,255 → 690,981 |
| Entries rejected before continuation | 0 → 972 | 0 → 60,274 |
| Added support attempts | 0 → 1,860 | 0 → 91,621 |
| Unavailable column/version attempts | 0 → 295 | 0 → 15,387 |
| Allocation calls | 94,101 → 93,665 | 2,591,621 → 2,576,984 |
| Reallocation calls | 18,241 → 18,104 | 388,933 → 388,424 |
| Requested bytes | 24,596,563 → 24,138,107 | 1,101,340,833 → 1,078,423,225 |

Query counts decrease 5.22% / 8.02% in these cases. Every eliminated query
reconciles to one rejected Entry. The allocator totals come from separate
instrumented executables and exclude setup/export; requested bytes are not
RSS. All matched bindings, actual writes, completions and publications remain
the same. The completed sum-bits catalog retains its direct completions.

The gate adds per-batch plan checks and per-Entry support probes. Both enter
the Bake work ledger, including unsuccessful attempts to use an unavailable
column. Rejection counts earn no synthetic credit: savings already appear as
fewer queries and dispatch operations. Equal-weight ledger scores still do
not predict time. The ordinary and stable sum-bits lanes and the completed
catalog preserve exact final graphs and ordered Run records. See results.json
for task counts, existing index storage, all costs and input/output hashes.

The prefix includes early attribute propagation and is larger than the earlier
128-Run initialization prefix. It is still not full Raytrace. Full throughput
remains subject to the agreed implementation-batch checkpoint.

## Validation and a separate baseline discrepancy

96 runtime unit tests, 40 integration tests and five work-credit tests pass.
The new index test checks forced collisions, absent/unbuilt columns and stale
negative results before late insertion. The new source fixture verifies late
constructor insertion, union, deletion and recreation against native source
checks and compares every Run's ordered bindings and graph across serial,
inline and pooled execution, in both backends. It asserts that the gate
actually rejects Entries. Sum-bits native choice diagnosis returns pass / 0.
Minimal/all-feature compilation and README compile/run/bench pass; the one
bench repetition is only a smoke check.

`baseline-refill.egg` preserves a separate unresolved baseline discrepancy.
Native `parse_and_run_program` passes its checks, while baseline `497d5300`
fails `device-backend-check-0` when the fill rule is invoked again after union.
The same failure occurred before this gate was applied. The passing lifecycle
fixture omits that extra refill and separately warms the existing support
index through an ordinary three-atom query. This does not establish that the
refill discrepancy is harmless or just an allowed extraction tie; its source
contract remains outside the sum-bits acceptance proof and needs investigation.

Follow-up: [collision delta repair](../cell-collision-delta/README.md) isolates
and fixes this discrepancy. Retiring a duplicate had incorrectly refreshed an
unchanged survivor's timestamp and replayed the fill rule. The saved baseline
fixture and measurements above remain the original checkpoint evidence.

The [first-attribute-read extension](../cell-attribute-locality/README.md) uses
the Cell instruction's Entry operand directly and admits current mutable reads
and longer point queries, while retaining ordinary residual admission.

## Reproduction

Freeze baseline and candidate executable paths from Cargo JSON, using the
cell-fixed-reads programs and identical flags:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH_SUM --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_PREFIX 1280 4 64 canonical
```

Use a separate build with `allocation-metrics` for allocator diagnostics.
Repeat sum-bits with `--local-congruence` and with the completed catalog for
the remaining semantic lanes. The read-only collector checks saved exports,
ordered Runs and accounting; it never launches workloads:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-point-support/semantic out/cell-point-support/semantic-acceptance.json
python3 benchmarks/cell-point-support/collect.py out/cell-point-support benchmarks/cell-point-support/results.json
```
