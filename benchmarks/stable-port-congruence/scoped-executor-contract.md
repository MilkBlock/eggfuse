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
the RHS cannot create a new equality or fact. Otherwise shared compiler-derived
expressions record explicit source equality pairs and new constructor sites.
Copy aliases share expression addresses; only needed bound slots are read, and
checked i64 arithmetic uses dense temporary values. The old whole-binding clone
and Copy/temporary-slot map are removed. Arithmetic remains in the preview even
when its result is unused, so failure cannot silently authorize source effects.
The code is prepared once per template only when pure epochs are enabled. All key
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
batch; unchanged unrelated input users do not. A new affected operator must also
be outside every older pending completion footprint, including effects reached
through output wiring. Pure constructors alone do not prove this: merging tasks
from overlapping epochs in FactRef order can change the surviving witness.
Unknown same-operator independence retains the source fence; a shared Eq sort
alone does not require one. Missing wiring and budget overflow
retain the previous wait. The preview accepts at most 4,096 expression/effect/overlay
steps; the proof also charges root/signal/static/legacy/source/birth/order checks
against its 4,096-visit budget.
These counters and scratch growths are charged to Bake's heuristic work ledger;
they do not provide a complete allocator census or a latency model.

The scoped queue stores an epoch with each existing pending fact, retaining its
source-ordered head directory. Multiple inputs can re-notify the same fact; its
pending epoch becomes the maximum notification epoch. Only the pure-epoch mode
relaxes the table-wide epoch assertion. Collision completion joins the task and
both row epochs before enqueueing the result equality, including when an older
task meets an already completed newer peer. This is pending work metadata, not a
new producer/consumer reverse index. The ordinary flat queue is unchanged.

Fixtures commit an independent H equality while F remains pending in the same
Eq sort, and publish/consume independent births. Overlapping constructor epochs
now retain a source fence. Other fixtures cover row epoch preservation, colliding
absent-key Sets, no-op unions, mutable boundaries and walk-budget fallback. This
establishes a single-thread protocol, not concurrent access safety.

The earlier `3c5739e8` pure-epoch admission is withdrawn by a regression that
changes ordered exported witnesses (its scalar record result stays equal).
The corrected sum-bits path rejects four Base overlaps, retaining six query and
four RHS waits, zero effective source unions and zero fact births while pending.
This is a conservative proof boundary, not evidence that all four waits are
intrinsic. All 1,428 source observations and state/RHS/effective-write/resume/Spine
hashes remain exact. Compiled preview code still uses three tracked scratch
growths and 155 materialized values. No overall acceleration is admitted.

The optional `--unique-port-publication` proof publishes a changed key only when
one complete shared input domain proves that no other live same-operator peer
exists, including hidden and pending facts. It cannot cross unfinished source
unions, earlier queued facts or legacy work. The publication joins row/task epochs
and advances the query version; it omits the key queue and congruence visitor.
Sum-bits removes 17 such obligations but none of the ten waits, adding 7,506
charged proof events. This experiment is disabled by default and is not admitted
as a performance improvement. No new instance consumer index is installed.

Optional progress diagnostics now retain the actual query fence outcomes. Runs
23, 86, 169 and 581 publish 9, 1, 12 and 50 effective congruence unions. Runs 79
and 477 have no collision or legacy repair: they advance one TCons and two Concat
query versions. These version advances are publication notifications, not source
writes. Removing those two waits requires a complete snapshot/publication proof;
zero result unions alone do not establish that proof.

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

## Immutable read phase

Exact local conditions and foreign candidate checks use a borrowed ReadView of
the equality relation and component signal arrays. Each guard returns local work
counts. The coordinator alone updates runtime counters, chooses the first live
eligible candidate, and commits visibility, retirement and result equalities.
Scalar fields and compiler condition code are borrowed; no full Graph or row
snapshot is copied to make the evaluator Send + Sync.

KeyGuard binds one live candidate to a key canonicalized in that same read epoch.
A true guard establishes neither domain completeness nor permission to publish.
The borrow prevents a union, deletion or rebinding while workers use the view.
After mutation, a new borrow and new canonical key are required. The optional
`--guard-workers N --guard-grain M` path now dispatches bounded candidate rounds
from the actual completion loop to a persistent private pool. A round finishes
all borrowed reads before the coordinator selects the earliest match or error
in original candidate order. Later speculative results cannot change the chosen
survivor or create an error the serial path would not observe. All executed
guards, including discarded results, contribute to work counts.

