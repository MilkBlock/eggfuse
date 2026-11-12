# A supported suffix is not necessarily a new dispatch opportunity

The full-history batch added `137 -> 143`, supported by nine completed paths,
but actual direct completions stayed at 183 and plan checks at 209. Offline
replay explains why: all nine events already pass through `143 -> 137 -> 143`,
whose installed unit is 46. One also has an earlier uncompiled producer 57.
The longer compiled Cell already selects the transfer. Comparing the proposed
suffix in isolation incorrectly treated it as additional runtime coverage.

## Change

History admission still requires typed source closure proofs and checks the
isolated terminal transfer. It now also replays actual event ancestry through
the current and proposed switches. If every supporting event still selects the
same terminal program, result sources, retained layout and direct plan, the
proposal does not spend an additional unit. This is profile-guided admission,
not proof of global equivalence or permanent domination. A later history or a
longer combined proposal can admit the route again. Missing ancestry is never
reconstructed from marginal pair support.

The replay follows parent event IDs, not catalog unit numbers. This matters when
adding producer roots rebases portable catalog IDs. The example compares source
recipes and requires the audited trace to belong to its baseline. It reports any
failure to reproduce the originally recorded unit before interpreting changes.
All replay structures are compile/diagnostic data; no runtime fact graph or
consumer subscription list is added.

## Evidence

- All 4,920 recorded baseline unit selections reproduced exactly, including
  uncompiled roots and the existing missing-parent boundaries.
- Full-batch direct-plan opportunities are 209 before and after; this equals
  the measured plan checks, but replay itself does not validate live witnesses.
- 173 event transfers change: 146 producer-60 roots, 23 rule-143 continuations,
  and four rule-137 continuations. This explains why substantial capture costs
  can appear without any new full completion.
- New admission rejects the nine-support saturated suffix and adds two units
  instead of three. The remaining producer-60 pair is still an experiment with
  demonstrated retention overhead, not a promoted optimization.
- 143 runtime unit tests and 19 ripsat integration tests pass. The synthetic
  saturation regression now checks both a useful missing longer completion and
  a short suffix already covered by actual longer ancestry.

No new workload execution or speed test was needed. This compiler change does
not claim a runtime memory reduction. The prior batch's exact 1,428 Run and
semantic acceptance remains its own evidence; it is not a new execution of the
two-unit artifact.

## Reproduction

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example history_dispatch -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/full-history-admission/program.json out/cell-structural-compression/root-history-full.json out/cell-structural-compression/history-dispatch.json
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics -- bake-cell-completion --program out/cell-structural-compression/closure-existing/program.json --history out/cell-structural-compression/root-history-full.json --extra-units 8 --output out/cell-structural-compression/actual-ancestry-admission
python3 benchmarks/cell-structural-compression/analyze_dispatch.py out/cell-structural-compression/root-history-full.json out/cell-structural-compression/history-dispatch.json out/cell-structural-compression/actual-ancestry-admission/program.json benchmarks/cell-structural-compression/actual-ancestry-results.json
```

Before enabling more root captures, establish whether the required query witness
already survives in the actual instance. `Instance.known` is transient matching
state; its presence during execution does not establish persistent storage after
publication. Copying it into a new history owner is exactly the cost under study.
