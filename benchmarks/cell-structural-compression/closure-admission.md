# Admit a new closure only when its lowered transfer differs

The saved sum-bits history contains 57 `internal_completion` events across five
paths, all with exactly one introduced symbolic fact. Consumer rule 55 accounts
for 41, rule 58 for 14, and rule 420 for 2. Rule 55's repeated `Single` constructor
is already a source-query alias; the outstanding operation is `Get`. The other
two consumers introduce `Add-Gets` and `ExprIsResolved`. These symbolic facts
are required effects, not proved fresh allocations. This cohort alone does not
justify claiming that an incremental RHS path would remove substantial repeated
constructor work. Dispatch and binding opportunities require separate evidence.

The prior history admission added a four-stage path
`143 -> 137 -> 143 -> 137`, supported by two actual events. The measured trial
had no extra runtime work saving. Its terminal completion was already supplied
by the existing shorter suffix.

## Compiler change

For a proposed batch of new prefixes, Bake lowers the current directory and the
trial directory with the same checked completion policy. It replays the actual
path through both switches, including their existing suffix fallback, then
compares:

- the terminal query/RHS reuse program and its lowered ports;
- captured results, retained history depth and inherited slot layout;
- the direct-completion plan, output sources, projections and lazy union code.

An identical terminal transfer does not spend another Cell budget. Existing
states are preserved. A batch needed to reach a *different* terminal transfer
can still introduce intermediate prefixes. This is an immediate-work admission
rule, not whole-automaton equivalence, full semantic canonicalization, or proof
that a rejected path can never help future compositions. Such a future longer
path can be proposed and checked as an atomic batch.

Compilation is lazy: the additional comparison lowerings run only for a proposed
new path within budget. Zero-addition admission does not do them. The final
catalog limit grows only to accommodate actually admitted units, not rejected
budget capacity. `admission_lowerings` and `redundant_terminal_transfers` report
these costs and decisions; neither earns runtime work credit.

## Offline result

Using the same saved, source-bound trace and budget of eight:

- new units: **1 -> 0**; existing 64-unit directory remains intact;
- direct-completion states: **8 -> 7**, matching the effective zero-addition lane;
- additional comparison lowerings: **2**;
- no workload execution or speed measurement was needed.

The regenerated artifact equals the already executed effective directory except
for `/sha256`, `/iterative_bake/closure_selection`, and the rebuilt
`/ownership_fragments/source` provenance digest. The compiler's `apply_plan`
revalidates the final artifact with `Program::parse`; the analysis refuses any
other difference. This is not an exclusion added to semantic acceptance. Runtime
validation and semantic evidence for that execution configuration remain in
[publication-forwarding.md](publication-forwarding.md).

All 18 ripsat integration tests pass. The new regression uses explicitly
synthetic ancestry to check that a useful missing three-stage transfer is still
admitted while a redundant four-stage completion is rejected. The existing
actual-history fixture still proves fewer constructor requests and exact Run
and ordered-effect equality after a useful admission.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics -- bake-cell-completion --program out/cell-structural-compression/baked-lean/program.json --history out/cell-structural-compression/closure-history-settled.json --extra-units 8 --output out/cell-structural-compression/closure-transfer-admission-final
python3 benchmarks/cell-structural-compression/analyze_closure_admission.py out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/closure-admitted/program.json out/cell-structural-compression/closure-transfer-admission-final/program.json out/cell-structural-compression/closure-history-settled.json benchmarks/cell-structural-compression/closure-admission-results.json
```

This removes a demonstrated duplicate admission, not the remaining query/RHS
work. Broader saturated-state execution and cross-stage matching elimination
remain part of the active objective.