The candidate-only mode gives one popped task a read epoch. The optional
`--completion-batch-tasks 2..64` mode instead uses the following certificate to
read several queued tasks in one pool dispatch. Both remain synchronous read
phases; concurrent Graph mutation and asynchronous publication are separate
obligations.

## Certified completion read batches

1. Merge a bounded prefix of the existing scoped table queues, stopping before
   an earlier legacy task. The compiler's scalar constructor key footprint and
   complete local condition plan must cover every prefetched source. No table
   bucket or graph body is scanned to discover work.
2. Borrow the same immutable equality relation for all worker tasks. Include
   earlier pending peers in guard evaluation: they may become completed peers
   before this source's turn. Later pending peers remain ineligible. Cache exact
   true/error answers in candidate order, stopping only at a pre-existing
   completed exact peer. The unchanged-input certificate also protects this
   peer: it cannot become a key task without an input-class change.
3. Record the canonical input classes from **every** compiler-declared equality
   key column in a transient `(class, task)` vector. This is one read window's
   certificate, not a persistent producer/consumer subscription index. Scalar
   fields, operators and node addresses are immutable during pure completion.
4. Before each derived union, check both result classes against unread inputs.
   Either an absorbed class or the absorbing class can invalidate equality
   predicates and candidate-domain completeness. Keep only the prefix before
   the first affected task. A no-op union changes no class membership.
5. At commit, recheck the live queue head, candidate liveness and pending state;
   then select the first still-eligible cached answer in original order. Read
   current visibility and epoch. After an effective intervening union, resolve
   the retained result ID again; certified inputs need no re-read. The original
   constructor collision path owns union, retirement and publication.
6. A newly queued earlier pure port-key constructor runs serially at its original
   position. Its derived union goes through the same certificate check, including
   the next uncommitted cached source. Unaffected reads survive this interruption.
   A legacy or opaque effect ends the window before it can allocate a new peer,
   mutate scalar data or otherwise violate the no-birth assumption.

The induction is over ordered commits: if no union touches a future source's
input classes, exact key equality with each surviving peer is unchanged and its
previously complete candidate domain remains complete. Retirement only removes
peers and is checked at selection. Earlier pending peers becoming eligible are
already represented. This admits independent nodes of the **same Eq sort**;
sharing a sort alone does not require waiting. Results never cross a source Run
or survive an uncertified mutable effect. Invalid/unused reads, preparation,
certificate searches, extra queue probes, dispatches and allocations are charged.

## Direct worker access to stable nodes

Stable fields have a single owner: a plain `FactRef -> Stored` directory in the
stable-port runtime. Cell metadata no longer owns an `Rc<Stored>`. Directory keys
are fact identities, never canonical equality representatives; union does not
rewrite or rehash these keys. Birth installs the entry, retirement removes it,
and missing entries are inactive candidates. Retained consumers of a deleted
producer still use the existing recipe fallback. Report-time invariants check
that directory entries and live owned facts correspond in both directions.

The immutable worker view borrows this directory, the equality relation, shared
component bindings, and a counter-free membership view of the authoritative
pending queues. No node copy, per-worker index or producer/consumer subscription
is created. These borrows still prohibit Graph mutation during the read phase;
splitting storage alone does not establish independent progress during mutation.

Batch tasks borrow candidate addresses and compiler condition code. A worker
looks up a node only when it reaches that candidate, checks current read-epoch
pending membership, and stops according to the existing ordered-match proof.
The coordinator no longer builds a bound descriptor for every candidate before
dispatch. Each worker writes answers into its task's disjoint result slots;
collection needs no intermediate answer array. Commit-time liveness and input
certificates remain unchanged. Node queries, directory lifetime operations,
pending probes, task preparation and allocator costs remain explicit in credit.

## Overlapped completion epochs

`--overlap-completion` extends the certified batch protocol. It requires a
configured completion batch and persistent pool. The coordinator remains the
sole writer and preserves task/union/publication order, but it can commit an
earlier task while later tasks are still evaluating guards.

Before dispatch, four base containers move into immutable shared ownership:
parent links, stable nodes, component records, and scoped queue tables. Creating
these bases copies no container body. Current coordinator reads first consult
their write overlays. New parent links use a small delta map; retired nodes use
tombstones. A queue table is copied on its first write in this epoch, and
subsequent writes reuse that copy. Component bindings are immutable within an
epoch; retirement records a tombstone without copying them. The ordinary non-epoch path still
reads and writes its local containers. All overlays merge back after scoped
workers join, including when an error or panic exits the epoch.

