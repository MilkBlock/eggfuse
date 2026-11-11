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
