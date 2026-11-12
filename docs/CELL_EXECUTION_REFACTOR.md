# Cell execution ownership and compiled dependency boundaries

Baseline: annotated local tag `cell-execution-refactor-base`, commit `4ba83913`.
Scope: standalone Cell CPU runtime. Native egglog remains the semantic reference
for the reviewed sum-bits contract. This document is a completion checklist,
not a claim that any unfinished phase is implemented or faster.
The [execution walkthrough](CELL_EXECUTION_WALKTHROUGH.md) explains source traces,
all boundary classes, the equivalence obligations and small-Cell batching.

## Evidence and objective

The last complete Raytrace run still has substantial coordinator matching,
Entry preparation, RHS and completion work. The saved stack window observes
workers in condition waits in 88.4–89.8% of samples; this is a sampled diagnostic,
not whole-run utilization. The prior separate RHS preparation draft introduced
another pool pass after winner selection and was not validated. It is archived
under ignored `out/cell-execution-refactor/prior-draft`, not shipped.

The objective is one owned Cell execution from query through local computation,
ordered shared effects, internal completion and Entry projection. Worker loops
alone are insufficient. Actual applications must guide subsequent Bake choices:
prefer compositions that discharge repeated queries, handoffs and completion
dependencies; retain entry proofs and charge uncovered work and all new costs.

## Work and acceptance sequence

1. Compile dependency cuts from the authoritative typed Cell operations. Reuse
   immutable instruction storage, actual result layouts and completion access
   proofs. Separate snapshot queries, safe local computation, ordered mutable
   reads/writes, constructor resolution, union, visibility and failure. The
   loader must reconstruct and validate any emitted plan from source.
2. Continue successful worker queries into the same Instance slots before
   returning. Distinguish prepared local results from committed effects. Keep
   winner identity restricted to original inputs. Consume prepared work in the
   ordinary RHS, removing its re-execution rather than adding a preliminary
   pass. Preserve failed arithmetic at its original source position.
3. Extend the same state through shared-effect boundaries: park the instance,
   return only unresolved boundary addresses, fill actual result slots and
   resume. Preserve actual foreign-owner results, source effect ordering,
   deletion/generation validity, early Hide termination and error ordering.
   Do not replace bindings with a full operation log for coordinator replay.
4. Unify retained results, completion and Entry publication around that owner.
   Freeze published prefixes and append only necessary suffixes. Derive local
   congruence wiring statically; no per-producer internal consumer lists.
   Current union submission is not completed congruence. Uncovered crossings
   retain the ordinary boundary handler and original visibility guarantees.
5. Make iterative Bake compose these executable fragments and layouts. A
   dominated-to-dominator transition needs exact incidence/entry proof, actual
   returned witnesses and remaining ordered effects. Remove covered intermediate
   handoffs while retaining exports needed by other consumers. Cross-Run storage
   reuse does not authorize early execution of later source Runs.
6. Batch small Cells by shared code and locality. Ownership may migrate without
   rebuilding the frame. A missing snapshot fact rejects the candidate; waiting
   is for an already scheduled boundary, not for a future matching fact. Parked
   instances must not park workers. Expand conflict handling only with a proof
   of independence that includes union and merge callbacks.
7. Compare the actual runtime to this tag and the historical fastest lanes.
   Required outcomes include reduced coordinator critical-path work, reduced
   instance handoffs/waits and verified throughput/utilization, with preparation,
   discarded speculation, storage, allocation and boundary costs included.
   No count of parallel operations alone satisfies the objective.

## Semantic obligations

Keep the same source Run query snapshot, residual enumeration, late and
union-enabled matches, watermark/delta ownership, original-input winner order,
actual constructor results and ordered observable effects. Do not cancel an
accepted binding merely because a previous RHS deleted one of its LHS witnesses.
Stale optimization evidence falls back at the unfinished operation; completed
effects never replay. Query errors, RHS errors, Panic and failed Hide retain the
same prior effects and stopping position. Mutable reads see the source-ordered
current value; pure expressions use their captured inputs.

