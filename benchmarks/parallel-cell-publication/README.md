# Repaired Cell outputs: parallel index publication

Control: `c6823564`. This is the **standalone Cell CPU**, not native egglog.
The change extends actual worker responsibilities beyond query completion;
full CPU utilization and a throughput gain remain unproven. The feature and
runtime option are disabled by default. No new throughput campaign is run.

## Opportunity and proof

The preceding complete Raytrace execution still published 2,319,660 column
changes, 1,124,415 neighbor-cache changes and 57,325 range-index changes on the
coordinator. These overlap: the ordinary publisher resolves a changed witness
once and updates all its readers. Adding those counts would overstate work.
Its Run-wide query queue did not take over this maintenance.

The same Cell definitions still determine query projections and the indexes
demanded by their execution. At the existing post-repair boundary, each table's
current column maps, range axes and demanded neighbor ports have one owner.
These existing storage partitions can be moved to exclusive worker tasks.
This is a storage-ownership proof, not evidence that different Cells cannot
construct or union the same node. RHS/union effects have already occurred.

There is no new Ripsat equivalence or cross-Run block-switch credit here.
The earlier catalog's executions identify the remaining publication work;
the change discharges the covered serial index updates at their existing
boundary. It cannot pull a later Run's mutable reads earlier or eliminate
publication merely because an earlier Cell has completed.

## Implementation and live obligations

`parallel-publication` plus `--parallel-publication --query-workers N` uses the
existing pool. It does not require enabling residual queries at runtime, though
its feature depends on their shared, thread-safe candidate-domain storage.

- Borrow authoritative rows after pending unions, dirty rows and ownership
  completion are drained. Changes and garbage intentionally remain until
  publication completes; the immutable borrow prevents mutation or collection
  while tasks run. Ordinary query admission retains its stricter settled gate.
- Move each existing column/range/neighbor partition into one task. Do not
  clone maps, graph snapshots, bindings or rows into another maintained graph.
  Query leases retain their existing Arc domain ownership.
- Run the original writer updates on the worker. Each changed row is resolved
  once and shared among that task's writers; retirement needs only its witness.
  Exact changes invalidate leases even when fingerprints collide.
- Join before Sieve publication or any later query. Restore partitions and
  column-change notifications in original table order. Cache versions advance
  only after all changes in their task succeed. Failed tasks retain old versions
  and their partially updated storage is restored before returning the error.
- Views, Entry/Spine publication, graph writes, repair and garbage collection
  remain on the coordinator. Stable noncanonical fields, owned Unit storage
  requiring specialized reads, and unfinished completion keep the old path.
  Family-survey builds reject enabling this option explicitly.

Small publications (fewer than `max(query_grain, 256)` indexed changes) retain
the old path. One partition executes inline; multiple partitions use the pool.
An N=1 configuration exercises the ownership path inline. Header-only tables
need no worker row read and do not restrict the required read-table proof.

## Costs and interpretation

Each partition adds a task record and moves map owners out and back. Worker
column notifications use a buffer owned by the existing index; restoring it
drains notifications into the original ordered stream and retains only empty
capacity for reuse. The report counts buffer growths, cumulative capacities,
peak retained notification bytes, per-worker rows/tasks and per-table work.
These exclude existing index storage, allocator metadata and pool bookkeeping.
`worker_task_seconds` and `table_task_seconds` are task wall residence, not CPU
time or proof of utilization. New storage is charged even when work counts
match the control exactly.

The covered coordinator row/update loop is omitted. Queries, actual graph
mutations and the number of mandatory index updates are not reduced. A logical
rule match is not a committed mutation. One large table remains one task;
cross-table parallelism alone cannot guarantee balanced workers.

## Complete execution evidence

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Total changes requiring index publication | 4,966 | 2,319,660 |
| Changes updated by worker threads | 0 | 1,364,230 |
| Changes in single-partition inline tasks | 0 | 772,626 |
| Small publications retaining the ordinary path | 657 | 7,879 |
| New-path batches / calls to the pool | 0 / 0 | 1,448 / 781 |
| Existing storage partitions moved and restored | 0 | 4,418 |
| New-path column / range / neighbor updates | 0 / 0 / 0 | 2,136,856 / 44,535 / 1,057,016 |
| New task-record capacity bytes, summed | 0 | 2,615,456 |
| Notification-buffer growths | 0 | 460 |
| Peak retained notification capacity bytes | 0 | 3,042,048 |

