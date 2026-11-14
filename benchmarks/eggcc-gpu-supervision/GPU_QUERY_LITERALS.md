# Exact query literals and native context export direction

Query i64 literals now lower to explicit bound scalar slots with template guards.
The existing initialization identity registry resolves each guard. GPU matching
checks it before candidate compaction, so rejected rows cannot displace a valid
match in a bounded batch. No constant fact relation or floating identity encoding
is introduced. Missing constants produce no matches. Witness audit and the
independent normalized-query reference also check the guards.

These extra slots are charged in the runtime layout and token encoding; this is
not a compression result. The constant remains exact even beyond f32 precision.
The original unlowered rule remains authoritative for effects and per-Run audits.
RHS literal initialization is still unsupported; this does not enable rule 145.

Actual rule 139 on synthetic seed 20261500 passes GPU full-graph, per-Run, matching
and lowering checks. The regression suite passes 23 tests, including capacity-one
literal filtering, absent constants, and a constant greater than 2^60. No learned
accuracy or speedup is claimed.

## Prefer Eggfuse for future corpus execution

The native runtime already exposes CellBindingObserver (borrowed input Slots and
Graph at the finalized query/RHS boundary) and CellResultObserver (actual slot
reads before repair/publication). The existing capture_rhs_results example uses
them with independent per-Run checks. They are a better base for executing random
synthetic programs and obtaining authoritative Cell evidence than indefinitely
extending a parallel Python executor.

This is not yet a bounded context export API: current capture is diagnostic and
may copy/export substantial data. Bake should specify required input slots,
actual result witnesses, local neighbors, scalar inputs and visibility/generation
checks; the observer should export those fields in shared batch layouts. Input
capture must precede completion; labels remain separate. Real Eggcc Runs remain
evaluation-only. GPU matching and token generation must not become dependent on
CPU finding each next match.

Python can retain orchestration and focused independent tests. No native exporter
or CPU runtime implementation was changed this turn. The native source files
have unrelated work in this worktree, which was preserved.