Workers retain the original equality relation, stable fields, component bindings
and pending membership throughout the epoch. Exact guard results therefore have
the same meaning as in a synchronous batch, even if the coordinator has since
retired a peer or changed a representative. They do not authorize a commit by
themselves: both union endpoints still invalidate dependent unread sources,
current liveness and pending membership are rechecked, and no new peer/birth or
opaque mutation may enter the window. The current result root is passed to the
shared collision commit separately from the immutable source-row inputs.

A bounded array of one-time result slots receives task outcomes. The compiler's
complete input footprint and the no-birth window permit fixed strided groups of
independent snapshot reads; at most one scoped job per configured worker is
spawned for the epoch. A small task-level input array projects plain borrows from
Prepared, whose Rc owners remain on the coordinator. No candidate fields are
materialized or copied during that projection.

Each lane writes only its own slots. The coordinator waits only for the next
ordered source, after completing any earlier pure child tasks, and borrows its
published answers directly. Out-of-order completion is represented by initialized
slots; there is no result channel, cloned answer payload or receive/reordering
pass. It may abandon a dependent suffix, but every reader continues and all
completed work is counted after the scoped join. A lane unwinding on panic
publishes abandonment to every remaining slot it owns before its panic is
propagated by Rayon. This releases a coordinator waiting on a missing answer.
Once all readers have joined, the epoch overlays are restored before the panic
is resumed. No unsafe Send/Sync implementation is used.

The optional `completion-overlap-probes` test feature holds the second reader
until the first effective union commits. A coordinator that waits for the entire
read batch cannot pass this test. A second probe panics that reader after the
union; retrying completion must preserve the prior commit and start a new epoch.
A third probe panics the first lane before its first answer; the coordinator must
exit its slot wait and restore the epoch. Disabling lane abandonment is a negative
control that fails this test's bounded timeout.
Production audit executables exclude these gates. Observed overlap and arrival
order are scheduling-dependent, separate from deterministic work counters.

This protocol removes the mandatory all-readers join before every ordered commit.
It retains an epoch-end join, ordered writes and the existing source-Run fences.
Snapshot handles, task projection, slot publication/read operations, activity
atomics, retained results, copied queue entries and overlay merge work are costs,
not inferred savings. The activity counter is retained across epochs; two atomic
updates bracket each reader lane. The sampled active-reader observation describes
an unfinished lane, not measured CPU utilization. Strided grouping can reduce
load balancing flexibility; fewer allocations alone do not establish a speedup.
Copies of whole touched queue tables can be expensive; compiler/Bake selection
must account for them. Independent source matching/publication and parallel
writers remain separate requirements.

### Stable signal bindings and component lifetime

A symbolic signal stores its first bound equality ID, not a cached canonical
representative. Union changes Parents and the existing boundary domain; it does
not rewrite component signals. Matching, influence and publication resolve the
binding through the appropriate current or snapshot Parents. Typed symbolic
wiring proves which columns share a signal; it does not prove equality between
distinct signals. Attaching a later frame must compare a retained binding's
current root with the actual input value before reusing that slot.

Capture the displaced native signal before inserting a union parent link.
After that insertion, resolving its retained binding could reach the new root
and wrongly reject the old domain. Boundary migration and shared-program
notifications still execute in their original order; no new reverse consumer
index is installed. Component retirement resolves every initialized binding to
its current root before removing the corresponding boundary record, including
signals whose last producer was deleted in an earlier stage.

The coordinator's live-fact counts are separate from the component records
workers read. Decrementing a count does not create a component overlay entry.
The last retirement removes current frame/domain membership and records one
component tombstone. A reader keeps the old component until the scope joins;
its answer still needs current liveness checks before committing. Component IDs
are not recycled. Shape extension and first-time binding are allowed only outside
an epoch; Component deliberately implements neither Clone nor EpochValue, so
ordinary slot mutation cannot silently introduce copy-on-write during a read.

Avoiding canonical writes can lengthen parent walks. Ownership binding roots,
port/guard reads, and their parent-directory probes are charged explicitly, as
are lifetime updates/growths. Probe counts include the terminating lookup and
are logical directory operations: an epoch overlay may perform two physical map
lookups for one probe. These counts do not establish a speedup or remove the
remaining boundary migration, queue copies, ordered writer or epoch-end join.

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
