# Compiler/runtime agreement on Cell type identity

The full shipped sum-bits catalog exposed an artifact bug while following up
the [candidate search](../cell-candidate-sweep/README.md). The native compiler
enables `serde_json/preserve_order` transitively through `egraph-serialize`; the
independently built runtime uses sorted object maps. Completion normalization
embedded type schemas using their ordinary JSON display, so the same type
could have two different color strings. An artifact accepted and executed
inside the compiler was rejected by the standalone runtime as
`invalid ripsat completion structures`.

Type colors now use the existing canonical artifact encoding, including
recursive object-key ordering. The checker still reconstructs and compares
the complete contract. It does not ignore types, weaken equality checks, or
equate post-Union facts with entry assumptions. No runtime instance state,
queries, effect order or publication obligations change.

The regression first fails on `58a6dddf`: sorting JSON objects without changing
the canonical artifact checksum makes the completed artifact fail validation.
It passes after the fix, and a forged type color is still rejected. Existing
canonical artifacts remain usable. Old artifacts whose embedded color strings
depended on field order need proof regeneration from their original catalog;
editing just those strings is insufficient because port labeling also depends
on colors.

## Independent execution and the remaining optimization opportunity

The compiler and runtime were built in separate Cargo invocations, preventing
feature unification from hiding the bug. The old independent runtime rejects
the saved full-catalog artifact; both versions accept the regenerated artifact.
They produce identical final graphs, all 1,428 ordered Run records, and all
checked integer work/layout fields on that same program. The native sum-bits
choice acceptance script passes. These checks cover the standalone Cell CPU
implementation, not a change to native egglog.

The same canonical backend also compares the shipped 64-Cell v1 program with
its regenerated ripsat completion program:

| Work | Shipped v1 | Ripsat completion |
|---|---:|---:|
| Key lookups | 18,692 | 18,692 |
| Ordinary handoff attempts | 592 | 262 |
| History-owner allocations | 663 | 498 |
| Joint history frames | 534 | 369 |
| Query receipts copied into joint frames | 534 | 369 |
| Direct completed applications | 0 | 165 |
| Direct plan probes | 0 | 2,692 |
| Direct layout checks | 0 | 223 |
| Direct witness checks | 0 | 633 |

These are **existing completion behavior**, made independently executable by
the normalization fix; they are not new savings attributable to that fix. The
shipped catalog already reuses the relevant constructor results. The isolated
base-Cell trial's saved lookups cannot be claimed again against this baseline.
The full catalog retains a query anchor as well as effect results, so three
result slots need validation; 58 completion attempts fall back. Removing those
checks requires evidence about actual result lifetime, not just equal types.

The useful next target is repeated maintenance around these proven results,
or a different observed hot query not already handled by the existing switch.
More compositions of this same completed RHS cannot remove a query that is
already gone. This checkpoint establishes neither sparsity nor a speedup.

## Validation and reproduction

94 sparse runtime tests and 19 compiler integration tests pass (`ripsat_completion`,
`state_inheritance`, `query_receipts`). The latter include every-Run graph and
ordered effect checks on direct execution, retirement fallback and forged
proof rejection. Minimal-feature compilation and the README compile/run/bench
commands pass. Bench uses one repetition only as a smoke check.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime
# Freeze that binary before other builds. Build the old control separately.
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- bake-cell-completion --program SHIPPED_PROGRAM.json --output NEW_COMPILED_DIRECTORY
RUNTIME --program NEW_COMPILED_DIRECTORY/program.json --output NEW_RUN_DIRECTORY --repair-ports --entry-publications
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-completion-coverage/semantic out/cell-completion-coverage/semantic-acceptance.json
python3 benchmarks/cell-completion-portability/check.py out/cell-completion-coverage benchmarks/cell-completion-portability/results.json
```

The checked baseline is the previously frozen `cell-execution-state/runtime-after`:
its binary hash matches the committed evidence, and its source tree hash matches
`58a6dddf`. An initially copied local target binary had obsolete State/Entry
layouts and was discarded from comparisons. Generated artifacts and binaries
remain untracked. `old-program.json` points to the saved shipped-resume program
from the preceding experiment. The collector only inspects artifact loading
and reads saved executions; it launches no workload or speed benchmark.
