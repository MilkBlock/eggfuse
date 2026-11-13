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
