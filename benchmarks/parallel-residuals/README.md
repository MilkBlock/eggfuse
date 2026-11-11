# Residual Cell queries on the existing worker pool

Control: `e2da3a05`. This is the **standalone Cell CPU**, not native egglog.
This change extends actual worker coverage; it establishes neither a speedup
nor sustained CPU utilization. Both the feature and runtime option are opt-in.
No new throughput campaign was run.

## Opportunity and replaced work

The preceding [Entry-filter experiment](../parallel-entry-filters/README.md)
left workers waiting in 97.3%–98.2% of its sampled stacks. Main-thread samples
still included Free Join admission and residual query enumeration. Moving
millions of cheap predicates had not moved enough of the expensive work.

The existing typed Cell Query proves a connected, single-expansion traversal;
the existing Free Join Entry plan supplies its necessary projections. At a
settled source-Run boundary these memberships, canonical fields and mutable
function values can be borrowed until workers join. No later Run is pulled
into this snapshot. There is no new cross-Run completion certificate, learned
Ripsat equivalence or Bake credit in this change.

`parallel-residuals` and `--parallel-residuals --query-workers N` enable:

1. Borrow the selected columns from the existing query index. Do not copy rows
   or build another membership index, runtime fact graph or subscriber list.
2. Omit coordinator `FreeJoin::admit` for admitted Entries. The worker performs
   those necessary checks and singleton delta rejection before query execution.
3. Execute the original Cell Query's point reads, guards and one expansion.
   Reuse the admission's expansion domain when available; check actual fields,
   visibility and delta ownership. Fingerprint collisions only enlarge scans.
4. Return the ordinary owned Instance directly to the existing match merge/RHS
   path. The coordinator omits its original residual `Frame::start/step` for
   these Entries. Query input sorting and deduplication remain authoritative.

Small batches stay inline. Indexed chunk collection preserves Entry order and
error selection across chunks. The mutable graph and its `Rc` owners never
cross threads. Existing decoded function fields are borrowed through their
shared storage, including after mutation or deletion/recreation.
Residual tasks are grouped by the existing kernel/pivot and chunked Entries;
this does not yet share computation across multiple Entries of a physical Cell.

Only candidate-domain `Rc<Vec<Dependency>>` changes to `Arc` in feature builds,
so the prepared index buckets can be borrowed safely. Lazy column creation
remains on the coordinator. This imposes atomic reference-count overhead even
when this binary's runtime option is disabled; a future throughput comparison
must also retain an old feature-disabled binary.

## Coverage and obligations still live

The compiled metadata records table/column access, not another query program.
Current admission excludes active Spine consumers, checked prefix routes,
absorption-capable queries, sum/range narrowing, unit-owned storage, stable
noncanonical constructor fields and scoped completion. Those paths retain
their current implementations and proofs. Per-read structural/family audit
builds reject this option explicitly.

Residual enumeration, actual returned witnesses, retirement, current mutable
values, per-rule watermark and source-Run visibility remain required. All
workers finish before RHS writes. RHS, union, repair, publication and the
remaining Entry organization are still coordinated serially. An instantiated
Cell query is not a committed mutation or a completed future-stage Cell.

The new path bypasses some ordinary PointPorts/Neighbor cache hits. It also
builds temporary borrowed Entry headers and per-chunk answer vectors. Removing
old admission/domain materialization does not make these new costs free.
Result capacity excludes each Instance's owned input/witness storage and pool
bookkeeping; it is not allocator usage or RSS.

## Full-workload diagnostics

Both frozen programs have 572 eligible static Entry plans. Counts below come
from complete executions; new-path totals include small batches run inline.

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Coordinator Free Join probes, before → after | 17,430 → 6,384 | 5,516,162 → 3,559,261 |
| New-path admission probes | 11,046 | 1,958,314 |
| New-path Entry executions | 10,348 | 1,881,965 |
| Entries actually on workers | 178 | 1,721,168 |
| New-path expansion rows passing ownership | 3,998 | 760,392 |
| Raw index references examined | 9,626 | 1,709,268 |
| Row reads before ownership/visibility checks | 4,333 | 826,235 |
| New-path successful matches | 3,397 | 560,582 |
| Total key lookups, before → after | 12,085 → 12,186 | 2,555,377 → 2,574,304 |

