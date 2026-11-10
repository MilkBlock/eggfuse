# Canonical constructor queries inside Cell tasks

Baseline: `634d082e`. This changes the standalone Cell CPU query executor, not
native egglog. Query workers remain explicitly enabled with `--query-workers`;
the default serial executor is unchanged. This is a short coverage/work check,
not throughput admission or evidence of general egraph sparsity.

## Opportunity and takeover

The previous Cell task reader admitted constructors only with complete stable
port ownership. The canonical backend, despite already storing repaired fields
and a current constructor index, could not use those tasks for constructors.
The saved 64-Cell catalog therefore left these existing point-query instructions
in the coordinator host. More joins for an already-completed RHS would not fix
this backend-specific gap.

The ordinary Cell Query already proves which instructions are full-key point
reads and which require enumeration. At a settled Run boundary, canonical
constructor birth/repair has installed current fields or retired the fact.
Workers now borrow those fields and the existing intern buckets directly. They
compare the complete key, preserve ordered collision selection, and return the
result, epoch and actual witness. No temporary Row or field-Arc clone is needed.
Nullary constructors retain the existing direct-member lookup. The reader adds
no graph copy, subscription, candidate index or per-instance fact representation.

The existing Cell grouping, scratch, Instance return and winner selection stay
authoritative. This replaces the selected entry's original query execution;
negative results are not rerun on the old host. Canonical coverage is independent
of ownership fragments. Stable storage retains its original coverage proof and
domain reader. Unsettled graphs, specialized Unit storage, enumeration and
existing history/context routes retain their original boundary handling.

Run changes cannot reuse these current values: mutable updates, new inputs,
union, visibility, watermark and delta ownership remain live obligations. The
borrow ends before RHS mutation. Canonical repair remains necessary and serial;
this does not make Cell grouping a proof of disjoint writes or parallel RHS.

## Actual short executions

All configurations use grain 64. Entry counts include inline work as well as
pool work; reduced coordinator-host counters do not mean every read moved off
the main thread.

| Work, old 4-worker → new 4-worker | sum-bits | Raytrace first 128 Runs |
|---|---:|---:|
| Cell task entries | 240 → 1,907 | 9,786 → 21,186 |
| Point reads in Cell task path | 269 → 2,082 | 9,786 → 21,229 |
| Canonical constructor reads there | 0 → 1,750 | 0 → 11,443 |
| Old coordinator continuation reads | 1,823 → 10 | 12,383 → 940 |
| Total key lookups | 18,692 → 18,692 | 88,737 → 88,737 |
| Chunks | 43 → 203 | 198 → 417 |
| Successful completion headers | 55 → 785 | 83 → 2,560 |
| Winner comparisons | 559 → 3,045 | 696 → 22,073 |
| Result-buffer allocations | 20 → 123 | 27 → 124 |

The four actual workers handle 391 sum-bits entries and 20,247 Raytrace-prefix
entries; respectively 1,516 and 939 execute inline on the coordinator. The
canonical reader examines 872 / 3,345 candidates and performs 949 / 2,182 field
comparisons. It allocates no candidate vector and clones no field page. These
are software operation counts, not hardware cache-miss or total allocation data.
Many new reads miss the index; this is not by itself a sparsity proof.

Expanded coverage also costs more queue/header work, grouping and winner
processing. Detailed positive and negative costs are retained in results.json.
Four new counters describe canonical lookup/candidate/field/result work. The
lookup is charged once through the existing total; the other operations enter
Bake's work ledger. Earlier serial reports did not itemize them, so the ledger
is conservative across this change and cannot be interpreted as elapsed time.
The counters add 32 bytes to each Work accumulator, not to graph facts or Cells.
QueryReads adds a borrowed backend variant, with no heap allocation.

The compiled ripsat program is checked separately: it retains all 165 direct
completions and the same total queries while gaining this query coverage. Stable
port sum-bits still uses only the existing stable reader. Neither repeated RHS
reuse nor worker coverage is credited as a newly eliminated logical query.

## Validation

94 runtime unit tests, 38 integration tests (`query_workers`, `query_receipts`,
`entry_publications`, `stable_ports`), and five work-credit tests pass. Canonical
tests cover scalar mismatches, two independent unions, hidden results, deletion
and recreation, nullary constructors, forced hash collisions, and residual
enumeration. They compare every source Run's graph and ordered bindings.

Saved sum-bits executions compare workers off, inline one and pool four, both
backends, and the compiled completion program. Saved Raytrace executions compare
only the first 128 Runs. Each group preserves the final graph, every ordered Run
record and total query calls. This is not a full Raytrace or native Raytrace
semantic proof. The required native sum-bits choice diagnosis returns pass / 0.
Minimal-feature compilation and README compile/run/bench also pass; the single
bench repetition is only a smoke check. No full performance campaign ran.

## Reproduction

Build and freeze runtime binaries from the baseline and candidate separately:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH_SUM_RUN --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_RAY_RUN 128 4 64 canonical
```

Use the saved README sum-bits 64-Cell program, and the `fast-raytrace-program`
v1 catalog identified by hash in results.json. Repeat the candidate with workers
one and off (omit runtime worker flags; use `0` for PREFIX). The stable sum group
uses `--local-congruence` instead of `--repair-ports --entry-publications`. The
completed group uses the regenerated program from cell-completion-portability.

The prefix helper now accepts an optional `canonical|stable` backend; its old
five-argument invocation still means stable. The isolated baseline checkout at
`/private/tmp/eggfuse-canonical-query-control-634d082e` changes only this helper,
so both versions execute identical bounded commands against unchanged production
code. Its Cargo target directory is isolated. Executable paths come from Cargo
JSON artifact messages before freezing; do not rely on an unrelated cached binary.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-canonical-queries/semantic out/cell-canonical-queries/semantic-acceptance.json
python3 benchmarks/cell-canonical-queries/collect.py out/cell-canonical-queries benchmarks/cell-canonical-queries/results.json
```

The collector launches no workloads. Binaries, full exports and build logs stay
under ignored out/ paths. Before a speed claim, run the complete worker/off/inline
comparison against the historical fast configuration at the agreed measurement
checkpoint; this is the fourth implementation commit in the current batch.
