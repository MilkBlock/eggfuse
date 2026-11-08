# Completion and publication contract

The current objective still requires actual independent progress through the
Executor, concurrent workers, stronger Bake/compiler information and measured
inference benefit. The Graph API added here is a prerequisite, not completion
of those requirements. The last accepted structural catalog (`d68f334c`) still
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
ordered traces. **No fixture yet demonstrates independent Executor publication.**

The sum-bits proof is too coarse: 401 tables, 99,201 potential dependency edges,
zero deferrable tables. Six opaque entries are one `set<Expr>` constructor and
five merges calling `Smaller`, `IVTMin`, `bound-min` or `bound-max`. This evidence
rejects treating table/type scopes as the final locality model. The compiler
already exposes the container element sort and merge programs; use those facts,
then refine unresolved dependencies to bound Cell ports and explicit boundaries.

## Required Executor changes

1. Source Run matching keeps its finite snapshot. Before reading a ruleset, wait
   for its relevant completion footprint; this must happen before ready-set
   selection so unpublished changes cannot make a rule appear clean. Absence,
   equality-sensitive guards and nonmonotone effects need the same completion
   proof. An unrelated source occurrence may advance only when its reads and
   effects are independent of outstanding work.
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
   garbage collection must obey the same lifetime contract.
6. Publish only a proved-complete region into shared Entries, query indexes,
   neighbor/range views and reader wakeups. Audit instrumentation, final export
   and program checks must explicitly complete their observation footprint.
   A global audit snapshot may demand everything; it must not silently erase the
   independent-progress test's pending region.

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
