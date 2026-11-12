# Lowering history-selected closures into actual execution

`bake-cell-completion --history FILE --extra-units N` now accepts completed
runtime ancestry bound to the exact input Program. It reconstructs bounded
paths from parent links (not serialized proof labels), rejects forward/cyclic
ancestry, requires increasing source Runs, and recomputes typed closure proofs.
Only repeated saturated/internal-completion paths enter selection. Additional
prefixes are charged atomically against `N` and the catalog's per-round budget;
invalid or oversized paths cannot leave a partial prefix installation.

Existing directory entries remain intact. Lowering uses the checked v5 result
switch, shared result layouts, actual retained receipts and source-ordered
union programs. Runtime visibility and liveness validation still apply. No
parallel fact graph, runtime shape construction or new per-instance binding
copy is introduced. Structural route inference outside this directory is off.
Existing typed entries may also gain direct completion when v5 is enabled;
therefore enabling the kernel and adding history routes require separate
controls.

## Actual sum-bits work

Three single-lane instrumented executions compare the original v1 directory,
v5 with **zero added paths**, and v5 with history admission (one added path).
Each passes all 1,428 saved Run graph and ordered RHS/write/resume checks.
The zero-addition configuration passes the specified native-choice semantic
acceptance; all three final states are exactly equal.

| Actual work | Original | Existing-directory v5 | Added-path v5 |
| --- | ---: | ---: | ---: |
| Direct completions | 0 | 165 | 165 |
| Legacy closed handoffs | 160 | 0 | 0 |
| Completion-frame result writes | 195 | 35 | 35 |
| Completion-frame growth bytes (cumulative) | 14,040 | 2,520 | 2,520 |
| History allocations | 485 | 320 | 320 |
| Effect frames | 4,372 | 4,207 | 4,207 |
| Effect slots initialized | 8,056 | 7,561 | 7,561 |
| History result reads | 466 | 136 | 136 |
| Constructor requests | 8,014 | 8,023 | 8,023 |
| Key lookups | 12,115 | 12,124 | 12,124 |

The new path has **no measured incremental work benefit** and is not the
selected sum-bits configuration. Most useful historical routes already existed;
their direct-completion lowering was disabled. The 165 direct completions must
not be claimed as 165 newly skipped rule applications: 160 replace an existing
closed-handoff implementation. Matching and rule-application counts do not
decrease. New costs include 1,950 direct-plan probes, 209 layout checks,
618 witness checks, 18 projection checks and 44 witness fallbacks. Constructor
and key lookups increase by nine; this cost remains charged, not hidden by the
allocation improvements. No overall speedup is claimed.

Final published-history census changes from 136 to 133 owners. Its component
figures are in `closure-execution-results.json`; this is not full runtime or
compiled-Program memory. Timing fields are deliberately excluded from the
comparison. New matching elimination, broader internal RHS injection, complete
storage/peak costs and latency admission remain future work.

## Reproduction

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics -- bake-cell-completion --program out/cell-structural-compression/baked-lean/program.json --history out/cell-structural-compression/closure-history-settled.json --extra-units 0 --output out/cell-structural-compression/closure-existing
# Repeat the compilation with --extra-units 8 and output closure-admitted for
# the additional-route control. Never overwrite an existing output directory.
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/closure-existing-work.json
# Run the same observer with baked-lean/program.json and closure-admitted/program.json.
python3 benchmarks/cell-structural-compression/analyze_closure_work.py out/cell-structural-compression/closure-baseline-work.json out/cell-structural-compression/closure-existing-work.json out/cell-structural-compression/closure-admitted-work.json benchmarks/cell-structural-compression/closure-execution-results.json
```

The real runtime integration fixture starts with an incomplete directory,
collects successful ancestry, admits a missing route, then asserts fewer
constructor requests plus exact Run graphs and ordered audits. It also rejects
foreign history, invalid ancestry, same-Run settled-union selection and excess
budgets. The full ripsat integration suite passes 17 tests.

Measurements use the actual standalone Cell runtime, not native egglog or a
simulation. The working tree's earlier uncommitted borrowed-layout change is
common to all three lanes and excluded from this commit and benefit claims.

The subsequent [publication forwarding change](publication-forwarding.md)
retains shared actual results through the existing delivery path, reducing
retired-witness fallbacks without the rejected shared-history sweep.
