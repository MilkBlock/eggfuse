# Share settled state without erasing the continuation interface

## Opportunity from the last catalog

The existing archive contains 4,920 actual standalone Cell runtime completion
observations, zero archive drops, and 117 explicit missing-parent boundaries.
It passed all 1,428 saved Run graph and ordered effect checks. This experiment
reuses that archive and performs compiler analysis only, not a workload rerun.

The existing `completion_contracts` describe ordered execution paths. They must
preserve pending unions and source stage boundaries. Those contracts are not
necessarily a canonical representation of the state after all those Runs have
completed. Treating their classes as completed-state identity hides reuse.

`describe_settled_path` now exposes the existing typed normalization with all
source unions settled. It returns the same constructor structure and operation
port maps used by the compiler, with an explicit all-source-Runs-completed
requirement. It is compile-only; no runtime registry, bindings or fact graph
were added. It does not change the versioned executable contract.

## Evidence

| Actual saturated extensions | Count |
| --- | ---: |
| Typed locally saturated events | 163 |
| Same old ordered class as parent | 1 |
| Same settled constructor structure as parent | 154 |
| Also exact source-path extension and strictly later source Runs | 154 |
| Also identical inherited operation port maps | 154 |

The 154 consist of 140 `143 -> 137`, eight `137 -> 143`, five `143 -> 143`,
and one `103 -> 103`. The other nine saturated extensions have no equal
supported settled parent class in this archive; they are not folded.

This is stronger than finding equal result hashes: the exact compiler structure
includes input assumptions, typed colors and completed constructor facts. Every
prefix Run required by the saturation certificate is checked against actual
ancestry. An opaque/unsupported state is never equal to another merely because
both are unsupported. Tests also confirm that settling constructor Set makes
previously different G keys congruent, but does not invent a missing G fact.

Hypothetically folding these edges changes recorded depth counts:

| Depth | Original | With equal settled edges folded |
| --- | ---: | ---: |
| 1 | 3,609 | 3,683 |
| 2 | 975 | 998 |
| 3 | 257 | 169 |
| 4 | 70 | 61 |
| 5 | 9 | 9 |

This is a diagnostic upper opportunity for history simplification, **not** an
implemented cursor rewrite. It does not count removable frames, facts or bytes.
The deepest chains remain unchanged, so this evidence alone cannot support a
large whole-egraph compression claim. Only 161 of the 458 observed source units
have a supported settled structure (148 classes); unsupported units remain an
explicit coverage limit.

## Follow-up: most candidate sharing already exists

The [actual capture audit](settled-capture.md) supersedes the proposed next
implementation below: 153 of the 154 events already have direct plans, and 134
already allocate no capture owner. Ordered-state inequality must not be treated
as evidence of duplicated runtime state. The remaining ownership costs need
separate analysis before adding a sharing mechanism.

## Original implementation hypothesis (now qualified by the audit)

Keep execution position and settled-state identity separate. A saturated step
may retain the parent's completed state and actual results while installing the
consumer's continuation interface, instead of creating another history owner
solely because the ordered source path grew. Its result port projection must be
compiled from the operation maps, not inferred from a producer operation address.

A scheduled switch may discharge the covered completed constructor work after
source repair, but it cannot advance publication or erase delta obligations.
The switch must retain the consumer Entry, actual returned witnesses, retirement
checks, pending external effects and the correct outgoing transition routing.
Even identical inherited symbolic port maps do not prove two runtime witnesses
have the same lifetime. Existing completion work must not be credited twice.

The next runtime change should target this state/continuation separation, with
owner allocations and peak live state as acceptance metrics. Enlarging the path
catalog without this separation risks retaining the same state under more
history owners.

## Reproduction and validation

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example review_settled_history -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/root-history-full.json out/cell-structural-compression/settled-history.json
python3 benchmarks/cell-structural-compression/analyze_settled_history.py out/cell-structural-compression/root-history-full.json out/cell-structural-compression/settled-history.json benchmarks/cell-structural-compression/settled-history-results.json
python3 -m unittest discover -s benchmarks/cell-structural-compression -p test_settled_history.py
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test ripsat_completion
```

No runtime execution path changed; no new timing, heap result or semantic
acceptance is claimed. Original archive validation remains historical evidence.