Raytrace thus adds **18,927 total key lookups** (about 0.74%). Ordinary shared
positive point hits fall from 21,650 to 2,723. The admission-probe decrease is
1,956,901, slightly less than the new path's 1,958,314 probes; do not call every
new probe a saved operation. This is work migration with costs, not a proof of
net work reduction.

Raytrace has 15,843 new-path batches and 41,191 chunks. Cumulative borrowed
Entry-header capacity is 75,278,600 bytes and answer-vector capacity is
84,864,960 bytes. These are summed capacities, not simultaneously live memory.
The single diagnostic records 0.00672 s preparation and 0.15801 s execution
including pool/inline calls and collection. Worker task residence totals about
0.263 s; it is wall residence, not CPU time. These observations are insufficient
for utilization or speedup claims and are not compared with the instrumented
control's timing.

The Raytrace control reuses the saved complete Entry-filter profile. Its filter
option moves predicates without changing their logic; the new candidate keeps
them on the coordinator. Sum uses the disabled development build. Exact
report/program/state hashes and all new-path counters are in `results.json`.

## Acceptance

- 32 integration tests pass, including two native-checked fixtures that compare
  every Run snapshot and ordered successful binding through mutable updates,
  late inputs, union and deletion/recreation. They assert actual expansion
  execution. Forced zero-bit query fingerprints also pass both new fixtures.
- All 98 runtime unit tests pass. Minimal and all-feature compile checks pass.
- Complete final states and all ordered Run signatures match their saved
  controls: 1,428 Runs for sum-bits and 16,883 for Raytrace. Constructor requests,
  function updates, unions and created facts match. All ordinary graph counters
  except the expected shared point-cache counters also remain unchanged.
- The unmodified sum-bits native choice validator returns `pass` / exit 0.
  Raytrace agreement remains a relative regression check, not native proof.
- README compile/run/bench (repeat 1) passes as a command smoke check, not a
  throughput measurement. The immutable upstream baseline tag is unchanged.

## Reproduce

