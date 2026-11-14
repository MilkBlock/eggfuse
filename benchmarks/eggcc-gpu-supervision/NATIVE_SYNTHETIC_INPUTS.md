# Native execution of synthetic Cell inputs

Training inputs remain randomized, rule-derived structures. Real Eggcc Run
values are not used by this adapter. `synthetic_native_source.py INPUT OUTPUT`
replays the synthetic generator's validation and emits a native `.egg` program.
Pass `--schedule FILE` for multi-stage inputs; original stage order is explicit.

Compile the emitted source using `cargo cell-compile --source OUTPUT --output DIR`
(README workflow), then execute the existing `capture_rhs_results` example with
`DIR/program.json DIR/trace.json --snapshot-runs=0`. The observer exports actual
matched inputs and RHS results. It does not turn logical matches into committed
mutations. No native runtime or GPU inference code is changed here.

`audit_native_synthetic.py INPUT TRACE SOURCE REPORT [--schedule FILE]` checks
source replay, native audit flags and exact projected final facts against the
independent local reference. Private `SyntheticSeed_SORT(i64)` constructors name
open input ports; those anchors alone are excluded, and every anchor is checked.
Top-level `let` names are deliberately avoided because they create extra tables.
This migration check is not the sum-bits acceptance contract. It does not
cryptographically link the provided source to the captured executable: retain
the compiler artifacts and trace program hash when reproducing results.

Scope: immutable constructors, Eq, copy, constructor set, exact i64 literals;
unsupported operations fail explicitly. This is not broad primitive support,
a bounded batched exporter, or a GPU token-generation implementation.

## First check

Synthetic Get/SubTuple input seed 20261500 (rules 145 and 139): 12 projected
facts equal, six input anchors, two Runs on both paths. Native per-Run graph,
binding audit and Run-control checks all pass. Three unit tests also exercise
schedule rendering, absence of global alias tables, missing facts, failed native
audits and corrupt anchors. No performance claim.

Artifacts on this machine:
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/native-synthetic-subtuple-v2/`.
Used pre-existing compiler/capture binaries under the same root's `cargo-target`;
these were not rebuilt from the currently dirty Rust workspace. Large traces
and binaries are not committed.

The intended data flow is synthetic input -> Eggfuse actual execution/context
capture -> training examples -> ridge fitting -> GPU inference. The local Python
reference is a migration cross-check, not a second production execution engine.