First keep the existing Run query barrier and effect order. Any later relaxation
requires its own proof; the current borrowed read view is not a multiversion
snapshot. At every legal publication boundary compare graph state, visibility,
ordered matches/effects and resumed entries against disabled execution. Test
branching matches, duplicate routes, foreign reuse, deletion/recreation, unions,
mutable reads, late inputs, partial completion fallback and source failures.

Use the repository's choice_diagnosis.py entrypoint for sum-bits native acceptance
and exact ordered Run regression for Raytrace. Validate compiler artifacts,
minimal and feature builds, and the README Cargo commands. Preserve
egglog-baseline. Commit coherent checked changes separately; do not claim the
overall objective complete until all applicable items above are proven.

## Current state

- Constructor continuation now crosses already completed captured-input scalar
  operations in the same instance; see [coverage and costs](../benchmarks/cell-scalar-boundaries/README.md).
  Raytrace removes 60,721 coordinator constructor boundaries and 27,738 source
  lookups, but adds 7,621 total lookups and 33,068 scalar-slot checks. Joint
  imports and additional arrays are charged; the equal-weight work proxy
  worsens by 547,001, so no speedup is claimed. Imported spare arrays no longer
  accumulate in the idle pool. Original source effects, all ordered Run
  summaries and final states remain unchanged; native sum-bits acceptance passes.
  Independent parked scheduling, compatible read/write storage and useful
  multithreaded throughput remain unfinished.
- Baseline tag created; prior separate-pass draft archived.
- Source-derived boundary plans and direct query-to-local-prefix continuation
  implemented; [work and semantic acceptance](../benchmarks/cell-execution-prefix/README.md).
  First result slots share the query allocation; covered RHS calculations are
  removed.
- Closed completion and first-miss promotion now retain that same owned slot
  array. The separate computed-result map, borrowed-input overlay and promotion
  merge are removed; [work and acceptance](../benchmarks/cell-execution-ownership/README.md).
  This is coordinator execution, not yet an independently parked worker Cell.
- Optional source-ordered resumption now retains progress in the actual Cell
  and runs its later pure segments on the existing worker pool; see
  [the resumption checkpoint](../benchmarks/cell-execution-resume/README.md).
  The host resolves shared effects once and waits for each frontier. Concurrent
  scheduling of multiple parked executions is still unimplemented.
- Input-derived scalar operations beyond the first shared effect now prepare
  in the existing query invocation and are consumed from the same slots at
  their source position, including the single-write and mixed-resumption paths;
  see [work and acceptance](../benchmarks/cell-execution-inputs/README.md).
  Raytrace removes 9,280 of 71,912 later worker round trips; 95,702 local
  operations remain outside this takeover. No new speedup is claimed.
- Already completed source-Run matches now join the existing worker invocation
  through their original owned arrays; see [work and acceptance](../benchmarks/cell-execution-matched/README.md).
  Captured scalars permit preparation despite parent/continuation provenance,
  and an attempt flag prevents failed speculation from being retried during
  batching. Raytrace consumes all 93,181 added prepared results and reduces
  later worker segments from 62,632 to 3,046. Header/admission, slot growth and
  mixed/matched-only invocation costs are recorded; no speedup is established.
- Deferred serial candidates now join that same invocation through their
  original owned arrays. The existing coordinator Cursor arena provides a
  move-only origin handle; selection releases losing origins and preserves
  source order. Separate ordinal and deferred-conversion containers are removed;
  see [work and acceptance](../benchmarks/cell-execution-deferred/README.md).
  Additional 29 / 4,283 prepared results are all consumed, removing the remaining
  observed 29 / 3,046 later scalar dispatches. Earlier Cursor storage, rule-slot
  mapping and group/slot growth are charged; no new speedup is established.
