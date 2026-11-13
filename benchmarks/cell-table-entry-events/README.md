# Independent index and Entry completion

This experiment uses the actual standalone Cell CPU, not native egglog. The
frozen control is current-branch commit `57813edd`. The rejected Entry map-update
experiment `9b107d45` is not included in either lane.

## Opportunity from the current catalog

The preceding execution showed that `Expr-size` accounts for 1,057,016 owner
publication rows. A table task updates query indexes and Shared Entry states
one after the other, then releases compiled Sieve conditions. Those conditions
read the index; they do not read the Entry state. The existing compiler-owned
table partitions and static condition edges already prove those owners are
independent within a sealed publication window. A larger Bake catalog is not
needed to establish this particular dependency fact.

The candidate removes the Entry completion prerequisite from index readers.
For sufficiently large tables with both kinds of work, a worker sorts the
existing witness header array once, then joins two tasks in the same pool:

* The index owner updates the existing column/range/neighbor indexes and
  immediately releases their compiled condition readers.
* The Entry owner reads the same immutable Graph and updates the original
  Entry state, including pending notifications from earlier Runs.

The condition tasks may finish while the Entry owner is still running. One
large changed table can use multiple workers; multiple changed tables are no
longer a prerequisite. Small tables, one-thread execution and tables with only
one kind of owner retain their combined path. No new row snapshot, index,
binding registry or per-producer consumer list is introduced. Repeated reads
are permitted and charged, rather than hidden as "free" parallel computation.

## Obligations that remain live

The shared immutable Graph borrow and the Run visibility fence survive until
both owners and all dependent conditions finish. Query consumers cannot see
partially refreshed Entries. Index versions advance only after both owners
succeed. Errors retain source table order, then original witness order; an
index error precedes an Entry error at the same row, and older pending Entry
notifications follow current rows. If an Entry task fails after its index has
released conditions, the speculative condition caches are invalidated before
returning the error. The existing index/Entry allocations remain the owners.

This does not discharge mutable reads across Runs. The compiler has no proof
that a later mutable value or epoch is unchanged. Cold enumeration, residual
matching, delta ownership, retirement, source RHS effects and repair remain
authoritative. This change removes an unnecessary dependency within publication,
not the final source visibility fence.

## Work and cost accounting

New counters report split Entry tasks/rows, single-table split batches,
additional current-row reads, total split Entry reads, and index completion
before its Entry owner. That last event also includes an Entry task which has
not started yet. It samples the Entry completion flag immediately before
invoking the index handoff callback; it does not count conditions proved to
have executed before the Entry finished, nor measure CPU utilization. Worker row counts are
work assignments, not committed mutations. Table task times include their
join residence and overlap with condition/Entry tasks; do not sum them as CPU
time. Full inference timing is the acceptance measurement.

Task-header capacities remain charged. Sorted witness-buffer capacities are
now reported for both combined and split paths; the buffer already existed in
the control, so its entire size is not a new allocation. The split path adds a
Rayon join and an independent Graph read for current wakeups. Existing Sieve
worker arrays now grow without truncation when a later batch runs inline;
historical truncated arrays cannot be compared as worker load distributions.

## Validation and reproduction

Run all builds/tests/work exports through the shared `eggfuse-job` compute queue.
Use `benchmarks/cell-query-fragments/validate.py CHECKOUT CHECKS TARGET` for the
runtime/integration checks, legacy/all-feature compilation, README commands and
frozen release binary. Use `benchmarks/cell-rhs-boundaries/reference.py CONFIG
OUTPUT BINARY ACCEPTED CONTROL_COMMIT` to produce each lane's work exports.
This preserves exact states, all source Run summaries and logical effects, and
binds the unchanged native sum-bits acceptance proof to the fresh CPU state.
Raytrace remains a differential runtime check, not a new native contract.

`check.py CONTROL CANDIDATE CHECKS OUTPUT.json` records the work deltas after
these checks pass. The timing comparison runs from the committed clean candidate
checkout with absolute artifact paths, using `benchmarks/raytrace-parallel/quick.py`
as one timing job. Finish every control workload before starting any candidate
workload; never interleave lanes or other managed jobs with samples.

Tests include a deliberately unfinished Entry owner: its condition must run
before it can finish. A second case reports an Entry failure after index
completion and requires cache invalidation. The real single-table integration
case uses a partial-key index, late mutable updates and independent Entries;
native checks, every-Run graph snapshots and binding/effect ordering must match.

## Work checkpoint

