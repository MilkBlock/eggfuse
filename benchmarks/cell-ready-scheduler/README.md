# Owned Cell continuations and a bounded ready scheduler

Scope: standalone Cell CPU runtime. Native egglog remains the sum-bits semantic
reference. This is not a claim of native egglog performance or full-core utilization.
Control: `83acd095` (runtime unchanged since `877ff5d2`).

## Opportunity from actual execution

The preceding Raytrace execution built 139,448 local constructor rows in 76,904
synchronous pieces, about 1.81 constructors per invocation. Moving additional
instructions into those pieces did not remove the coordinator's wait after each
piece. The rejected scalar-write extension had zero workload coverage.

The new path owns the writable continuation independently of the graph's published
input slots, then batches instances whose remaining constructor work has an exact
independence proof. Small Cells share a bounded queue and worker invocation; they
do not need artificially enlarged templates to enter the scheduler.

An initial constructor-only admission exercised 2,739 Raytrace jobs in 1,363
batches, with a peak of 64 ready instances. It was real concurrent dispatch but
covered too little of the previous 76,904 pieces. Final admission also allows
ordered, total effects after the independent constructors, as specified below.
This extension is exercised by regression fixtures; it has not established extra
coverage in these two workloads.
The final measurements and checks are recorded in [results.json](results.json).
These are operation/semantic checks, not a new performance campaign.

| Final execution work | sum-bits | Raytrace |
| --- | ---: | ---: |
| Local pool invocations, control → candidate | 299 → 240 | 76,904 → 75,530 |
| Queued jobs / batches | 86 / 27 | 2,736 / 1,362 |
| Flushes for pending dependencies | 4 | 1,277 |
| Global key lookups, unchanged | 14,054 | 4,037,109 |
| Uncalibrated net saved work (negative = added work) | −2,207 | −211,906 |

The queue is a validated scheduling checkpoint, not an established optimization:
it adds net work and still drains on most shared-root dependencies. The next
takeover must remove those waits or reduce admission costs. Runtime tests (136),
compiler/integration tests (103), forced hash/sieve-collision tests, feature/minimal
builds and README compile/run/repeat-one bench passed. Native sum-bits acceptance
is `pass`; both workload exports and ordered Run summaries match the control.

## One frame, public prefix, owned continuation

`FrameSlots::lease` moves the existing slot allocation into an immutable prefix.
The graph still reads it for retained parent projections; the job owns only the
writable continuation. Reattachment checks the prefix identity and that the public
side has not been modified. An unchanged unique prefix returns to its original
allocation when the worker joins. This is not a copied binding or a second fact
store. When an admitted tail needs a previously projected parent operand, its
actual value is captured once into the same frame and charged.

Queued jobs hold a shared compiled plan, necessary existing row handles and
their own slots. Existing `Effects` output arrays are uniquely borrowed by each job; the
coordinator retains the Rc owners. A single existing parent read epoch covers a
whole batch. No root directory is cloned. Original Cell lifecycle holds protect
parked public frames and retained parents, and resumption restores the original
source epoch and input certificate.

The ordinary synchronous fallback borrows its existing Cell directly. Both
transports execute the same generic constructor plan; only actual queued jobs pay
for prefix sealing, row handles and read epochs. An earlier all-owned draft charged
those costs to 76,904 Raytrace pieces despite admitting only 2,736 jobs; the final
implementation removes that unnecessary ownership work outside queue coverage.

The batch has a join before graph registration. It does not permit arbitrary
concurrent union or graph mutation. Read-only slot ownership tests separately
exercise two owners while the live parent directory changes.

## Compiler proof and boundaries

The checked Cell definition, existing static aliases and operator-site ranges
supply the proof; there is no runtime fact graph or producer-to-consumer list.

1. An ordinary source constructor actually creates a fresh implicit result in
   this Cell. Ownership of a row or a constructor name alone is insufficient.
2. Each following admitted constructor has an input produced freshly within
   the tail. Its exact operator candidate range contains no constructor after
   that fresh producer. It therefore cannot reuse an external or preceding local
   key. The proof is inductive and rejects dynamic local-dedup ambiguity.
