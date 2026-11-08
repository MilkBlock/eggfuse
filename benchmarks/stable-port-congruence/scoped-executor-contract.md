# Completion and publication contract

The current objective still requires actual independent progress through the
Executor, concurrent workers, stronger Bake/compiler information and measured
inference benefit. The Graph API and selective Executor publication added here are prerequisites,
not completion of those requirements. The last accepted structural catalog (`d68f334c`) still
executes 1,046 logical completion tasks and a global barrier at every source Run.

## Present evidence

`Graph::complete_scope` drains only tasks whose compiler-derived effects can
reach the requested tables. The ready queue retains one membership per fact,
partitioned by table; only nonempty table heads share an ordered directory.
This preserves the former survivor order for the ordinary full-completion path.
Unrelated facts do not need to be rescanned individually to find a selected head.
The ordinary mode retains its original flat set.

Connectivity is committed before scope readiness can be reported. Incomplete
readiness means unknown, not a failed equality test. Owned tasks retain their
origin epoch; callers cannot enqueue a new dependent epoch into an unfinished
table. Queue membership and delayed epochs are independent of condition-node
lifetime: conditions still read current live facts, and fact/component IDs are
not reused. The API assumes the compiler-typed graph contract, including
same-sort equality endpoints; direct mutation of public internals is outside
that contract.

Compiler reachability includes constructor result equalities, tables containing
that sort and transitive chains across result sorts. Ruleset demands include
query tables, RHS accesses, deletion and Eq-valued primitive operands. Opaque
merge programs retain ordered full completion when actually pending; merely
declaring a dormant merge does not connect unrelated sorts. Mutable or uncovered
effects prevent declaring an ancestor safe for cross-Run deferral.

Fixtures establish independent Graph closure, dependent cross-sort closure,
origin epochs, exact mutable effects and stale program-scope rejection. Existing
ownership fixtures also run with table queues through the normal Executor. The
frozen sum-bits audit retains the original global barrier and compares exact
ordered traces. The subsequent Executor fixture now demonstrates independent publication and
consumption across two datatypes; see `scoped-executor-fixture.json`. It does
not establish same-sort locality or workload acceleration.

The subsequent `--port-scopes` experiment establishes same-sort locality through
the actual Executor: B commits and consumes results while A remains pending,
even with an unchanged shared input and an unrelated mutable table of that sort.
Shared influence code starts from the actual union cause roots, follows input
uses to possible output equalities, and uses the existing explicit boundaries.
It adds no per-producer consumer list. It remains table-granular and single
threaded. Sum-bits admits zero useful cross-Run progress in this experiment;
its added proof cost is retained as negative evidence in `port-scopes-audit.json`.

The initial sum-bits proof was too coarse: 401 tables, 99,201 potential dependency edges,
zero deferrable tables. Six opaque entries are one `set<Expr>` constructor and
five merges calling `Smaller`, `IVTMin`, `bound-min` or `bound-max`. This evidence
rejects treating table/type scopes as the final locality model. The compiler
already exposes the container element sort and merge programs; use those facts,
then refine unresolved dependencies to bound Cell ports and explicit boundaries.

The checked merge-footprint refinement now removes those six opaque entries.
It separates future equality tasks from constructor births, and read prerequisites
from mutation effects. Source Set and incoming union fences include hidden merge
reads. Concrete groups seed future result equalities from operator-filtered
shared input domains, including nonpending collision peers, rather than
replaying every effect of the input union already committed. Shared changed
inputs can therefore feed independently completed regions in the fixtures.

At `9a5c0a18`, sum-bits still has zero useful cross-Run progress: ten partial publications are
followed by ten access-footprint waits, with zero waits caused solely by union
expansion. Its scope analysis is more expensive than the previous global-boundary
shortcut. The next required proof must refine the ruleset's aggregate LHS/RHS
accesses to the actual bound work. Query readiness must precede dirty-reader
selection and snapshot matching; only then can empty/unexecuted RHSs be removed
from effect demands. Completing deferred work after matching is admissible only
when that work cannot invalidate any query binding, guard, watermark or snapshot.
The matched-rule refinement now implements that separation under `--port-scopes`.
The compiler derives mandatory query demands separately from each rule's RHS
accesses, hidden merge reads and conservative incoming-union effects. Queries
still wait before ready-set selection. All matching seals into one StagePatch;
only rules with bindings contribute the second, RHS wait. An empty snapshot
contributes no RHS effects, including inside a saturating source schedule.