Candidate `e97ebde4` passes 211 runtime unit tests, 111 compiler integration tests,
legacy/all-feature compilation and all three README Cargo commands. Fresh
sum-bits and Raytrace exports match the reference states, all 1,428 and 16,883
Run summaries, and logical effects. The unchanged native sum-bits contract
validator passes with its CPU-export hash equal to the fresh sum state.
Entry updates, predicates, retirement, consumer delivery and Sieve logical
work remain identical. The new path does not activate on sum-bits.

Raytrace splits 1,896 Entry tasks covering 1,896,796 publication rows. This adds
666 single-table parallel batches: pooled publication calls rise from 783 to
1,449 and formerly inline publication rows fall from 771,570 to zero. These
are publication assignments, not a claim that all runtime work is parallel.
The ready-flag observation described above occurs 1,269 times.

The cost is 1,764,849 additional current-row reads; total parallel-publication
reads rise from 1,996,513 to 3,761,362. Accumulated table-task header capacity
rises from 4,365,680 to 4,618,240 bytes. Existing sorted witness-buffer capacity
is 33,186,720 accumulated bytes, with the same 2,073,562 ordered headers as
the control. These are capacity sums, not peak memory or allocator call counts.
Diagnostic work-run phase times are not used as performance acceptance.

## Sequential timing: Raytrace gain, unresolved sum-bits regression

The initial timing job 43 was interrupted after the first measured control sum
sample when another unmanaged `emit_cell_source` appeared. Its retained evidence
is recorded in `timing-attempts.json`; none of its samples are reused. Once the
external corpus driver exited, job 46 completed the ordinary five-sum/three-Ray
checkpoint. All 48 boundary guards were clear. It reported sum 25.771 to 27.629 ms
(+7.21%) and Raytrace 6.074 to 5.337 s (-12.14%). The control Raytrace range was
5.451–6.082 s, so this first apparent gain was not treated as stable evidence.

Before another sample was run, the follow-up was fixed at 15 sum and 7 Raytrace
measurements per lane, still with one warmup each. The harness preserves those
counts through queue submission and records them in each lane; six harness
tests pass. Shared timing job 48 completed all control workloads before any
candidate workload. All 104 sample/group guards were clear. No compilation,
profiler or other managed job was interleaved. Every timed state, Run summary
and logical effect matched the frozen references.

| Inference median | Control `57813edd` | Candidate `e97ebde4` | Change |
|---|---:|---:|---:|
| sum-bits, 15 samples | 26.686 ms | 27.699 ms | +3.80% |
| Raytrace, 7 samples | 5.636 s | 5.336 s | -5.33% |

Raytrace's query-update phase median falls from 1.192 to 0.984 s, consistent with
the intended publication change. Other phase medians also move; do not attribute
the entire whole-inference difference solely to the new dependency split. Phase
medians are independently calculated and must not be summed as a median run.

Sum-bits executes zero split tasks, zero parallel-publication batches and zero
staged Sieve batches in both versions. Its query-update phase median increases
by about 112 microseconds, RHS by 233 microseconds and search by 614 microseconds.
This locates most of its observed change outside the new path but does not prove
the regression is harmless or explain its cause. Binary layout, common-path
cost and grouped-run environment drift remain unresolved possibilities.

**The code remains on `codex/table-entry-events`; it is not merged into the
active runtime branch while the sum-bits regression is unresolved.** The two
completed trials remain separate in `timing-short.json` and `timing-fixed.json`,
with individual samples and checksums/locations of all full observations.
No samples are discarded to obtain an improved median. These grouped trials
are not an interleaved statistical-significance test, an overall CPU-utilization
measurement or a comparison against every historical configuration.

## Common-path and identical-binary diagnosis

`codegen.py CONTROL CANDIDATE OUTPUT` inspects the frozen arm64 binaries through
the compute queue, verifies their manifest hashes and saves the selected assembly.
It does not run either workload. `codegen.json` records job 60's result:

| Method | Control instructions / initial stack | Candidate instructions / initial stack |
|---|---:|---:|
| Publication::publish | 2,023 / 2,656 B | 2,315 / 2,736 B |
| publish_finished_tables | 401 / 192 B | 401 / 208 B |
| Executor::run | 3,539 / 1,264 B | 3,579 / 1,264 B |

The instruction totals include every branch, including paths sum never enters.
They are not executed instruction counts. The small owner-count loop still
precedes rejection; the larger publication implementation is inlined into its
caller. The additional 80-byte publisher frame and unchanged main Run frame do
not establish the cause of the approximately one-millisecond sum difference.