Raytrace moves **58.8%** of required index-publication rows onto workers.
The new ownership path covers 92.1% including inline tasks. Neither fraction
is a speedup. Worker row counts are 489,622 / 434,372 / 237,171 / 203,065;
rows need not cost equally and these totals do not establish simultaneous
utilization. `Expr-size` alone accounts for 1,057,016 new-path rows. The largest
single partition contains 27,315 changes; one-partition batches still execute
serially. Sum-bits never passes the size gate, so it supplies a regression
check, not workload evidence for this takeover.

Every ordinary graph counter, total key lookup count, Sieve/Free Join/Entry
schedule report, publication count and indexed-column coverage agrees with the
control. Exact states and ordered Run signatures agree for 1,428 sum-bits Runs
and 16,883 Raytrace Runs. Required index updates are moved, not eliminated.
[results.json](results.json) retains all new costs and per-table work, including
task wall residence with the limitations above; no throughput comparison is
made from these single diagnostic executions.

Validation: 34 integration tests, including a native-checked fixture that
requires actual pool execution through late values, union and deletion/rebuild;
forced zero-bit fingerprints; 101 runtime unit tests; minimal/all-feature
checks. The new unit tests cover publication before change draining, rejection
of pending unions, and empty-buffer reuse. The unmodified native sum-bits
validator returns `pass` / exit 0. README compile/run/bench with repeat 1 is a
command smoke only, not a throughput measurement.

## Reproduction