- Cursor/receipt ownership, completion/publication unification and Bake
  composition now continue through an owned ordinary RHS continuation; see
  [the ownership checkpoint](../benchmarks/cell-execution-owner/README.md).
  One Cell position replaces duplicated loop/worker positions. Its existing
  Cursor, handoff inputs and actual result buffer survive a returned boundary;
  stale or failed deliveries cannot replay effects. The source driver still
  resolves those boundaries synchronously. Joint result frames independently
  own transient scratch instead of borrowing all pending publications, removing
  415 / 42,787 exclusive arena borrows with one 64-byte scratch growth per case.
  Existing logical work and source Run states are unchanged; no speedup claimed.
- Ordinary effect results now have independent ownership through completion and
  publication, including partial publication and abort; see
  [owned output buffers](../benchmarks/cell-execution-outputs/README.md).
  The retained array moves into its owning Completion without copying results;
  global arena offsets and borrowing unrelated pending outputs are removed.
  Empty buffers are recycled. Added pooling, growth, ownership-transfer and
  larger Completion-record costs are reported and charged by measured Bake.
  Ordinary history capture is still separate from this result array.
- The fifth-change [timing checkpoint](../benchmarks/cell-execution-outputs/README.md#five-change-timing-checkpoint)
  does not establish a speedup against the immediate control. Current four-worker
  inference is 29.2% slower than serial on sum-bits and only 3.3% faster on
  Raytrace; Raytrace still takes 5.617 s. Whole-process times vary across the
  measurement sequence, so their medians do not isolate a runtime change.
  All samples and exact state/Run signatures are retained. Remaining scalar
  suffix dispatches are already zero in the observed work; extending useful
  worker computation and removing ordered RHS/boundary work remain necessary.
- The graph-facing execution context now moves together across actual worker
  suffix dispatch: private slots, writer hint, source epoch, input certificate
  and ownership Entry; see [suspension checks](../benchmarks/cell-execution-suspension/README.md).
  Already referenced frames remain graph-addressable with existing lifecycle
  holds. Two private contexts can coexist, and parked public/parent frames
  survive replacement, deletion and collection in targeted checks. The source
  driver still waits; independently scheduling several executions is unfinished.
  Public-frame worker borrows still exclude concurrent graph mutation. New
  promotions/holds and context moves are charged, not claimed as saved work.
- Native ordinary rule RHS prohibits mutable function lookups. A legal primitive
  boundary fixture exercises the suspension protocol, while mutable-read
  semantics are checked at the runtime instruction layer. Together with zero
  scalar suffix dispatches on sum-bits/Raytrace, this points the next coverage
  work toward constructor resolution and local completion. Removing scalar
  dispatch, graph attachment and publication-arena borrowing alone does not
  establish concurrent shared effects, repair or useful full-worker utilization.
- Input-ready constructor preparation now continues in the existing query
  invocation and its actual witness stays with the instance into source RHS;
  see [work and acceptance](../benchmarks/cell-constructor-preparation/README.md).
  Both ordinary execution and constructor prefixes consume that witness without
  a repeated serial lookup, retaining source order and fallback at the same
  key. Raytrace removes 556,868 source lookups but adds 913,319 probes, 1,027,684
  validation field checks and larger instance/owner headers. Total lookups and
  uncalibrated work increase. This bounded takeover remains opt-in; compiler
  selection/validation, independent parked scheduling and useful throughput
  improvement remain necessary. It is not completion of the overall goal.
- Prepared constructor results now use the existing source-Run union certificate
  and original-witness lifecycle checks to bypass source key reconstruction and
  comparison; see [certificate continuation](../benchmarks/cell-constructor-certificate/README.md).
  The actual Raytrace run replaces 1,027,684 field comparisons with result-only
  access for 556,868 witnesses; source lookup counts and all logical effects are
  unchanged. Invalid certificates/receipts retain exact validation and fallback.
  No instance or compiled-plan storage is added. New certificate/lifecycle work
  is charged; the conservative equal-weight score does not improve, and no
  speedup is established. This reduces the contents of an ordered boundary but
  does not yet independently schedule parked Cells or parallelize shared effects.
- Existing compiled Cell result donors now suppress redundant worker preparation
  at the original matching outlet; see [handoff admission](../benchmarks/cell-constructor-handoff/README.md).
  Raytrace removes 28,127 prequeries, with 21 restored source lookups after stale
  handoffs, for 28,106 fewer total lookups. No bindings, history arrays or instance
  fields are added. A shared compiled flag restricts admission to 2 of 366
  preparation rules, adding 4,656 compiled-plan bytes. Original handoff validation
  and source fallback remain live. Rule/history checks, comparisons and reads
  are charged; the uncalibrated net work score improves by 223 / 90,740 operations.
  Actual query/dispatch work decreases, but this does not establish throughput improvement or independent
  parked scheduling. The remaining constructor misses and shared-effect boundary
  work still require further takeover.
- The first [resumption timing checkpoint](../benchmarks/cell-execution-resume/README.md#timing-checkpoint)
  finds grain-1 worker dispatch regresses sum-bits / Raytrace inference medians
  by 21.9% / 12.9% against current four-worker execution with resumption disabled.
  Grain 64 runs those suffixes inline. Independent parked-frame scheduling and
  a throughput/utilization improvement remain unproven; dispatch stays opt-in.
- Workers now continue existing permanent constructor prefixes in the original
  slots; see [prefix continuation](../benchmarks/cell-constructor-prefix/README.md).
  The original Run certificate and table readiness validate the whole mutation-free
  prefix before source effects. Invalid prefixes clear all prepared Eq slots.
  Raytrace skips 483,504 source instructions and removes 436,620 ordinary
  constructor boundaries, but adds 345,339 probes against 198,959 additional
  avoided source lookups. Total queries increase by 146,380. New slot growth,
  temporary witness arrays, header/compiled storage and receipt writes are charged.
  Final states and ordered Run summaries match; native sum acceptance passes.
  The result buffer still transfers demanded witnesses into Effects, and shared
  effects still run synchronously. This is broader worker continuation, not
  independent parked scheduling or evidence of throughput improvement.
- The constructor-prefix [fifth-change timing checkpoint](../benchmarks/cell-constructor-prefix/README.md#fifth-change-timing-checkpoint)
  does not establish speedup: relative to `8369a224` with the same continuation
  flags, sum-bits improves 3.0% but Raytrace regresses 2.0% in median, with
  overlapping samples. Candidate Raytrace is 5.778 s, versus 5.533 s for the
  refactor tag and 5.597 s for the historical control. It remains opt-in.
  Four-worker prefix execution is only 2.1% faster than current serial on
  Raytrace and 29.5% slower on sum-bits. Independent scheduling, removal of
  temporary result storage and useful throughput/utilization remain unfinished.
- Prepared constructor witnesses now occupy the same compiled result layout as
  source Effects; see [shared prepared results](../benchmarks/cell-prepared-results/README.md).
  Raytrace transfers 185,328 arrays into Effects, removes 262,894 source receipt
  writes and 483,504 intermediate writes across both phases. Combined result-buffer
  growth events fall by 115,102. A measured cache-retention regression was corrected
  by replacing the source spare when adopting an incoming array; the pool keeps
  39,067 buffers and shrinks from 2,742,768 to 698,240 capacity bytes. Actual query,
  graph, repair and source-boundary work is unchanged. Header sizes remain unchanged,
  while shared layout storage, worker checks, moves and spare releases are charged.
  Ordinary publication retains this buffer; joint-history conversion is explicit,
  and ordinary history capture remains separate. Native acceptance and Run checks
  pass. There is no new speed claim or independent parked scheduler.
