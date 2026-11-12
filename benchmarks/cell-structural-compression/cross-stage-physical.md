# Cross-stage logical executions and actual instance storage

The Get completion families contain 216 consumer applications. This is not 216
physical egraph nodes. Completed-history events now attach their actual execution
id and a snapshot of the registered or transient RHS frame. Missing observations
are null and must not be interpreted as empty frames. Training-only storage does
not change the runtime Cell representation or create a second maintained graph.

The snapshot is taken after successful RHS work and before source-Run repair and
frame release. It distinguishes `registered` graph Cells from transient RHS
frames via the existing `rhs_frame` accessor. A transient frame may subsequently
be released or become a writer. Writer-owned storage is **not included** in this
per-event snapshot. `non_hidden_facts` checks the stored hidden flag, not full
runtime visibility. Logical slot counts can include shared inherited storage;
they are not unique requested bytes.

## Corrected evidence

For the 45 rule-340 bundles and 27 rule-324 bundles:

| Consumer | Executions | Registered frames | Transient RHS frames | Registered fact observations |
| --- | ---: | ---: | ---: | ---: |
| 58 | 72 | 26 | 46 | 26 |
| 143 | 72 | 72 | 0 | 72 |
| 137 | 72 | 0 | 0 | 0 |

Rule 143 has four logical slots per registered frame, 288 slot observations in
this cohort. Rule 58 has 262 slot observations across its registered and transient
frames. Neither is a live peak or a sum of unique bytes. The next compression
candidate is the persistent 58/143 storage and its relation to the actual Get
Entry, rather than nonexistent 137 frames. Rule 137 still offers matching and
scheduler simplification; existing RHS/frame elimination cannot be counted twice.

None of the 72 Get witness owners equals its logical producer execution id.
Producer-340 executions have 45 transient RHS frames and no registered frames;
producer-324 executions have 11 registered and 16 transient frames. This directly
rules out using `(logical producer execution, operation)` as a universal physical
result address. Cross-stage replacement must inherit actual Entry/result sources.

An initial diagnostic inspected only `Graph.cells`; it missed transient frames.
That result is superseded and is not committed as evidence. A regression now
observes the same instance while transient, after registration, and after release.

## Validation

The corrected full trace reproduces all 1,428 saved Run graph and ordered effect
hashes, all 4,920 earlier event identities/ancestry links, and the exact earlier
final export. No capacity drops. Semantic acceptance is pass. Runtime tests: 145;
ripsat integration tests: 20. No speed or large-memory reduction is claimed.

## Reproduction

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/physical-history.json --closure-history 8192
python3 benchmarks/cell-structural-compression/analyze_cross_stage_closures.py out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/physical-history.json out/cell-structural-compression/physical-candidates.json
python3 benchmarks/cell-structural-compression/analyze_cross_stage_storage.py out/cell-structural-compression/physical-history.json out/cell-structural-compression/physical-candidates.json benchmarks/cell-structural-compression/cross-stage-physical-results.json
```

Lowering a replacement still needs source-stage order, Entry/delta eligibility,
actual-result lifetime, external consumers and mutable boundary obligations. These
measurements locate storage to target; they do not themselves discharge it.