Use new output directories and the frozen `cell-fixed-reads` program hashes in
`results.json`. Freeze the binary before subsequent builds overwrite it.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-residuals
cp target/release/eggfuse-cell-runtime ROOT/runtime-final
ROOT/runtime-final --program SUM_PROGRAM --output ROOT/sum-final --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals
ROOT/runtime-final --program RAY_PROGRAM --output ROOT/ray-final --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic-final ROOT/semantic-acceptance.json
python3 benchmarks/parallel-residuals/collect.py ROOT SUM_REFERENCE RAY_REFERENCE SUM_PROGRAM RAY_PROGRAM RESULTS.json
```

Prepare `semantic-final` with the saved native contract inputs and the fresh
`sum-final/state.json`, as required by the existing choice-diagnosis contract.
The collector does not launch workloads or compare timing. Raw exports,
binaries and logs remain ignored under `out/parallel-residuals`.

## Direct Entry filtering and query completion

Follow-up control: `cef7db18`; same opt-in feature and original Cell query.
The previous path still created a consumer Seed and an empty domain for every
Sieve survivor, then selected those Seeds again and converted them to worker
headers. These are transport objects, not additional query evidence.

For the same admitted, non-Cursor Entries the scheduler now borrows their
existing rows directly. Each worker performs the original Sieve conditions,
Free Join checks and complete residual query in one task. Ordinary reverse
candidate selection remains in use; separately selected/shared projections
and per-Entry audits retain the previous path. An existing Entry row pointer
crosses the thread boundary, not its owning `Rc`, consumer or publication state.
Successful owned Instances still enter the original ordered RHS.

This removes the covered Seed/consumer ownership clones, empty-domain records,
and the later Seed-to-query handoff. It creates no runtime relationship index,
extra bindings, cross-Run assumptions or new Bake credit. Graph accounting is
reduced after the scheduler releases its borrow; that reduction carries no
rows or query state. Completion accounting is created only for actual work.

| Complete diagnostic | sum-bits | Raytrace |
|---|---:|---:|
| Consumer Seeds, before → after | 12,095 → 1,747 | 3,435,349 → 1,553,384 |
| Seed/domain handoffs omitted | 10,348 | 1,881,965 |
| Sieve probes in the combined task | 2,053 | 372,680 |
| Candidate rows entering the combined task | 11,944 | 2,202,688 |
| Header capacity bytes, before → after | 413,920 → 141,936 | 75,278,600 → 25,478,712 |
| Task batches, before → after | 1,604 → 1,872 | 15,843 → 19,395 |
| Answer-vector capacity bytes, before → after | 632,640 → 633,120 | 84,864,960 → 85,102,080 |

The saved Seed and its corresponding empty domain describe one removed
handoff, not two independent semantic takeovers. The lower `borrowed_slots`
count is less consumer-projection bookkeeping; it does not mean those input
fields no longer need to be read by the query.

New costs remain visible: worker input includes Sieve-rejected candidates, and
filter-only batches now enter this path. Raytrace has 320,723 such rejected
rows and 48,701 chunks versus 41,191 before. Only borrowed row pointers are
collected (8 bytes each on this target), rather than 40-byte Entry headers.
Summed capacities are not allocator totals or peak memory. Preparation now
includes gathering those pointers; the prior timer excluded scheduler Seed
creation. Phase times are not a fair speed comparison. This checkpoint records
no new throughput or utilization result.

Both workloads preserve all ordinary graph counters, total key reads, every
Sieve probe/rejection/per-rule count, publication work and indexed-column
coverage. Exact final states and ordered logical/executed Run signatures agree
(1,428 and 16,883 Runs). The 18,927 extra Raytrace key reads versus the earlier
non-residual baseline have not been eliminated by this change.

The new-path regression fixtures require actual direct Entry execution and
equal Sieve counters. All 32 integration tests and forced-collision checks pass;
98 runtime unit tests, minimal/all-feature builds and README command smokes
pass. Native sum-bits acceptance returns `pass` / exit 0. Raytrace remains a
relative regression comparison.

Reproduce with the same flags above, using `ROOT/sum` and `ROOT/ray` as fresh
output directories and freezing the executable as `ROOT/runtime`. Prepare the
saved-input semantic contract under `ROOT/semantic` and write its result to
`ROOT/semantic-acceptance.json`. The prior root has the preceding frozen
`sum-final` and `ray-final` outputs:

```sh
python3 benchmarks/parallel-residuals/collect_entries.py ROOT PRIOR_ROOT RESULTS.json
```

[entry-takeover.json](entry-takeover.json) records checks and costs. Raw artifacts
are ignored under `out/residual-entry-takeover`. Remaining query barriers still
occur per kernel/pivot; this change does not yet combine these tasks with the
Run-wide physical-Cell queue. RHS, publication and repair remain coordinated.

## One physical-Cell queue for the source Run

Follow-up control: `15b0b4c1`. Its actual Raytrace execution still dispatched
19,395 residual batches, including inline batches. Direct Entry borrowing had
removed Seed/domain handoffs, but each kernel/pivot still completed separately.
This change appends eligible residual Query code to the existing Cell code
table and queues its original Entries alongside point continuations. There is
one completion call for the queued source Run, organized by actual physical
Cell and shared template. This shares scheduling and locality, **not query
prefix computation**. Ordinary point batches outside this queue remain.

The proof comes from the original Query, Free Join projections and source-Run
read boundary. This does not learn a new Ripsat equivalence from the catalog,
discharge a future Run or give Bake new reuse credit. It removes the covered
per-kernel execution/join and result handoff; it does not remove the predicates
or enumeration. Entries with active Spine/absorption/prefix specializations
retain their existing paths.

Each queued Entry keeps one coordinator-owned `Rc<Row>` until completion;
workers borrow the Row itself. They never receive the Rc or Cursor. Existing
columns are prepared when the old batch would have used them, including lazy
columns of already indexed tables. The final read views borrow those prepared
maps. Matching another rule does not mutate the graph. Results rejoin before
any RHS write, with the original watermark, delta ownership and visible values.

Winner selection uses one stable sort by input key and original source order.
Direct Entries precede ordinary residual answers; compatible already-filtered
Seeds retain their original position between serial kernel results. Expansion
row order remains stable within one source. The owned instances then enter
the original ordered RHS; no second set of input bindings or fact graph is
introduced. Failure clears queued owners and active Run metadata.

| Complete diagnostic | sum-bits | Raytrace |
|---|---:|---:|
| Original residual source batches (unchanged) | 1,872 | 19,395 |
| New Run completions containing residual work | 279 | 2,785 |
| Of those, calls to the worker pool | 59 | 1,466 |
| Runs sharing the queue with point continuations | 99 | 1,105 |
| Chunks containing residual work, before → after | 1,876 → 741 | 48,701 → 39,772 |
| Queued Row owners (new) | 11,944 | 2,202,688 |
| Header capacity bytes, before → after | 141,936 → 511,440 | 25,478,712 → 95,786,680 |
| Chunk answer capacity bytes, before → after | 633,120 → 845,696 | 85,102,080 → 122,156,672 |
| Per-rule ordered merge capacity bytes (newly recorded) | 735,896 | 114,950,464 |
| Shared Cell queue peak capacity bytes | 65,536 | 8,388,608 |
| Shared task grouping peak capacity bytes | 35,440 | 3,424,112 |

These costs matter. The old residual header held only a borrowed Row pointer;
the new mixed header additionally identifies code, source and prepared reads.
It borrows the Row instead of repeating its value/epoch/witness fields, but is
still 40 bytes on this target versus the old 8 bytes. New header totals include
point Entries in the same Runs; answer totals include point results in mixed
chunks. Merge buffers hold source-order metadata beside moved instances. The
new plan metadata uses 234,976 / 234,984 bytes; shared code capacity also grows
and is recorded. Capacity sums are not peak memory or allocation totals, and
the fields omit nested instance storage, sort scratch and pool bookkeeping.

All residual query, admission and filtering work counts remain exact. Ordinary
graph counters, total key reads, Sieve, publication, Entry scheduling and index
coverage also remain exact. Complete states and ordered Run signatures match
the control: 1,428 / 16,883 Runs. The earlier 18,927 extra Raytrace key reads
relative to the non-residual baseline remain. There is **no new throughput or
utilization measurement**, and fewer batches alone do not establish a gain.
Task/execute times now include shared point work and cannot be compared with
the previous residual-only phase timers.

Acceptance includes 33 integration tests, a new native-checked mixed point/
residual fixture with same-Run writes and cross-rule Cell grouping, forced
zero-bit fingerprints, and 99 runtime unit tests. A new unit test checks lazy
column preparation before borrowing. Minimal/all-feature checks and README
compile/run/bench (repeat 1) pass; the latter is only a command smoke. Native
sum-bits acceptance returns `pass` / exit 0 without changing its contract.
Raytrace agreement remains a relative regression check.

Freeze the binary as `ROOT/runtime`, run the same flags above into fresh
`ROOT/sum-checked` and `ROOT/ray-checked`, and prepare the saved semantic inputs
under `ROOT/semantic`. The collector reads saved outputs and launches no tests:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/parallel-residuals/collect_run_queue.py ROOT PRIOR_ENTRY_ROOT RESULTS.json
```

[run-queue.json](run-queue.json) retains both dispatch and storage costs. Raw
artifacts remain ignored under `out/residual-run-queue`. RHS, publication and
repair remain coordinated; full CPU utilization is not achieved.
