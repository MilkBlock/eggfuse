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
