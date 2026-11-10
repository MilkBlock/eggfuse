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

## Equivalent-route recognition

After integrating `c1ffd8ef` and `14d1d8c0` at `3dfb684d`, exact equivalent
derivations can inherit an already-proved local completion route. This lowers
into the same `CompletedPlan` and shared publication path. Oversized projections
keep ordinary execution; identical executable programs share immutable storage.

The next compiler change replaces per-transition whole-catalog scans with one
temporary index keyed by normalized structure, constructor table and output
ports. It borrows the canonical structures; it is dropped before runtime.
Candidate order and the last matching final-stage output preference remain
unchanged, as do composition limits, exact typed terminal proof and fallback.
This discharges repeated candidate/port discovery during Bake, not a Run's
remaining receipt checks or repair obligations.

In the opposite-construction-order regression, the old loop visited four
catalog positions; the index visits only the two equivalent output sources,
performs one new terminal proof and admits the same one route. The existing
test verifies that only the alternative producer has run when that consumer
actually completes, with exact Run/effect parity. `completion_search` records
index entries, route probes, candidate visits, proof checks and admissions for
that compilation. Building/storing this temporary index is added compiler work;
these counts do not establish wall-time or runtime savings. No new execution
observations are fabricated from the inferred route.

Early v1 completion contracts without the transition census remain loadable;
present transition contracts are checked exactly, as are all executable switch
programs and entry-dispatch proofs.

## Iterative Bake

### Recognition from actual Cell history

For `ripsat-completion`, each round now builds `cell-egraph.json` **after**
training execution, from completed cursor history rather than the entire
static catalog. The matching `cell-history.json` retains logical execution
events, parent event indices, rule/pivot, source output position, producer and
consumer Runs, and the witness observed at the boundary. A witness is historical
provenance, not a current-liveness proof or a physical ownership claim.

Root executions are recorded after successful RHS completion and root seeding;
resumed executions extend the parent's event chain. Cloned cursors share their
parent event, so forks remain explicit. A failed RHS records no completion.
The existing training sample window carries the event index; ordinary inference
does not allocate this trace, and no second binding or runtime fact graph is
maintained. Training adds event storage and one index per retained sample.

The trace budget is `candidates * min(depth, nodes)` events. Collection stops
at that budget and reports dropped events. Truncated parents are explicit;
the bounded sample window is not described as full-program tracing. This
covers existing eligible Cell cursors, not every residual match or physical
mutation. Identical observed paths share an implementation, with `event_units`
mapping each execution back to it. To recover one execution's cross-stage trace,
follow `events[id].parent`; to collect a Cell's histories, select its event-unit
indices first. These are offline operations on the export.

The existing bounded `Training.pairs` table continues collecting after raw
trace capacity is exhausted. Recognition also consumes these successful
applications, exported separately as `sampled_applications`; it does not invent
missing parent links. Each retained shape stores its latest actual boundary
sample in the existing evidence fields. `retained_support` is a bounded counter
subject to pruning, not an exact execution frequency; `pair_counter_prunes`
reports pruning. The compiler checks composition against the authoritative
source operations before registering a sampled path. No extra runtime bindings
or consumer lists are introduced.

A short actual Cell runtime sum-bits replay (rounds=0, local congruence enabled)
retained 2,048 raw events and reported 380 drops across 1,428 Runs. Raw events
ended at Run 1,220; 39 retained pair samples included two later samples, up to
Run 1,223. Registering these samples increased observed path implementations
from 111 to 121 and native eclasses from 109 to 119. This does not recover the
full dropped history. Final state, schedule, ordered RHS, writes and resumes
hashes matched the preceding implementation. This is a coverage check, not a
speed measurement or native egglog semantic acceptance.

The native ripsat registry receives normalized structures of those executed
paths and their observed prefix transitions. Measured inferred-route candidates
start from actual cross-Run parent/consumer applications in that trace or the
existing bounded successful-pair samples,
including applications not already present as joins in the executable catalog.
Observing two source implementations alone does not authorize an expansion;
there must be an observed application to recognize and specialize. Source
implementations outside those observations are not normalized for this search. With no
observed applications, Bake builds no recognition index.

Equivalence may generalize an observed route to another observed implementation;
typed completion proof, exact output incidence and measured admission still
apply. Candidate routes remain predictions, never fabricated trace events.
Extension provenance records `origin: completed-runtime-history` and whether
the proposed application itself occurred (`observed_application`). That is
distinct from a predicted equivalent route and from a committed mutation.
Explicit static/offline expansion remains available as a separate policy.

The short retained-chain check records 6 executions, 4 cross-Run parent edges,
5 path implementations and 4 native eclasses, with no dropped events. Two
independent chains remain distinguishable (`0→2→4` and `1→3→5`) even though
their structures share classes. Tests cover failed RHS exclusion, fork ancestry,
capacity loss, disabled inference collection, observed-only expansion, and
the mapping of exported histories into the native registry. These are history
and semantic checks, not performance measurements.

Measured admission now separates lowering from structural expansion. The
baseline is lowered with `emit_existing_ripsat_handoffs`, which cannot add
joins. Observed join proposals may carry inferred equivalent routes and are
scored as one complete catalog; a standalone equivalent-route proposal also
competes when no new observed join exists. Rejected proposals never modify
the baseline. Empty expansions do not trigger a baseline replay.

The winning Program is retained, not reconstructed from just its initiating
join. The next round reuses its exact artifact, and the round credit records
`selected_program_sha256`. This prevents another implicit expansion between
measurement and admission, and avoids recompiling the winning artifact. The
source Run, ordered RHS/write/resume checks still run before scoring and on the
following training round. `--score static` retains the prior bounded expansion
policy and does not imply measured profitability.

The opposite-order producer regression now exercises both measured outcomes
with the same source and no new observed proposal (support threshold 1,000,000).
With local congruence disabled, the inferred route scores −6 and is rejected;
with it enabled, it scores +23 and is accepted. The accepted trial hash equals
both the next round's source artifact hash and final output hash. Zero rounds
leave the four-unit baseline unchanged in both configurations. These are
equal-weight operation scores on a small standalone CPU fixture, not timing
measurements or native egglog performance. Scalar/visibility proof rules are
unchanged. The query-receipt and completion integration suites pass (12 tests).

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

### Reusing measured candidate executions

An observed join proposal and an inferred equivalent-route proposal can lower
to the same executable catalog. Measured Bake now compares complete compiled
artifacts after removing only the root artifact checksum and the compile-only
`completion_search` / `completion_extensions` annotations. Comparison is exact
JSON equality, not normalized Cell equivalence or a Bloom-filter decision.
Every operation, slot layout, proof, execution entry and ordering stays in the
comparison. The first audited artifact is retained unchanged as the winner.

`duplicate_executable_proposals` reports avoided candidate replays; the trial
limit counts actual distinct replays, and `untried_ranked_proposals` counts
remaining proposals. This uses temporary compiler-side copies bounded by the
trial limit; it adds no inference state. Compilation of duplicate proposals
still happens before equality can be established.

The alternative-producer regression with support=1 previously replayed two
candidates with identical work, despite their different artifact checksums.
It now replays one and skips one. Both local-congruence configurations retain
the previous admission decision (−6 rejected, +23 accepted, equal-weight work
counts). Exact winning-artifact inheritance and Run-boundary audits remain
checked. This saves offline replay work; it is not an inference speedup claim.
