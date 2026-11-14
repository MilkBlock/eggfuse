# Diagnose growing graphs separately from boundary completion

All 20 unresolved two-Cell inputs were checked for eight explicit source Runs.
The ordinary compiler performs native Bake discovery before lowering; even an
explicit bounded source schedule did not make its search finish within the
existing two-second limit. The new `compile_local_source` compiler example uses
the existing typed frontend and runtime compiler directly, skipping Bake search.
It is a diagnostic lowering route, not a new optimized execution engine.

`diagnose_enumerated_growth.py CAPTURE OUTPUT DIRECT_COMPILER OBSERVER --runs 8`
checks original archive/input provenance, emits a bounded schedule, captures each
Run with the native runtime and compares the final facts and Eq classes against
the independent reference. All 20 native comparisons passed, including Run
control and ordered binding audits. A bound is not a saturation label.

Examples of native business fact counts (excluding private seed anchors):

- Case 187: 4 -> 6 -> 10 -> 13 -> 16 -> 19 -> 22 -> 25 -> 28.
- Case 193: 5 -> 11 -> 18 -> 24 -> 30 -> 36 -> 42 -> 48 -> 54.
- Case 227: 5 -> 7 -> 9 -> 11 -> 13 -> 15 -> 17 -> 19 -> 21.

All twenty grow at the final observed step. However, their initial boundary Eq
partitions have no changes after Run 2 within this eight-Run observation. Some
never change; others change in Runs 1 or 2. This distinguishes graph expansion
from the boundary projection that a compressed Cell may need to expose. It does
**not** prove no later boundary change or that new constructors are unobservable
to subsequent stages. The 20 remain unresolved for saturation training. Next
work requires an inductive boundary/continuation contract, not treating an
observed plateau as a fixed point.

`enumerated-growth-results.json` contains native fact counts, independently
computed changes, per-boundary partitions and compiler/observer hashes. Captures
remain in `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/enumerated-growth-direct-v1`.
The direct compiler was built with local Cargo; the current dirty workspace's
unrelated changes were preserved and are not part of this commit. A disk-full
build failure was resolved by removing only the dedicated native-source-target
incremental cache. Runtime binaries and experiment results were preserved.

The GPU labeler's synthetic provenance adapter now also accepts verified
`enumerated-cell-input/v1` documents, retaining wiring/partition provenance
instead of requiring a random seed. Four enumeration/provenance tests pass.
No GPU retraining, speed or accuracy improvement is claimed in this diagnosis.
