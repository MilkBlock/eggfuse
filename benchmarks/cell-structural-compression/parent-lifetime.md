# Completed-field lifetime projection: useful coverage, no storage win yet

The previous eager attempt required every matched input to have a composed symbol:
one detachment for 413 candidates and 762 field checks. The saved trace exposed
unused query-result and scalar inputs. This experiment derives the retained subset
from the authoritative Cell operations, their result positions, known-result aliases,
and cross-stage producer read columns. In particular a static constructor alias may
read a query result even when that slot is absent from instruction operands.

Only templates whose entire retained parent subset maps to existing symbols receive
a layout. Unsupported scalar/state projections are rejected before runtime probing.
After successful RHS completion, result/history capture and ordinary frame release,
the runtime verifies actual values against the existing component symbols, removes
the parent reference, and leaves ancestor GC at the original Run boundary. No copied
bindings, consumer lists, second fact graph, or speculative RHS skipping is added.
Writers and transient frames are not taken over. External reads remain conservative.

The final implementation is **opt-in under storage-metrics**, via
`Executor::use_completed_parent_takeover`. Ordinary builds have neither the new
layout field nor its execution hook. It is not enabled by default because storage
measurements below show no reduction. The layout is a prerequisite for a future
fact-owner replacement, not evidence that replacement is implemented.

## Actual standalone Cell runtime evidence

Same closure-existing program, natural lifetimes, no diagnostic per-Run compaction:

- 131 runtime candidates, 137 field checks, 128 successful detachments, 134 delegated slots.
- Final parent links: 316 (control) -> 216 (takeover).
- Both lanes: 1,746,960 counted Graph bytes at final state and boundary high-water.
- Zero Run boundaries have a counted-byte reduction.
- Same source instance/fact arities; no small Cell owner retired as a result.

The census excludes parts of the Graph heap and is not a within-Run peak or RSS.
The full audited lane preserves all 1,428 saved graph and ordered effect hashes.
Both natural-lifetime storage lanes reproduce its final-state digest; semantic
acceptance passes. Runtime tests: 147; ownership tests: 33; ripsat tests: 21.
The opt-in configuration has focused coverage for cross-Run unused inputs, required
scalars and constructor-result aliases, in serial and two-worker execution.

The full audit was taken before moving the identical algorithm behind opt-in; the
final opt-in path passes the ownership tests. The non-storage-metrics runtime also
passes cargo check. Counters now charge candidates and field checks in work_credit;
detachments are not credited as saved operations. The original audited work JSON
predates that counter-reader extension; raw graph counters are authoritative here.

## Consequence for the next structural change

Removing parent dependencies alone cannot erase live facts' Cell owners. The current
FactRef(cell,op) path still fetches a complete Cell record and its fact map. Replacing
58/143 with a completed shared Cell requires preserving those fact identities while
moving their storage and lifetime under the shared owner. The 137 tail already has
no frame and cannot be counted again. Constructor conditions, scalar i, writer
origins, external readers and the source Run schedule remain live obligations.

Do not spend more iterations maximizing detached-parent counts in isolation.
Measure distinct owners, field/fact/index bytes and execution peak when implementing
replacement, including the cost of any stable-address directory required by it.

## Reproduction

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/parent-lifetime-natural.json --natural --parent-takeover
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_parent_storage -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/parent-lifetime-natural.json out/cell-structural-compression/parent-lifetime-storage.json
```
