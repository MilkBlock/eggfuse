# Bounded device loop over explicitly covered stages

`device_stage_loop.run` combines bootstrap completion, snapshot Entry matching,
joint admission, ordered effect completion and token refresh. A device stage
cursor advances only on a quiet round with no new tokens, no executed effects,
no refreshed tokens, no query/admission failures, no pending completion, settled
Eq, complete external coverage and explicit query coverage for that stage.
Capacity failure or round-budget exhaustion cannot manufacture a fixed point.

The fixed Python round loop unrolls GPU dataflow; stage cursor decisions use
array masks. There are no host reads between rounds. Completed schedules stop
admitting matches and preserve state for remaining budget lanes. This still
computes masked work and is not claimed efficient. The controller's `finished`
means only the supplied covered stage list completed, not that it independently
proved whole-program semantics.

`compile_controls` takes existing lowering coverage, which currently has
`closure_authorized=False`. Therefore controls generated from real current
catalogs cannot advance a stage. A true coverage vector in a test is an explicit
local-family assumption; it must not be used as an inferred real-workload proof.
The controller does not perform CPU auditing, validate arbitrary supplied proof
bits, implement rollback or prove ownership transfer.

## Tests and limits

78 mechanism tests pass. A two-stage local GPU fixture produces counts
[1, 0, 1, 0, 0] with stage history [0, 0, 1, 1, -1], executes actual constructor
effects, and retains actual result IDs. It receives no intermediate CPU bindings.
The fixture explicitly assigns its compiled Entry blocks to two stages and
assumes complete enumeration of its tiny family. It does not demonstrate current
cross-stage lowering or Eggcc schedule translation. Tests also verify that real
lowering controls remain blocked after zero-new rounds, and capacity, external
boundary and budget failures prevent advancement.

The saved dot-product recipe stores its schedule under `control`, not `schedule`.
It contains nested `sequence`, `repeat` and `saturate` forms, including nested
saturation around type helpers and outer multi-ruleset saturation. Flattening
these into independent saturated rulesets changes semantics. This initial flat
controller must be extended with the actual compiled control structure and the
outer loop's accumulated change condition; it is not yet that implementation.
Original Run visibility, effect order and residual matching obligations remain.

Reference Bake tip `9ee7070d` retains only admitted executable context cuts while
preserving residual enumeration. The corresponding GPU lesson is to compile
covered control/execution blocks without falsely discarding uncovered work.
This commit adds no new instance binding graph or apply log, but it does not yet
remove the CPU runtime's full matching/scheduling path. No actual Eggcc runtime,
speedup, prediction-accuracy or ownership-completion claim is made.

## Nested source control table

`device_schedule` compiles the actual `sequence`, `repeat`, `saturate` and `run`
forms into a fixed table. Runtime control state consists of a program counter,
repeat counters and one accumulated-change flag per saturation region. Static
Run-to-region membership propagates a completed Run's change to every enclosing
saturation. Resetting an inner loop does not reset its parent's accumulated flag.
An outer saturation therefore repeats even when the last inner iteration was
unchanged but an earlier inner iteration changed state.

Repeat counts are not expanded into duplicate code. Zero repetitions skip the
body. A RUN holds its program counter until its caller supplies a completed Run;
change signals while waiting are ignored. Invalid control syntax, unknown
rulesets and invalid counters fail compilation; an invalid runtime PC is marked
and cannot report HALT. Bookkeeping uses bounded tensor masks/counters, not a
recursive GPU stack. This is a small control plane, not an attempt to express
counter state as learned floating semantics.

81 mechanism tests pass. In addition to nested saturation, tests cover repeat
zero, nested repeat, wait-state immutability and malformed controls. The real
dot-product `recipe.control` compiles to 380 instructions, 108 saturation flags,
9 repeat counters and 30 rulesets. Static arrays occupy 48,640 bytes. The audit
executes chunks of 16 controller ticks on GPU without inspecting intermediate
PC values on CPU.

Two deterministic synthetic Run policies agree exactly with an independent
recursive source-tree interpreter: always unchanged produces 909 Runs; changing
only the first Run of each ruleset produces 934 Runs. Both reach HALT. This is
control-tree evidence only: no graph or model completion is executed, and the
audit budget is derived from the reference traversal. It is not an observed
Eggcc Run-count reproduction or a saturation certificate.

Reproduce with `audit_device_schedule.py TRACE OUTPUT`; hashes and results are in
`device-schedule-results.json`. The controller's stage IDs follow the explicitly
supplied name list; an integrated runtime must align Entry plan IDs to that same
mapping. Empty rulesets cannot be dropped merely because they have no compiled
Cell entries.

The next integration must supply real completed-Run change evidence, freeze the
query snapshot while effects finish, and preserve ordered original effects and
visibility. Logical matches, numerical token changes, and a token novelty count
alone are not committed semantic changes. Thus this nested controller does not
yet replace the runtime schedule or discharge uncovered query/ownership work.
Reference Bake tip remains `9ee7070d`; executable control tables are retained
runtime memory and are counted as such, not treated as free offline metadata.

## Completed-Run handshake with effect evidence

`device_scheduled_runtime` now connects the nested controller to one snapshot
query/admission per Run, followed by as many effect-completion ticks as needed.
An open Run does not rematch after its effects modify the graph. Its phase,
program counter, query failure and accumulated effect-change flag survive a
bounded invocation through the returned continuation state. Uncovered queries
hold the same program counter even after supported effects finish.

Completion reports two supported semantic changes: new constructor allocations
and decreases in the number of Eq equivalence classes. Copying slots, reusing
existing constructors, refreshing vectors or adding an execution token is not
by itself a graph change. Eq path compression changes root pointers but not the
number of classes, so it does not falsely keep saturation alive. Partial Eq
changes remain accumulated while a Run is open; they cannot be reported as a
completed Run until coverage and completion gates pass. Future mutable effects
will need their own semantic change evidence.

85 mechanism tests pass. A compiled GPU local-family test drives nested
saturation with actual constructor effects: its completed Runs report changes
[true, false], although both Runs admit a new token. Another test waits with an
incomplete external boundary, performs only one query attempt, then resumes the
same Run after coverage is supplied. A negative coverage test retains its
unreported change and cannot advance. Eq tests distinguish class merging from
path compression and constructor reuse; copy-only completion reports no change.

These fixtures assume complete query enumeration of their finite local family.
In general a token can enable additional execution of already-existing facts;
coverage must prove those query routes are not omitted merely because an
intermediate cache token did not exist yet. Current real catalog coverage is
still false. The controller requires already-initialized source state, aligned
ruleset IDs, valid external coverage and no unrelated pending source operations.
It does not establish original cross-instance effect ordering, initial graph
import, CPU audit rollback or complete ownership takeover. Query failures stay
latched; automatic retry against a changed snapshot is not introduced.

Reference Bake tip `4c38c51c` learns real cross-stage composition from audited
executions, yet explicitly shows that fewer components/deeper paths need not
save retained state. The GPU continuation must likewise remove actual source
responsibilities under a proved combined template, not credit more generated
tokens as ownership savings. This commit changes no native runtime and makes
no full Eggcc correctness, prediction-accuracy or speed claim.