Use the same frozen `cell-fixed-reads` sum-bits and Raytrace programs as the
control. Freeze the executable before another build can replace it and use
fresh output directories:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
cp target/release/eggfuse-cell-runtime ROOT/runtime
ROOT/runtime --program SUM_PROGRAM --output ROOT/sum --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
ROOT/runtime --program RAY_PROGRAM --output ROOT/ray --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/parallel-cell-publication/collect.py ROOT PRIOR_RUN_QUEUE_ROOT RESULTS.json
```

`ROOT/semantic` uses the unchanged saved native contract plus the new sum-bits
export. The collector reads existing reports and does not time workloads.
Full Raytrace agreement remains a relative regression check, not an independent
native proof. Raw exports, binaries and logs remain ignored under
`out/parallel-cell-publication`.

## Residual winner completion on workers

Control: `73c40b25`. A new five-second stack diagnostic of that frozen binary
still finds the four query workers parked in 1,606 / 1,607 / 1,614 / 1,618 of
1,705 samples each. These are wall-stack counts, not CPU utilization. Of 1,704
main-thread inference samples, matching has 595 inclusive samples, publication
373, Entry batches 318, and residual Frame steps 121. Counts overlap. Progress
logging accounts for 95 samples; an external compilation was also active.
The complete 16,883 Run signatures, final state and graph counters agree with
the saved execution. This diagnostic does not establish a throughput change.

Beyond the still-uncovered query hosts, the complete execution reports
4,460,810 residual winner comparisons on the coordinator. Rule input layouts
are already compiled by their Cells; every rule owns its answer instances.
Once query workers join, these independent vectors can be completed in parallel
without any graph write or new cross-Run proof. The new path transfers the
existing residual and final RHS vectors to exclusive per-rule tasks on the
same pool. Each task merges ordinary residual answers, stably sorts by the
original input key and source position, and deduplicates into its original
RHS vector. Fully tied sources retain expansion order. The coordinator omits
the old sorting loop, then performs the existing point/Spine merge and ordered
RHS commit after all tasks join.

The number of comparisons and required winners does not decrease. There is no
new Ripsat composition or credit for crossing a Run. This is actual execution
takeover, not a second query catalog or another binding representation. It
preserves residual coverage, delta/watermark ownership, actual witnesses and
the original source-order winner. There is no per-comparison atomic counter:
each task retains its existing local count, merged after join.

Parallel completion requires at least two rule vectors with `query_grain`
candidate answers each, and at least
`max(worker_count * query_grain, 256)` candidate answers in total. Other Runs
execute the same operation inline. One large rule is still indivisible. New
costs are a temporary task-header vector, another pool join for qualifying
Runs, task timing, and moving existing vector owners. Reports charge
`merge_task_capacity_bytes`, `merge_prepare_seconds`, `merge_execute_seconds`,
`merge_pool_calls`, inline tasks, per-worker rows/tasks and task wall residence.
The existing `merge_capacity_bytes` and `order_comparisons` remain comparable.

The semantic fixture compares all Run states and ordered bindings while a
point Cell writes a value also read by two residual rules. It requires the new
winner pool path to execute. A unit test separately distinguishes direct vs
ordinary answers, earlier vs later pivots, and completely tied expansion
answers. Small sum-bits Runs are regression coverage; their presence alone
does not prove parallel completion occurs.

Complete execution evidence is in [winners.json](winners.json). Raytrace sends
488,952 candidate answers through 2,534 worker rule tasks in 277 pool calls;
11,870 small or single-rule tasks remain inline. Its 4,460,810 comparisons and
114,950,464 cumulative answer-capacity bytes are unchanged. New temporary task
headers sum to 2,659,776 capacity bytes; persistent per-rule completion
metadata adds 13,968 bytes to each workload's plan capacity. Sum-bits has 1,438 inline
tasks, zero pool calls, and 250,432 new cumulative task-header capacity bytes.
No copied binding or extra query is counted as a saving.

The full states, ordered Runs, graph counters, key reads, filters, publication
counts and comparison counts agree with the control. The unchanged native
sum-bits validator passes. The initial full Raytrace diagnostic spends about
0.038 s inside winner completion including its pool calls; this is a small
remaining component, not evidence that this change can saturate the workers.
[winner-profile.json](winner-profile.json) retains the preceding sampled stacks
and artifact hashes, with their coverage limits.

Validation: 34 integration tests, 102 runtime unit tests, forced zero-bit
fingerprint residual/publication fixtures, minimal and all-feature checks, and
README compile/run/bench command smokes pass. The smoke benchmark uses repeat 1
and is not throughput evidence. Final residual tests and complete exports use
the admission gate that requires two nontrivial rule vectors.

`profile.py RUNTIME PROGRAM SAVED_RUN OUTPUT` reproduces the separate stack
diagnostic using a saved complete execution as the semantic reference; it
does not require inventing a timing sample. `measure.py CURRENT BEFORE_MERGE
LAST_CHECKPOINT SUM_PROGRAM RAY_PROGRAM OUTPUT` runs the five-implementation
checkpoint with one warmup and seven sum-bits / five Raytrace samples per
lane. It compares the preceding serial checkpoint, current serial, preceding
four-worker publication path, and the current path with one/four/eight workers.
All samples and semantic signatures are retained by the shared process harness.
The one-worker path runs inline, so comparisons also charge pool/dispatch costs.

## Five-implementation throughput checkpoint

Candidate: `aa2161e2`; preceding publication/winner control: `73c40b25`;
preceding timed serial checkpoint: `e2da3a05`. Apple M3 Max, 16 logical CPUs.
Current and preceding publication binaries use
`cell-absorption,view-ports,parallel-publication`. The older checkpoint retains
its frozen normal `storage-metrics,parallel-entry-filters` build. All lanes use
the same frozen program per workload and enable absorption, repair ports and
Entry publication. The same current executable supplies serial/1/4/8 lanes.
No allocation instrumentation or `CELL_CPU_PROFILE` is enabled during timing.
The current serial comparison includes dormant feature/layout/codegen costs.

One warmup and seven sum-bits / five Raytrace repetitions per lane are
interleaved in a fixed shuffled order. No own build or diagnostic runs overlap
timing; process checks did not observe Cargo/rustc during this campaign. Other
system activity is not controlled. All samples, warmups and execution order
are retained in [timing.json](timing.json), including the 10.914 s Raytrace
one-worker process sample. Medians of separately measured phases need not sum.

| Configuration | sum-bits inference | sum-bits process | Raytrace inference | Raytrace process |
|---|---:|---:|---:|---:|
| Preceding checkpoint, serial | 15.773 ms | 121.909 ms | 6.294 s | 9.130 s |
| Current binary, serial | 17.688 ms | 127.962 ms | 6.050 s | 9.064 s |
| Before winner change, 4 workers | 21.418 ms | 129.065 ms | 6.027 s | 8.960 s |
| Current, 1 inline worker | 17.948 ms | 125.775 ms | 6.354 s | 9.282 s |
| Current, 4 workers | 20.559 ms | 130.404 ms | 6.017 s | 8.883 s |
| Current, 8 workers | 24.832 ms | 133.676 ms | 6.965 s | 9.958 s |

Paired inference ratios (trial/control; lower is faster) with 95% paired
bootstrap intervals:

| Comparison | sum-bits | Raytrace |
|---|---:|---:|
| Current 4 / preceding checkpoint serial | 1.263 [1.179, 1.565] | 0.997 [0.880, 1.064] |
| Current 4 / current serial | 1.224 [1.162, 1.325] | 0.977 [0.959, 1.043] |
| Current 4 / before winner change 4 | 0.946 [0.896, 1.109] | 0.998 [0.860, 1.081] |
| Current 4 / current 1 | 1.118 [1.026, 1.349] | 0.943 [0.863, 1.084] |
| Current 8 / current 4 | 1.181 [1.059, 1.287] | 1.153 [1.064, 1.260] |

The five changes **do not establish an overall Raytrace speedup**, and
sum-bits regresses under four-worker activation. The last winner change alone
does not establish either a gain or a regression against its preceding
four-worker binary. Eight workers regress both workloads here. Admission
thresholds depend on worker count, so these are end-to-end configurations,
not pure scaling of an identical task partition. The features remain opt-in;
do not promote this path or claim success from the amount of transferred work.

Raytrace winner completion itself has median wall residence 44.2 ms inline,
35.4 ms with four workers and 37.1 ms with eight, including its pool calls.
This is too small a component to explain a large overall improvement. Current
four-worker phase medians remain search 2.541 s, RHS 1.729 s, index update
1.161 s and repair 0.550 s. These whole phases include serial and worker work.

A separate final five-second stack capture records 1,622 / 1,621 / 1,641 /
1,657 parked samples out of 1,737 for each worker: 93.3%–95.4% wall-stack
residence, not CPU percentages. Main-thread inference inclusive samples still
include matching 618, publication 355, Entry batches 342, residual Frame steps
108, and Free Join admission 104. They overlap; progress logging and sampling
perturb this window. Complete-process average core use has median 1.016 for
four workers and 1.106 for eight, including load/export/reporting. Neither is
an inference-only utilization metric. **The full-utilization goal is unmet.**

The next priority is the substantial serial query preparation and uncovered
Cell execution, not more winner shards or threads. In particular, current
residual admission excludes an entire rule when its Spine is active, while
source Entries may already distinguish owned continuations from uncovered
queries. Any per-Entry takeover must preserve the source coverage count,
Spine winner priority, residual ordering, existing absorption/prefix reuse,
and Run visibility; merely removing that guard would be incorrect. The
observed stack samples identify the broader host bottleneck, not a measured
cost attributable solely to this admission restriction.

All 84 timed/warmup processes preserve their workload's exact final state and
ordered logical/executed Run signature, with identical actual constructor
requests, function updates, unions and created facts. The new normal sum-bits
export passes the unchanged native acceptance contract and matches the timed
state. Raytrace checks remain relative, not an independent native proof.
Raw files are under `out/parallel-cell-winners`. Reproduce the summary after
`measure.py` and the separate `profile.py` run with:

```sh
python3 benchmarks/parallel-cell-publication/collect_timing.py ROOT benchmarks/parallel-cell-publication/timing.json
```
