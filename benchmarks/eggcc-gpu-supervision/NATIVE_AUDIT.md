# Native Cell Eq supervision

The native `proof_audit` module reuses the actual CPU Cell Graph before and after
source Runs. Template input sorts compile the candidate pair layout once. The
observer retains Eq identities and pre-Run roots, not a second set of bindings
or constructor facts. Boundary roots come from the authoritative Graph. Root
reads are memoized per Run; pending storage is reused. Outstanding completion or
missing input ports makes the frame incomplete, never a pass.

Owned frames can be checked off-thread after the CPU advances. Packets identify
program, execution, Run and epoch; the complete-output contract includes empty
Runs. Duplicate, unknown and stale claims are rejected; both extra and omitted
Eq claims produce local corrections. Replay uses execution tag zero explicitly.
No GPU claim is committed and corrections are not yet applied to GPU state.

## Actual full sum-bits replay

`native-audit-results.json` records one dev/unoptimized run, not a speed benchmark:
1,428 Runs, 7,265 bindings, 30,736 Eq ports, 17,526 initially unequal candidate
pairs, 518 new equalities. Every outcome exactly matches the saved observer.
All source Run controls and final graph match ordinary execution of this runtime.

CPU execution with observer and frame construction: 190.03 ms; ordinary CPU
execution: 180.68 ms. Instrumented capture + finish: 12.13 ms (included in the
190.03 ms); proposal check: 6.92 ms (additional). Setup is reported separately.
These single samples do not establish an overhead ratio. The old Python closure
had a different proof-coverage task; its 35.7 s is not a like-for-like denominator.

Actual Metal context-ridge predictions are rejected: TP 404, FP 5,903, FN 114,
invalid addresses 0. Wrong pairs are 34.33% of candidates across all splits;
held-out test: TP 6, FP 617, FN 0 out of 1,409 candidates. Training rows are
included only in the aggregate, not presented as generalization. Native auditing
identifies the same errors using the executing graph rather than a Python closure.

This does **not** verify all token contents: scalar values, new constructor
outputs, mutable effects and visibility still need contracts. CPU still executes
the original program in full. It is a native Eq supervisor, not the final
proof-only auditor or an autonomous GPU runtime. Same-runtime comparisons do not
replace `choice_diagnosis.py` or establish native egglog equivalence.

## Reproduction

Use the full program and relation trace described in this directory's README.
`PYTHON` below is the environment with NumPy and MLX.

```sh
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false cargo test --locked -p eggfuse-cell-compiler --test proof_audit --test cell_binding_observer
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false cargo build --locked -p eggfuse-cell-compiler --example native_proof_audit
$PYTHON benchmarks/eggcc-gpu-supervision/context_ridge.py TRACE RIDGE_RESULTS --proposals PROPOSALS
# Exit 1 is expected for these inaccurate GPU predictions; output is still saved.
target/debug/examples/native_proof_audit PROGRAM AUDIT_RESULTS PROPOSALS
python3 benchmarks/eggcc-gpu-supervision/native_audit_report.py TRACE AUDIT_RESULTS SUMMARY
```

Omitting PROPOSALS generates exact checker controls, explicitly labeled as such.
Tests cover changed Run relations, graph/snapshot preservation, missing and false
claims, duplicates, unknown addresses, stale metadata, missing slots and checking
an owned frame on another thread.

The scheduled block-switch opportunity remains avoiding repeated CPU rule
execution using verified Cell evidence. This change removes Python shadow-graph
construction from Eq verification only; it discharges no CPU Run, query, RHS or
repair work. Such work cannot yet be counted as saved. No multithread branch merge
is necessary for this read-only interface.
