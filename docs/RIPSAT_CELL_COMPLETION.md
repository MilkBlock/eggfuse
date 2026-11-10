# Ripsat Cell completion implementation plan

The implementation starts at merge `718259bc` (the complete
`codex/cell-state-inheritance` branch through `4ba41744`). The executor is the
standalone Cell CPU runtime, not native egglog. The previous uncommitted
literal-query experiment is preserved in stash
`b6e5b1223b642e1c519365f1f4207481922054b7` and is outside this work.

## Objective and evidence

A successful source-scheduled rule application extends an existing Cell
instance. Bake should recognize its completed local structure, retain different
entry proofs, and compile the extension to a state transition with inherited
slots. A transition whose results already exist must not replay a synthetic RHS
or materialize another receipt array just to rediscover them.

The current CPU Cell egraph registers ordered continuation paths. Its state
extractor chooses materialization or history inheritance; it does not yet
identify different derivations of the same completed structure. Cursor carries
actual result witnesses and original Run positions, but `Training::applied`
currently runs before the RHS. Closed RHS completion still walks instructions,
builds a temporary Cell, assigns result values, records receipts and captures
them again. These are concrete takeover opportunities, not evidence of a speedup.

Prior full Raytrace evidence (`benchmarks/cell-winner-fold`) has 1,097,825 worker
point reads and 432,416 removed winner-record moves, without an overall speedup.
Consequently admission and scoring must include extra validation, dispatch,
storage and fallback work, not only the count of successful state switches.

## 1. Establish completed applications

Move the existing bounded apply evidence update to successful RHS completion.
Keep its existing rule/position, real witness, source Run and bounded window;
do not create a second binding log. A successful query or chosen winner is not
an applied rule. A failed RHS cannot establish a completed state. Pending unions
are effects queued at this boundary, not proof of public congruence completion.

## 2. Structural identities and finite proof

Derive a local symbolic graph from the authoritative Cell query and effects.
Normalize local port names, constructor incidence and exact equality closure.
Keep assumptions separate from derived results and retain ordered observable
effects. Start with positive constructor fragments whose closure can be proved;
unsupported mutable reads, deletes, primitives and effect ordering retain their
source path and ordinary execution.

Equivalent completed structures share an eclass; their entry assumptions and
local-port maps remain distinct implementations. Different rule sequences are
not a reason to keep duplicate structures, nor sufficient reason to merge them.
An observed path is a finite derivation, not a saturation certificate for all
possible future facts. Compile-time constructor congruence reaches a fixed point
within that finite graph. Any stronger saturation claim needs its own proof.

For each admitted D-to-U transition record the source completion state, source
rule application and template position, input mapping, inherited results,
remaining work and original visibility boundary. D inclusion in U requires an
incidence-preserving map. A hash/digest may index candidates but never prove
inclusion. Exact reconstructed contracts are checked on artifact loading.

## 3. Compile transitions and layouts

Use a shared finite transition graph, not all complete route sequences. Preserve
one immutable completion definition with route-specific entry maps. Prefer a
direct exact table for small fanout; use a Bloom prefilter only where it avoids
enough candidate reads. Bloom positives still require an exact record; negatives
exclude only learned transitions and cannot disable residual rule execution.

Compile retained result sources and consumer projections together. A result
source is an actual witnessed query/effect return, possibly owned by a foreign
Cell. It is never inferred from `(producer, operation)` alone. Existing slots
retain their location; aliases are template projections. Fresh results allocate
only their required suffix. Do not reserve the largest possible U in every D.

## 4. Execute completion, remove replaced work

At an original source Run, use the matched input/Entry proof to select the exact
transition. Validate any live witness needed at that boundary. For a fully
inherited constructor completion, use its compiled receipt projection directly:
no temporary RHS values, per-operation result stores or second receipt buffer.
Advance the same Cursor state only after the source application completes.

History and Entry publication must read the existing owner through the same
layout. Template wiring remains static; no per-instance producer-to-consumer
lists. Where some effects remain, execute them once in source order. A failed
proof must preserve normal execution without claiming saved work or publishing
an invalid completed state. Publication remains after required repair; immutable
structure equivalence does not permit early visibility.

## 5. Close the Bake loop

Feed successful applications and actual takeover counts into the next catalog
iteration. Compare routes by remaining work for their entry, rather than path
length. Charge receipt validation, slot reads/writes, retained bytes, allocations,
dispatch probes and boundary publication. Count avoided work only once across
marker, Cell and RHS paths. Preserve alternatives where their assumptions differ.

The deliverable is executable completion plus removed maintenance within proved
coverage, supported by exact tests and measured work. A registry, plan, counter,
or a state label without a runtime consumer does not complete this task.

## Acceptance and checkpoints

1. Merge: 85 runtime unit tests, 61 compiler/integration tests and the 20-lane
   short checker pass; sum-bits choice diagnosis is `pass`. No timing claim.
2. Proof tests: renamed ports and independent construction orders normalize;
   different incidence, assumptions, scalar literals and ordered effects do not
   falsely merge. Multiple routes preserve actual returned witnesses.
3. Execution tests: direct transition vs disabled transition has identical
   final graph, ordered Run snapshots/bindings/effects. Include late input,
   union-enabled match, stale/retired witness, foreign constructor reuse and
   fallback. Repeated transitions must preserve owner/slot storage rather than
   grow a projection chain.
4. Artifacts: reject corrupt mappings, source digests, unsupported operations,
   premature completion and forged entry proof. Run current feature combinations
   and README compile/run/bench on a short source.
5. Work: compare the same short inputs and binary configuration against
   `718259bc`; record deleted work and added costs. Reuse native exports with
   `benchmarks/marker-handoff/choice_diagnosis.py`, requiring pass/exit 0.
6. Speed: at the authorized five-commit checkpoint run sum-bits and Raytrace,
   including worker lanes and the historical fastest configuration. Build before
   measuring. A work-counter improvement alone is not an acceleration result.

These checkpoints are implementation stages, not permission gates. Until the
runtime takeover, Bake integration and semantic acceptance are complete, the
overall feature remains unfinished.

## Implementation checkpoints

`e276c6ca` adds exact bounded structural normalization, native ripsat registry
integration, typed prefix inclusion maps and actual-success apply sampling.
Renaming/order, stronger-entry and failed-RHS tests pass. This checkpoint alone
is a compiler foundation, not a runtime takeover.

The next implementation introduces result-switch v4. Artifact loading
reconstructs the exact direct program and slot maps. A qualifying completion
borrows an existing retained owner, validates actual receipt visibility, reserves
only its source identity and seals a shared Entry delivery. It bypasses
`result_inputs`, `begin_effects`, `start_completion`, result assignments and raw
receipt capture. There is no intermediate dependency array. A shared projection
wrapper may still allocate; that cost remains in `history_allocations`.

The direct regression runs the optimized configuration, stops after each source
Run, and compares graph snapshots plus ordered input/write/resume digests. The
ordinary `audit=true` mode suppresses compiled publication and cannot alone prove
this takeover. Foreign-owner reuse, a union between stages, a deletable-result
fallback and forged artifacts are included. Repeated projection composition,
structural alternative transition discovery and workload coverage remain work
for the next checkpoints.
