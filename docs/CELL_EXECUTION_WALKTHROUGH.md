# Owned Cell execution: trace, boundaries and equivalence

This explains the ongoing refactor, including constructor-prefix continuation
and its shared prepared-result layout. It distinguishes implemented ownership from the still-unfinished
independent scheduler. See [the checklist](CELL_EXECUTION_REFACTOR.md) for scope.

## What remains the same instance

An execution instance is not the same as the physical Cell that owns an existing
constructor. An `Instance` owns its captured input slots, query evidence and
continuation origin. Those slots move into the graph's private/retained Cell
frame. `Execution` retains its frame handle, Cursor, demanded actual-result
buffer and source phase. `Cell.completed_prefix` is the source progress owner.
The result buffer later moves into completion/publication ownership.

These are lifecycle views of the execution, not a requirement that one Rust
struct or physical address remain unchanged. Moving ownership is permitted;
reconstructing bindings or replaying completed effects is what must disappear.
Constructor preparation now writes demanded witnesses into the source Effects
layout; ordinary completion/publication can retain the same allocation. The
existing joint-history path may need an explicit layout import. Ordinary history
capture and result publication are not yet completely unified.

The target scheduler parks the execution and queues its unfinished operation
address. A worker can then run another ready instance. A parked instance need
not stay assigned to the same worker, and a private slot array must never have
two concurrent writers. Current `apply()` instead loops synchronously through
`advance_cell`, `resolve_cell_boundary` and `finish_cell`. Optional suffix work
uses `pool.install` and waits. That is not the independent target scheduler.

## A source trace

Consider these conceptual operations, not a claim about their exact frontend
lowering:

```text
Run R query: Input(a,n), Other(b)
RHS: k = n + 1
     u = F(a)
     v = G(u)
     set Out(a) = k
     union(v,b)
Run R completion and publication
Run R+1 consumer: use G(u) and Out(a)
```

1. Query uses the original Run read view. Failed matches produce no execution.
   A successful match fills `a,n,b` and demanded witnesses. Different matches
   remain distinct instances. Successful candidates still undergo original
   input-key, depth and ordinal winner selection before shared effects.
2. Worker-local computation can fill `k`. If a safe speculation fails, it does
   not surface an RHS error early; the original source position remains live.
3. A typed proof may let existing `F(a)` and `G(u)` fill `u,v` in those same
   slots. Actual witnesses may belong to other physical Cells. The prefix can
   cross scalar operations already completed from captured inputs, including
   `k = n + 1` above. Bake records their required slots; a missing scalar result
   stops continuation before the next constructor. It does not reevaluate the
   scalar or invent graph identities. An invalid constructor certificate clears
   speculative Eq slots while retaining independently captured scalar results.
4. If a constructor is absent, source-time resolution remains necessary. A
   worker miss cannot skip that resolution: earlier source effects may create
   it. On its original turn, normal interning returns an existing or newly
   created actual result. That result fills the destination slot exactly once.
5. `set Out` retains its original order, merge callback and any resulting
   effects. More pure operations could run after its returned operands become
   available. Merely moving the operation to another thread does not prove
   independence from another instance's writes or unions.
6. `union(v,b)` retains its source submission point. Submission is not completed
   congruence. Local static wiring can establish which congruence conditions
   are relevant; unresolved shared equality and uncovered effects still pass
   through the authoritative graph path.
7. The Run boundary completes the required scope and opens legal visibility.
   A later Entry projects actual results and retained inputs. If Bake proves
   the consumer prefix, it can continue from the remaining query position.
   Residual/late/union-enabled matches still enumerate through their legal path.

## Exhaustive boundary classes, including exceptional paths

