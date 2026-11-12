# Retire completed execution scratch from Cell state

The old completed-state plan retained every operand/destination of every RHS
operation, then only discarded unused matched inputs. A scalar temporary or
union/hide-only operand could therefore survive long after its effect finished.
This was execution state, not a fact needed by a later Cell.

The opt-in parent-takeover path now derives a completed projection from future
readers: all table-operation recipe columns/results, Set keys/values, and existing
cross-stage producer projections. It recursively retains lazy Copy sources and
static actual-result aliases. Completed primitive arguments and equality/
visibility-only inputs are not roots. Both matched inputs and computed slots can
retire, using the existing slot array and lifecycle hooks after result capture.
No duplicate fact graph, binding map or reverse consumer list is added.

Conservatively, all table-operation recipes remain roots, even when the current
instance did not create that fact: retained children can still read deleted
parent recipe columns. Mutable reads and writer output state remain covered.
Constructor aliases must retain the actual query result instead of falling back
to the synthetic `(Cell, result slot)` identity. Incomplete executions do not use
this retirement plan. The same live projection controls parent detachment.

On the current sum-bits catalog (actual standalone runtime):

| Retained state | Before | After |
| --- | ---: | ---: |
| Explicit Cell slots | 8,354 | 7,482 |
| Cell slot arrays | 218,592 B | 197,640 B |
| Writer storage subtotal | 134,360 B | 132,488 B |
| Complete Graph requested heap | 2,682,261 B | 2,659,437 B |
| Complete Program requested heap | 117,310,933 B | 117,318,509 B |

Graph heap falls 22,824 B (0.85%); larger compiled discard lists cost 7,576 B,
leaving **15,248 B net**. This retires 872 retained Cell fields, not just spare
capacity. Cumulative dead-slot removals rise 4,411→5,375. Seven additional frames
need compaction; no per-effect consumer/index maintenance is introduced.

Facts, source frame counts, workload parent links (216), completed-owner frames
(787), RHS requests and other Graph operation counters remain unchanged. The new
serial/two-worker scalar-chain regression does demonstrate removing a parent
hold after its scalar operand has been consumed, while later fact reads still
work after deleting that parent; that opportunity does not change the sum-bits
parent count. This is useful cleanup, not the requested large physical takeover.

Process requested-heap peak falls 125,458,209→125,443,265 B and growth above setup
falls 5,634,875→5,612,363 B. These are not Graph-only peaks or RSS; setup includes
the compiler layouts and path-dependent diagnostic allocations. Takeover extra
peak remains 49,576 B. No latency claim.

All 1,428 saved Run graph and ordered RHS/write/resume hashes pass. Final state
matches the saved reviewed semantic export exactly; choice diagnosis passes.
38 ownership tests and 23 ripsat-completion tests pass, including later reads,
union/deletion, worker boundaries, actual-result aliases and parent restoration.
The artifact itself is unchanged; behavior remains under the existing opt-in
completed-parent takeover configuration.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/completed-live-audit.json --natural --shared-owners --parent-takeover --port-domains-only
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/completed-live-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_completed_live.py out/cell-structural-compression/domain-classes-derived-audit.json out/cell-structural-compression/completed-live-audit.json out/cell-structural-compression/domain-classes-derived-heap.json out/cell-structural-compression/completed-live-heap.json benchmarks/cell-structural-compression/completed-live-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/completed-live-semantic.json
```