Timing job 58 used **the identical frozen control binary in both lanes**, with
15 sum and 7 Raytrace samples per lane, one warmup, and the same complete-first-
lane ordering. Counts and the diagnostic purpose were fixed before execution.
All 104 guards, frozen states, Run summaries, effects and the existing native
sum acceptance passed. The result is retained in `timing-aa.json`:

| Same binary in both lanes | First lane | Second lane | Change |
|---|---:|---:|---:|
| sum-bits | 27.718 ms | 26.224 ms | -5.39% |
| Raytrace | 5.704 s | 5.801 s | +1.70% |

This demonstrates variation even without a code change. It does not prove the
earlier candidate is regression-free, identify thermal or OS activity as the
cause, or provide a correction to subtract from a different trial. In particular,
the earlier 3.80% sum difference cannot responsibly be assigned entirely to the
new synchronization. The candidate remains experimental, and its structural
work reduction remains distinct from a stable whole-runtime speed claim.

## Small-batch admission follow-up

The actual sum execution rejects 657 publication attempts before constructing
parallel tasks. Those attempts still inspect column/range/neighbor owners and
Entry readiness to count eligible rows. The sealed change-map lengths provide
an upper bound before any owner lookup: fewer total rows than the grain means
fewer eligible rows than the grain. This is an exact subset argument over the
existing notification storage, independent of mutable Entry readiness.

The follow-up uses that bound, stopping when it can no longer prove rejection,
and keeps the large task implementation in a separate non-inlined method.
Covered small batches remove the owner tests; other batches retain the exact
owner count, canonical-read proof and original publication path. New metrics
charge bound table visits and record rejected batches and avoided owner tests.
No new retained admission map, consumer list or binding representation is added.

This uses work from the last catalog rather than adding another Bake catalog.
Template facts still identify the real consumers; they do not prove mutable
values, retirement or cross-Run readiness unchanged. No scheduled block switch
can erase those remaining obligations. The bound does not authorize early
visibility or change publication, repair, residual or delta semantics. This
is a separate preparation optimization, not a claimed explanation of the
earlier timing regression.

Commit `0dfdfb2a` on `codex/table-entry-admission` passes the same 211 runtime
and 111 integration tests, legacy/all-feature checks and three README commands.
Fresh workload exports preserve exact states, all source Run summaries and
logical effects; the unchanged native sum contract passes. Its control for
this follow-up is experimental parent `e97ebde4`, not the independently moving
active runtime branch. Reproduce exports with the existing `reference.py`, then
run `check.py PARENT FOLLOW_UP CHECKS OUTPUT.json`; it now accounts for the
duplicate-read delta when the parent already has independent Entry owners.

| Admission work | sum-bits | Raytrace |
|---|---:|---:|
| New change-map length visits | 1,311 | 15,158 |
| Batches rejected by the upper bound | 657 | 7,646 |
| Table owner eligibility evaluations removed | 1,311 | 12,339 |
| Existing total small-batch rejections | 657 | 7,878 |

An owner evaluation is one original table predicate, with short-circuited
index/range/neighbor/Entry checks; it is not four guaranteed saved probes.
Raytrace still has 1,449 publication batches, 1,896 split Entry tasks and
3,761,362 parallel row reads. The preparation change does not alter that work.
The three diagnostic counters add 24 inline bytes to publication statistics.

`admission-codegen.json` records that Publication::publish now has 546 static
instructions and a 560-byte initial frame, versus 2,315 and 2,736 in its parent.
Much of that code moved into the separate large-batch method; it was not deleted
from the binary. Actual deleted work is the eligibility evaluation count above,
with the new length visits, counters and large-batch call charged separately.

Timing job 65 completed one fixed 15-sum/7-Ray comparison against `e97ebde4`,
with all 104 boundary guards clear and the same state/Run/effect checks passing.
All parent samples preceded every follow-up sample. `admission-timing.json`
retains every sample and the raw observation checksum:

| Inference median | Parent `e97ebde4` | Follow-up `0dfdfb2a` | Change |
|---|---:|---:|---:|
| sum-bits | 27.657 ms | 26.851 ms | -2.91% |
| Raytrace | 5.432 s | 5.408 s | -0.45% |

Both point estimates improve, but their magnitude does not establish a stable
whole-runtime speedup in light of the separate identical-binary diagnostic.
This change removes demonstrable preparation work; it does not solve the
remaining serial RHS/repair work or establish full worker utilization. The
candidate remains on its experimental branch. Integration with the moving
active branch requires a fresh reference for that branch, not comparing these
numbers to older runs or subtracting the A/A deltas. There was no repeat-until-
green trial for this follow-up.
