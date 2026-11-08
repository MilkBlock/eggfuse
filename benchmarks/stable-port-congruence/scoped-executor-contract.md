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
origin epoch. Ordinary scoped callers cannot enqueue a new dependent epoch into
an unfinished table. The opt-in pure-epoch proof described below admits multiple
source epochs in one table only after checking the actual RHS. Queue membership and delayed epochs are independent of condition-node
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

## Closed pure source epochs

`--pure-epochs` extends port scopes with a restricted bound-effect proof. The
compiler accepts only copies, checked i64 arithmetic, explicit union and Set
operations for constructors covered by shared ownership. Each Set table must be
complete before its key is probed. No custom merge, deletion, fresh constructor
call or opaque equality is previewed. All source matching remains sealed first.

If every union is already true and every Set finds the same existing result,
the RHS cannot create a new equality or fact. Otherwise a bounded interpreter
records explicit source equality pairs and new constructor sites. All key
lookups use complete tables. A finite RHS-local overlay includes earlier births
under the same exact key; no source union commits between these lookups.

The proof builds equivalence classes of those *known source pairs*, including
transitive chains. The actual runtime's minimum-root union policy identifies
which existing roots will be displaced; it does not establish any congruence.
Only displaced roots start an effect. Their complete shared signal domains
identify affected operators. For each operator, the proof includes outputs from
all class members, including the unchanged representative and the new Set sites.
It therefore cannot omit a same-operator collision peer on the unchanged side,
and it does not expand unrelated operators on that side. Candidates need not
satisfy all scalar or multi-input guards: including extra outputs is conservative.
The existing exact congruence path still proves every committed equality.

From these output roots, the proof closes conservatively through live shared
wiring, the whole known source class and new Set sites. An older pending effect
can also acquire a new consumer: a birth whose input belongs to the retained
complete pending frontier contributes its output to this closure. Typed fallback
frontiers are unknown and conservatively expose every such birth. The frontier
sets reuse the existing forecast's visited-root sets, and are retained only in
pure-epoch mode. They are not per-producer consumer lists.

A live legacy/mutable user on a displaced root or possible result rejects the
batch; unchanged unrelated input users do not. Missing wiring and budget overflow
retain the previous wait. The preview accepts at most 4,096 instruction/overlay
steps; the proof accepts at most 4,096 root/signal/static/legacy/source/birth steps.
These counters and scratch growths are charged to Bake's heuristic work ledger;
they do not provide a complete allocator census or a latency model.

The scoped queue stores an epoch with each existing pending fact, retaining its
source-ordered head directory. Multiple inputs can re-notify the same fact; its
pending epoch becomes the maximum notification epoch. Only the pure-epoch mode
relaxes the table-wide epoch assertion. Collision completion joins the task and
both row epochs before enqueueing the result equality, including when an older
task meets an already completed newer peer. This is pending work metadata, not a
new producer/consumer reverse index. The ordinary flat queue is unchanged.

The short fixture commits one source union and two fact births, and consumes the
new result while prior congruence is still pending in the same table. Other
fixtures cover repeated input notifications with the final row stamped at epoch
two, colliding absent-key Sets, a no-op union with a mutable user, an actual
mutable-boundary rejection, and the walk-budget fallback. This establishes the
single-thread protocol, not concurrent access safety.

The original all-root proof in `210b57dd` admitted only three no-op batches on
sum-bits. The displaced-source proof now admits the other four batches too:
five effective source unions and six fact births commit while old congruence is
pending. RHS waits drop from four to zero; query waits stay at six, so total
waits fall from ten to six. All 1,428 source observations and state/RHS/effective
write/resume/Spine hashes remain exact. This is independent single-thread
progress, not a measured speedup or concurrent-worker result. The original pure
proof and scope planning costs remain visible in the two audit files; additional
source grouping, birth checks and retained-frontier memory must also be counted.

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
