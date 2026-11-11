# Cell execution ownership and compiled dependency boundaries

Baseline: annotated local tag `cell-execution-refactor-base`, commit `4ba83913`.
Scope: standalone Cell CPU runtime. Native egglog remains the semantic reference
for the reviewed sum-bits contract. This document is a completion checklist,
not a claim that any unfinished phase is implemented or faster.

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
- Cursor/receipt ownership, completion/publication unification and Bake
  composition of those continuations remain live work. The next opportunity
  is batching already completed source-Run matches with the existing worker
  invocation, preserving their slot ownership and proving parent/continuation
  eligibility, rather than creating a separate preparation pass.
- The first [resumption timing checkpoint](../benchmarks/cell-execution-resume/README.md#timing-checkpoint)
  finds grain-1 worker dispatch regresses sum-bits / Raytrace inference medians
  by 21.9% / 12.9% against current four-worker execution with resumption disabled.
  Grain 64 runs those suffixes inline. Independent parked-frame scheduling and
  a throughput/utilization improvement remain unproven; dispatch stays opt-in.