| Case | Required behavior |
|---|---|
| Snapshot query miss or false guard | Reject this candidate. Do not wait for a future fact that was absent from this Run. |
| Multiple matches/routes | Preserve all required enumeration, delta ownership and deterministic winner selection. Prepared output slots do not change identity. |
| Captured scalar or static alias | Compute/read the original slot; skip the corresponding source work only with the existing proof. |
| Existing constructor | Use actual results under source-valid evidence. Historical Cursor evidence cannot acquire a current-Run certificate merely by being retained. |
| Missing constructor | Park at the unresolved source operation in the target scheduler; normal source interning resolves it once. No private invented identity. |
| Missing parent projection/implicit result | Use the original operand reader at that unfinished instruction; completed instructions do not replay. |
| Union, retirement, hiding or generation change after preparation | Discard invalid optimization evidence and resolve the unfinished operation normally. Current prefix fallback clears all speculative Eq slots before allocation/effects. |
| Earlier RHS deletes an accepted match's LHS witness | Preserve the accepted source binding. Invalid reuse evidence is not grounds for canceling the original application. |
| Mutable read/write or merge callback | Observe the original source-ordered value and effect order. Runtime-layer mutable reads exist; ordinary native rule RHS does not allow arbitrary mutable lookups. |
| Local congruence condition | Check every required equality, not a digest alone. Static incidence can remove discovery/index work; shared union commit and publication still need their own proof. |
| Multiple Cells touch the same constructor/eclass | Treat as a potential shared conflict even if Cell owners differ. Per-Cell placement is a locality policy, not exclusivity. |
| Hide termination, Panic or primitive failure | Preserve earlier committed effects and the original stop/error position. A speculative later failure must not outrun earlier effects or Hide. |
| Duplicate/stale boundary delivery | Reject by execution phase and source position; never execute the same shared effect twice. Lifecycle generation checks remain necessary when handles can be recycled. |
| Cross-Run continuation | Retain storage/proofs, but honor the original schedule, visibility and activation boundary. Composition does not execute the next Run early. |
| Incomplete Bake coverage | Keep ordinary boundary/residual handling. An unknown route is not evidence that a match or effect is absent. |

## What Bake can discharge

The current execution plan derives typed segments with `start/end`, input/output
slots and the next boundary's kind, table and operation position. The loader
reconstructs and validates it against the authoritative recipe. It distinguishes
constructors, mutable reads, writes, unions, visibility, failure and unclassified
primitives. It is not yet a complete general-purpose parallel conflict plan.

Existing alias proofs, actual-result layouts, Cursor handoffs, permanence facts
and completion-access scopes can refine those conservative cuts. Bake can prove
that a required input is already established, a constructor is a valid reused
result, an internal Entry needs no materialized handoff, or only a specific
completion scope must finish before an observation. Runtime checks supply the
instance-specific facts: actual returned witness, generation, current equality,
table readiness and the legal source phase. Unknown facts leave the cut live.

For a dominated-to-dominator transition, the compiled mapping must retain the
entry proof, old slot identities, demanded exports and remaining ordered effects.
Changing the template/state can reuse storage. It cannot declare an unexecuted
constructor, union, mutable effect or later Run completed. Several incoming
routes can share the completed shape while retaining different entry proofs.

## Equivalence argument

At each original source position, relate executions by: the same accepted input
binding, the same committed effect prefix, the same established actual values,
and the same externally visible graph/Entry state. Prepared private values are
allowed in addition, provided they cannot become visible without validation.

A local step computes the same value from the same established operands. A
validated reused result is what original interning would return. A boundary
executes the same authoritative source instruction in the same order and stores
its actual return. A failed optimization resumes at that unfinished position,
without replay. The completion/publication boundary exposes the same legal
observations. Induction over source positions and Runs gives equivalence under
these obligations; equality of the final union-find alone would not suffice.

The current single-threaded source driver preserves this ordering by construction.
Allowing shared effects from parked instances to execute out of order is a
separate proof obligation and is not implemented by the current ownership work.
Nor does the borrowed Run read view permit graph mutation while readers hold it.

## Small Cells

Logical Cell size, execution-fragment length and worker batch size are separate.
Small instances with common code/locality can share one existing batch without
changing semantics. A combined Cell is valuable when it removes an intermediate
query, state transfer or dependency boundary. A larger name containing the same
sequence of waits does not improve the critical path.

Measure useful operations per batch, surviving external boundaries per instance,
redundant queries/handoffs actually removed, ready work, worker idle time, source
commit/completion waits, storage and discarded speculation. Extend composition
where observed applications and typed proof remove the most work. Do not reserve
the largest dominator layout for every tiny instance, and do not add a runtime
consumer list for dependencies already represented by shared static wiring.
