# Delegate completed bindings before physical owner grouping

## Opportunity and remaining obligations

The accepted configuration delegated redundant Eq slots only when several
completed frames qualified for physical owner transfer. Completed frames that
remained in ordinary storage kept bindings already supplied by their existing
component ports. The saved source census contained 4,543 explicit Eq slots in
completed ordinary frames; this was an opportunity count, not proof that every
slot had a live matching port.

At successful Cell completion, after result capture and dead-slot retirement,
the opt-in completed-state path now checks each eligible bound Eq slot against
the existing template port. Only equal canonical values are delegated. Scalar,
unbound and unequal fields retain ordinary storage. No new binding store,
reverse index, owner or per-instance layout is created. The existing symbolic
slot reader and component-retirement restoration remain authoritative.

An empty completed liveness plan now means enabled with no dead slots; None
continues to mean disabled. This allows a completed rule with no dead operands
to delegate already represented live fields. Temporary frames with no facts or
retained users still skip compaction before destruction. Writer handling is
unchanged. Source Runs, delta ownership, result receipts and FactRef identities
are preserved.

## Actual standalone Cell runtime result

Same program artifact, owner catalog, query classes and domain-only index mode;
no new Bake directory or workload timing campaign.

| Metric | Before | After |
| --- | ---: | ---: |
| Final explicit Cell slots | 7,482 | 5,740 |
| Cell slot-array bytes | 197,640 | 155,520 |
| Complete Graph requested heap | 2,659,437 B | 2,617,317 B |
| Complete retained Program heap | 117,318,509 B | 117,318,509 B |
| Live source-frame descriptors | 2,385 | 2,385 |
| Parent links | 216 | 216 |
| Execution/takeover process peak | 125,443,265 B | 125,400,997 B |
| Maximum takeover extra peak | 49,576 B | 50,320 B |

Final explicit slots fall by 1,742 (23.3%); complete Graph heap falls by
42,120 B (1.58%). The array-byte change includes capacity differences, so it
must not be divided by final slot count to infer the Value size. Program storage
is unchanged. Fact counts, source-frame count and writer storage are unchanged.
This is actual redundant-field removal, **not** large whole-egraph compression.

New runtime work is explicit: 4,813 completion-point Eq comparisons, all allowing
a slot to be removed on this workload. Those are cumulative removals, not the
final live reduction. The later shared-owner path's delegated-slot counter falls
from 2,260 to zero because the same work has moved earlier; these 2,260 must not
be claimed again as additional savings. Shared-owner inherited-frame counts
increase because those frames now arrive already using symbolic fields.
All other Graph work counters remain unchanged. No timing improvement is claimed.

## Verification

All 39 ownership integration tests pass. A new serial/two-worker regression
checks delegation without any physical completed-owner transfer, later source
Runs reading the resulting facts, and deletion. Existing coverage checks foreign
actual results and restoring a retained parent's fields when its component dies.

The actual diagnostic execution matches all 1,428 saved Run graph and ordered
RHS/write/resume checks. Final export exactly equals the saved semantic input;
`choice_diagnosis.py` returns pass/exit 0. The allocation lane has the same final
state digest. This is the standalone Cell executor, not native egglog or RSS.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test cell_ownership
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/completed-symbolic-audit.json --natural --shared-owners --parent-takeover --port-domains-only
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/completed-symbolic-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_symbolic_completion.py out/cell-structural-compression/completed-live-audit.json out/cell-structural-compression/completed-symbolic-audit.json out/cell-structural-compression/completed-live-heap.json out/cell-structural-compression/completed-symbolic-heap.json benchmarks/cell-structural-compression/completed-symbolic-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/completed-symbolic-semantic.json
```