Publication between matching and RHS execution must preserve matched Entry
origins and sealed Spine cursors. It also retains receipt forwarding and defers
frame garbage collection until those bindings are consumed. The binding's union
generation is captured before matching and remains unchanged across completion;
otherwise a stale context could acquire an invalid freshness certificate. The
matched-binding protection ends after RHS consumption; outstanding deferred
consumers still retain their original lifetime obligations. Global observers
retain their original barriers.

The short fixture commits three new facts through two bindings, and consumes the
independent result in a later Run while old same-sort congruence remains pending.
A matched RHS touching the pending region still waits; an explicit union retains
its future-effects fence. A negative control that unconditionally clears matched
origins fails with an out-of-bounds sealed cursor. This tests actual lifetime
dependence, not merely matching final graph hashes.

Sum-bits still commits no RHS while repair is pending. Its ten waits become three
query completions and seven matched-RHS completions. Forty bindings can be matched
earlier, but they still wait before execution. Two empty Runs carry pending work
without producing results and lose the settled-idle shortcut. The scope proof
and new RHS-demand bookkeeping are additional costs. Six RHS waits intersect
the access footprint; one comes solely from incoming-union expansion. Do not admit this as a
speedup. Bound access/effect proofs, same-table regional ownership, concurrent
workers and full-cost admission remain open.

## Executor contract (implemented for conservative table scopes)

1. Source Run matching keeps its finite snapshot. Before reading a ruleset, wait
   for its relevant completion footprint; this must happen before ready-set
   selection so unpublished changes cannot make a rule appear clean. Absence,
   equality-sensitive guards and nonmonotone effects need the same completion
   proof. An unrelated source occurrence may advance only when its reads and
   effects are independent of outstanding work. In port mode, query reads are
   mandatory first; RHS demand is derived from the sealed matched rules afterward.
2. Separate propagation progress from publication. Carry the origin epoch of
   deferred tasks, changes and publication records. Custom merge ordering and
   node allocation identity remain observable obligations, not incidental work
   that can be reordered without proof.
3. Split `ChangeBatch` by publication ownership while preserving per-table event
   counts. Publishing B must leave A's changes intact; re-publishing the whole
   batch and hiding A from queries only duplicates maintenance.
4. Seal shared Entry publication context across Runs. A pending Spine anchor
   references `Publication.slot`, `pending_steps` and `published_bases`. Clearing
   these arrays at the old global boundary invalidates deferred anchors. Retain
   their context or move it into an owned sealed bundle; do not copy every field
   into a new per-node maintenance structure. Preserve source ordinal selection
   when receipts later coalesce.
5. Keep unresolved `receipt_forwards` until every deferred consumer is resolved.
   The unconditional clears at Run start and after global publication are not
   valid under partial publication. Retirement, visibility, cache epochs and
   garbage collection must obey the same lifetime contract. Already matched
   bindings also retain their cursors and frame ancestors across a pre-RHS wait.
6. Publish only a proved-complete region into shared Entries, query indexes,
   neighbor/range views and reader wakeups. Audit instrumentation, final export
   and program checks must explicitly complete their observation footprint.
   A global audit snapshot may demand everything; it must not silently erase the
   independent-progress test's pending region.
7. A new source Run's writes are also a completion demand. An explicit union can
   reach old pending work through result aliases even when its direct reads are
   disjoint. The current compiler conservatively expands union and constructor
   `set` result sorts. Do not reuse a prior influence proof across changed Runs,
   or remove this gate, without a proof for the bound writes and epoch ownership.

## Gates that must remain open

- Through the actual Executor, A retains outstanding congruence while B matches,
  commits and publishes. A dependent observation and a negative/equality guard
  must wait. Both eventually reach the reference fixed point.
- Exercise partial births, deletion/recreation, boundary aliases and delayed
  receipt forwarding. Include same-sort disjoint Cell regions, not just two
  unrelated datatypes; the latter validates the protocol but is not sufficient
  for the intended workloads.
- Measure scope planning, queue operations, retained contexts, repeated
  notifications and allocations. The queue-only audit adds work until it
  replaces waiting or repeated maintenance in the Executor.
- Then remove shared mutable publication/union-directory bottlenecks and enable
  real workers with contested boundaries, source-ordered mutable effects and
  worker-count comparisons. No global lock or queue-drain wrapper establishes
  completion of the objective.