3. All remaining non-alias constructor operations are covered. No unaccounted
   constructor after an ordered effect may be hidden by the tail proof.
4. The source template contains only constructors, Copies, typed Eq unions, and
   integer function writes with an exact `old`, `new`, `min` or `max` merge
   expression. The latter cannot fail or allocate constructor identities.
   Mutable table callbacks, arbitrary primitives, unique/conflicting writes,
   constructor assignments, Hide and Panic keep the ordinary source path.
5. Unions and writes are never executed by these workers. They retain their
   original source order, and a later instance cannot cross its ordered effect
   while earlier instances remain parked. Query snapshots and Run publication
   boundaries do not move.

These conditions allow a later Cell's independent constructor seed to be resolved
while an earlier tail is parked. The earlier tail's keys contain its fresh ports;
future captured inputs cannot already name those ports. If a later seed reuses an
earlier new root, the first dependent key is detected against the sorted parked
Cell IDs. The consumer is suspended, earlier tails finish, and that exact source
operation resumes against their actual results. A worker never blocks on that
consumer. Cell IDs are still allocated in source order.

There is an intentional commuting of independent seed construction with earlier
isolated tail construction. This is not a promise of identical within-Run birth
trace order. Canonical results, original Cell identities, ordered mutable effects,
matching snapshots and published Run states are preserved. The total-effect
restriction prevents an early future seed from surviving a source failure that
should have stopped before it.

Existing Cursor/history handoffs retain their direct path. Unproved local tails
retain the existing exact local-dedup executor, including its useful dynamic
reuse; a failed queue admission does not replace that executor with a full RHS
replay. Refresh after draining a queue is restricted to those earlier isolated
tails and non-birthing ordered effects. Other graph births or changed roots still
invalidate the ordinary freshness window.

## Actual scheduling and accounting

The source driver admits at most 64 parked owners, forms jobs from their existing
frames, and shares one read epoch and pool invocation. Worker results go directly
into their existing output slots. The coordinator registers actual row allocations,
restores each owner and completes its remaining effects and publication in source
order. Completed-but-not-yet-published owners stay in that same bounded queue.

`worker_batches` counts actual pool invocations, including a single invocation
for a whole ready batch. `worker_operations` counts completed constructor work;
it is not a committed-mutation counter. `committed_rows` counts registration.
The scheduler separately reports jobs, maximum ready width, dependency/effect
flushes, fallback certificate checks and worker participation. Participation on
four workers does not establish useful utilization or throughput.

New costs include public-frame headers and prefix allocations, plan/row handles,
operand captures and dependency checks, task/result containers, lifecycle holds,
root epochs, queue storage and completion waits. Shared output slots avoid a
second operation log, but pending row metadata remains necessary. Work-credit
parsing rejects unknown schemas and missing required counters; outcome subsets do
not earn another saving. The equal-weight work score is uncalibrated.

## Reproduction and acceptance

Use the same frozen sum-bits/Raytrace programs and flags as
[the control](../cell-local-births/README.md). Freeze the feature runtime before
README's default-feature builds. Reuse the saved native exports; replace only the
candidate CPU sum export in the semantic directory.

```sh
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-ready-scheduler/check.py ROOT PRIOR RESULTS.json
cargo cell-compile --case sum-bits --output ROOT/readme-program
cargo cell-run --program ROOT/readme-program/program.json --output ROOT/readme-run
cargo cell-bench --program ROOT/readme-program/program.json --repeat 1
```

Tests cover independent batches, a shared new root that parks the consumer, actual
foreign constructor reuse, ordered scalar writes, following union/repair and Entry
publication, source failure boundaries and dynamically equal local keys. Source
Run snapshots and matched inputs are compared directly in integration tests.
The write audit also compares exact effective-write digests including original
source ordinals. Suspension carries that ordinal with the owner, rather than
attributing an earlier completion to the most recently admitted instance.
Full-workload checks require conserved logical effects, all ordered Run summaries,
exact final exports and the unchanged native sum-bits validator's `pass`.

Still outside this takeover: arbitrary concurrent shared writes/repair, callbacks
with unproved dependencies, and elimination of all remaining source waits. This
scheduler removes a real class of per-Cell waits; it is not completion of the
larger full-core execution objective.
