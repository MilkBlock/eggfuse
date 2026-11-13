# Cell CPU toolchain

`cargo cell-compile` accepts a named workload or a flat egglog source. It rewrites structural keys, analyzes a training schedule, selects structural markers, lowers the marked source and validates the CPU artifact. Training and target declarations and rules are checked for compatibility. Compilation publishes into a fresh directory after validation.

`--bake-source FILE` supplies a separate training input for a custom source. `--profile FILE` and `--marker-locality identity|all` control offline marker selection. An optional `--catalog FILE` attaches recipe-bound Spine blocks, iterative transitions and admitted query contexts after lowering. The catalog's recipe hash and each executable component are checked. Changes to marker selection can produce a different recipe; supply a matching catalog in that case.

`--marker-handoff values` rewrites the generated `.egg` to forward permanent
constructor results already bound by a marker. Consumers use those variables
directly, and producers capture actual results for marker publication. Residual
conditions and source Run boundaries remain live. The default `legacy` preserves
the frozen suite recipes; a values-mode artifact requires its own matching
catalog. Static substitution counts in `marker-selection.json/result_handoff`
are compiler diagnostics, not measured runtime savings.

`--marker-receipts omit` suppresses the generator's diagnostic `CellSpineApplied`
tables and writes. Query markers and ordinary Cell definitions remain. The default
is `materialized`, which preserves apply-history exports and the old receipt-based
continuation report. Omission changes the compiled recipe, so an old catalog must
not be reused unless its recipe check succeeds. This is generation-time selection,
not deletion of tables from an existing runtime. See
[the proof boundary and validation](../../benchmarks/cell-bake-owner-merge/application-receipts.md).

`cargo cell-run --program FILE --output DIR` executes the complete source schedule and writes `state.json` and `report.json`. The report separates inference from setup and export. For small inputs, `--audit-stages` saves every logical graph and binding snapshot. `--inspect-program` validates an artifact and reports its admitted context plans.

`cargo cell-bench --program FILE --repeat N` starts a fresh graph for each repetition, checks the final graph digest and reports inference samples and their median. It can also compile `--source FILE` or `--case NAME` before the timed runs. `--reference-program FILE` adds per-Run comparison before timing. `--lane` and `--modules` belong to the research CLI.

For ordered RHS digests and the full winning Spine prefix tree, use a separate audit process.

```sh
cargo run --release --locked -p eggfuse-cell-runtime \
  --features slot-transfer-audit,spine-shapes -- --program out/sum-bits/program.json --output out/audit
```

To learn blocks for another workload, run a training artifact with `spine-shapes` to collect observed prefixes. Create a seed using `cargo run --release --locked -p eggfuse-cell-runtime --example bake_spine_blocks -- TRAIN_PROGRAM TRAIN_SHAPES TARGET_PROGRAM NEW_PROGRAM 32`. Use `cargo cell-iterate --program NEW_PROGRAM --output out/learned --rounds 4 --objective rhs-lookups` to grow bounded adjacent units. The iterative command checks ordered RHS inputs across rounds. The separate `bake_contexts` example can transfer admission evidence from paired discovery profiles collected with the research executor.

`bake-cell-completion` compiles an existing catalog into checked ripsat completion
states without executing its workload:

```sh
cargo run --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake -- bake-cell-completion --program out/seed/program.json --output out/completed
```

Use `--objective ripsat-completion` with `cell-iterate` to recompile this proof
and charge completion dispatch/validation in each measured-work trial. Measured
Bake lowers its baseline without adding equivalent routes. Structural expansion
is a scored candidate even when no new observed join is available; the winning
complete artifact, including inferred joins, is reused unchanged next round.
Static scoring and standalone `bake-cell-completion` retain bounded expansion
without claiming measured benefit. Current
direct coverage requires an already established, constructor-only RHS whose
actual result ports come from one retained frame. Eligible Entry publication
projects those existing slots; original Run visibility and residual execution
remain authoritative. Unsupported effects and deletable results keep their
ordinary execution. This is standalone Cell CPU work, not an application
speedup claim. [Plan and acceptance](../../docs/RIPSAT_CELL_COMPLETION.md).

For conditional-template experiments, pass `--local-congruence true` to
`cell-iterate`. Both discovery and scored replays then use stable port fields,
port constructor matching and shared local conditions. `--port-keys true` and
`--stable-ports true` also select their respective prerequisite backends.
Credit records the resolved configuration; these modes cannot be combined with
local-union or repair-cell completion. Measured-work remains an uncalibrated
operation count: validate any claimed speedup separately with single-thread
timings against the same frozen artifact and the fastest control.

The frozen suite uses marked recipes produced by the compiler. Per-Run equality on this branch is measured against the prior standalone Cell CPU executor. Comparisons against native egglog require its original unmarked eggcc input.

For semantic acceptance of the reviewed sum-bits extraction contract, run
`python3 benchmarks/marker-handoff/choice_diagnosis.py ARTIFACT_ROOT OUTPUT.json`.
Accept only `pass` / exit 0; `difference` / exit 1 and `inconclusive` / exit 2
are not acceptance. See [inputs, proof rules and limits](../../benchmarks/marker-handoff/choice-diagnosis.md#default-semantic-acceptance).
Strict graph equality is a separate determinism diagnostic. Source contracts
outside the reviewed fingerprint require extending the proof; scheduling and
visibility changes still require the relevant Run-boundary checks.
