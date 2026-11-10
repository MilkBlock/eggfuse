# Cell specialization and completion entry dispatch

Implementation base: `ec1b1ce6`, standalone Cell CPU (not native egglog).

## Opportunity and scope

The preceding completion check observed 165 completed sum-bits applications,
but 2,692 plan probes; the first 128 Raytrace Runs had 2,876 probes and no
completed applications. These are prior observations, not new measurements.
Compile eligibility into the selected query Entry instead of making every RHS
discover whether its state has a completion program. No runtime takeover of
dispatch is claimed by exporting this information alone.

`iterative_bake.completion.entry_dispatch` now contains eligible `(rule, pivot,
leaf)` entries, their original effect template, and their eligible switch PCs.
Unlisted entries and states select ordinary execution. A PC directly indexes
the existing `rhs_handoffs.completion_states`; no proof, operand, slot map or
runtime binding is duplicated. Its switch digest scopes IDs to this catalog.
Loading reconstructs and checks every exported field. Old artifacts without
this optional export remain supported.

Integration for the parallel executor:

1. Bind the entry's eligible states when compiling its query code. An absent
   entry needs no specialized handler.
2. Advance the existing switch with its original `(operation, leaf)` edge;
   include inherited suffix edges and the existing initial-entry fallback.
3. Select the handler using the resulting PC. Eligibility at a prior PC is not
   evidence for the next PC. Do not search the ripsat structural registry.
4. After the ordinary successful match and delta/visibility checks, execute the
   selected completion projection. Keep execution-mode, publication-layout,
   actual-frame and receipt-visibility checks. Failure retains ordinary RHS.
5. Publish at the original source Run boundary. The export authorizes neither
   worker graph mutation nor earlier visibility.

The new information does not certify static publication layout compatibility;
that check remains live. `sources`, `back`, `outputs` and composed projection
maps are already in the referenced completion program. They refer to actual
returned results, including constructors owned by another Cell.

## One executable Cell representation

The authoritative representation remains `Rule.query`, its effect `Template`,
`Site`, Entry projections and ordinary `ResultPort`/`SlotLayout`. Initial,
composed and ripsat-specialized Cells all refer to those operations. The ripsat
normalized graph is a compile-time equivalence/proof representation, not an
executable instruction set or another runtime fact store.

The existing constructor completion now lowers to `cell::CompletedPlan`.
Its projected actual results implement the same `CompletedEffects` interface
as an ordinary RHS and a single-write Cell. `complete_direct` only constructs
that view and delegates to ordinary `complete`. The separate direct-completion
history capture, delivery installation and boundary-publication loop have been
removed. Sealed publication, training and history transfer have one owner.
No new per-instance result array is introduced; the view borrows a shared
effect plan through an Rc and moves the existing Results projection once.

| Source condition | Specialization boundary |
| --- | --- |
| Constructor fact | Existing matched/completed operation and wiring provide evidence; actual returned port supplies its receipt. |
| Eq | Existing proved aliases may share slots. Unproved equality stays an ordinary condition; structural-class membership alone cannot remove it. |
| Scalar primitive | Existing query/effect primitive remains authoritative; this change adds no new scalar constant-folding pass. |
| Mutable read | Existing table query and lifecycle checks remain; no cross-Run reuse is inferred merely from equal normalized shapes. |

This implements the existing finite constructor completion subset. It does
not add general extraction of executable programs from arbitrary ripsat
eclasses, or a new specialization engine for scalar and mutable operations.
Opaque source contracts and unsupported cases keep their original operations.

## Iterative Bake

Entry dispatch is generated inside `state_plan::completion`, so both offline
`bake-cell-completion` and every `iterate --objective ripsat-completion` trial
regenerate it from the current checked catalog. `rounds.json` reports eligible
entry/state counts as static coverage, explicitly not saved work.

Iteration is useful to learn additional executed cross-stage chains and rank
them by work removed. It is unnecessary to route already-proved states.
Training remains based on completed RHS applications; candidate acceptance
retains the existing ordered-input, write, resume and per-Run audits. No new
runtime apply log or reverse dependency list is added.

## Validation and accounting

Compared with the base, there is one shared publication implementation instead
of two. The short retained-chain fixture exports one eligible entry/state.
This is structural coverage, not latency evidence. The runtime still performs
generic completion probing until the parallel branch consumes the export.
Shared publication counters now also include successful projected Cells; they
must not be added again to ripsat-completed counts when estimating savings.

Tests check every exported state against the proven program, reject corrupt
dispatch/default/checks/digest, and accept legacy artifacts. Existing completion
tests compare every Run graph, ordered RHS inputs, writes and resumptions,
including foreign results, union, deletion and composed projections.

Smoke commands use README compile/run/bench with the short
`tools/cell-compiler/tests/fixtures/history-retention.egg` fixture and one bench
repetition. No Raytrace timing campaign or speedup claim accompanies this change.

Checks completed: 88 runtime unit tests; 4 completion integration tests; 10
Entry-publication, 8 worker, 5 state-inheritance and 1 joint-result tests. The
README short compile/run/bench commands passed. A short iterative run with
`--rounds 3 --max-depth 4 --max-nodes 8 --min-support 1 --score static` grew the
catalog from 3 to 4 to 5 Cells. Eligible entry/state counts were 0/0, 0/0, 1/1;
each round preserved the existing graph/schedule/ordered-effect audit. This is
a functionality check, not evidence that static admission is profitable.

The required saved-export sum-bits semantic command was attempted against the
available `out/cell-unification` exports in the neighboring worktree. It
returned **inconclusive / 2** because `native-legacy.json` was missing. No
exclusions or proof rules were changed, and this is not recorded as a semantic
pass. The per-Run fixture checks above are separate regression evidence.

Reproduce the focused checks:

```sh
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells --test ripsat_completion --test joint_results --test state_inheritance --test query_workers --test entry_publications
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake --example emit_cell_retention -- out/completion-entry-dispatch
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/completion-entry-dispatch/fixture-chain/program.json --output out/completion-entry-dispatch/iteration-deep --objective ripsat-completion --rounds 3 --max-depth 4 --max-nodes 8 --min-support 1 --score static
```
