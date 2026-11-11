# Partition uncovered queries from owned Cell continuations

Control: `06e1c090` (the frozen executable is `aa2161e2`; the intervening
commit only documents the throughput checkpoint). This measures the
**standalone Cell CPU**, not native egglog. The experiment remains opt-in.
Full utilization and a throughput gain are **not established**. This is the
first implementation after that checkpoint; no new timing campaign is run.

## Opportunity and compiler proof

The last throughput checkpoint did not establish a four-thread Raytrace
speedup; eight threads regressed. Its wall-stack diagnostic found workers
parked in 93.3–95.4% of their samples, while the coordinator still performed
Entry preparation, Free Join admission and residual Frame queries. Stack
residence is not CPU utilization, and inclusive samples overlap.

The old admission gate excludes an entire rule's residual expansions whenever
its Spine is active. That is stronger than the necessary ownership condition:
Shared Entry already identifies which actual rows have a published Cursor.
The compiled Cell Query and Free Join plan independently identify connected
expansions that can read a sealed Run. Entries without a Cursor need not wait
for the coordinator just because other entries of their rule have one.

This uses the preceding catalog's actual execution costs and the existing
typed Query/Entry plans. It adds no Ripsat equivalence, new catalog, marker or
cross-Run block-switch credit. The scheduled block already owns its Cursor
continuations; uncovered matches cannot inherit their completion proof.

## Takeover and remaining obligations

- Keep Sieve and actual published-Cursor selection on the coordinator for
  mixed rules. Cursor-owned entries retain the existing Spine path, including
  its winner priority and absorption/prefix optimizations.
- Queue an eligible uncovered Entry's existing `Rc<Row>` directly in the
  shared physical-Cell Run queue. Omit the old Free Join admission, domain
  handoff, consumer Seed and coordinator Frame query. Workers do necessary
  admission and expansion once; they do not repeat Sieve.
- Retain the same canonical read-view, visibility, delta-owner and watermark
  checks. Unsupported ranges, prefix hosts, absorption kernels, unsettled
  completion and audit modes keep their original route. Small Runs execute
  inline; queueing is not evidence that a worker thread ran the query.
- Record each pivot's original insertion position once in its shared plan.
  Residual winner selection uses that position and the original Entry order,
  never thread completion order. Spine winners are sealed through the existing
  pending-rule mechanism and keep priority over residuals. Deferred error
  selection keeps rule order and Spine-before-residual order within a rule.
- Until worker admission returns, uncovered entries conservatively prevent a
  complete-Spine claim. Some counters formerly counting post-admission Seeds
  now include pre-admission candidates (`routed_matcher_seeds`, fallback and
  partial-query counters). Their increase is not new logical matches.
- Join before ordered RHS and repair, as before. Each task returns the actual
  Instance and witnesses. No binding history, producer/consumer list or graph
  snapshot is copied into a second representation.

## Complete execution evidence

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Newly queued uncovered Entries | 1,381 | 1,131,289 |
| Those Entries executed on worker threads / inline | 759 / 622 | 1,112,319 / 18,970 |
| Passed admission; old Seed/domain handoffs omitted | 572 | 844,253 |
| New-path successful query Instances, before winner selection | 651 | 742,755 |
| Coordinator consumer Seed deliveries, before → after | 1,747 → 1,175 | 1,553,384 → 709,131 |
| Coordinator Free Join probes, before → after | 6,384 → 4,986 | 3,559,261 → 2,427,588 |
| Total Free Join probes including workers, before → after | 17,430 → 17,430 | 5,517,575 → 5,517,584 |
| Total point accesses, before → after | 12,259 → 12,259 | 3,695,314 → 3,695,314 |
| Old neighbor-port publication checks, before → after | 161 → 0 | 1,124,415 → 0 |
| Old demanded neighbor-port keys, before → after | 65 → 0 | 11,004 → 0 |

`results.json` distinguishes new Entries actually run on worker threads from
inline completion, and charges all additional queue, task, result and sorting
storage. Logical matches and successful query Instances are not committed
mutations. Native-checked fixtures also require the newly partitioned queries
to execute on workers, not merely other queries in the same Run.

### Cache accounting matters

Raytrace's `key_lookup_calls` rises from 2,574,304 to 3,695,314. The difference
is exactly 1,118,287 old neighbor-port hits plus 2,723 shared point hits.
Both old and new paths perform **the same number of point accesses**. The
ordinary neighbor cache uses a key hash map to find a copied Row; the worker
reads the authoritative scalar-key index and function slot. The new path
therefore removes the old port cache's demand storage and publication, rather
than rebuilding that cache on each thread. Negative shared hits are a subset
of shared hits and are not added twice.

This is an accounting identity, not proof that the accesses cost the same.
The worker still pays for its authoritative lookup, scalar result and ownership
checks. Constructor-domain reuse also changes: old cached-parent visits fall
from 706,246 to 385,506. That cost must be considered alongside the removed
maintenance. All 509,296 absorbed Raytrace matches and their original
conditions remain unchanged; they are not recounted as this change's savings.

### New costs and limits

Raytrace queues 1,131,289 extra row owners, including 287,036 entries rejected
by worker admission. The previous path only materialized a Seed after
admission. This moves rejection work off the coordinator but increases queue
traffic. Per-instance bindings are not cloned.

The shared expansion plan adds a partition flag and pivot insertion position;
reported plan capacity grows by 15,048 bytes. Error ordering stores one first
source ordinal per compiled rule, not per Entry. `rule_run_capacity_bytes`
reports the entire existing rule-run vector after that addition. Per-worker
partition counters add a small vector. These capacities exclude allocator and
pool overhead; they do not establish total allocation savings.

Residual winner comparisons rise from 4,460,810 to 10,861,714 and cumulative
residual merge capacity from 114,950,464 to 262,450,896 bytes. The old
coordinator sorted the newly transferred answers outside this counter, so the
delta is not a measure of net extra comparisons. It nevertheless exposes the
larger worker pipeline's cost. The broad task/result capacities are retained
in the evidence. Mixed Entry preparation is part of overall search time;
`residual_expansion.prepare_seconds` only times the older batch enqueue paths.
No timing conclusion is drawn from the single complete diagnostic execution.

RHS, union and required repair are still ordered on the coordinator. This
change cannot by itself guarantee balanced workers or eliminate Run barriers.

## Validation and reproduction

The fixture mixes bootstrap constructors and produced constructors in one
active-Spine rule, then changes mutable values, unions inputs, deletes and
recreates a constructor. Native checks pass. Serial residuals and 1/2/4-worker
residuals agree on every Run snapshot, ordered binding, actual write digest and
chosen continuation origin (digests require `iterative-bake`). Forced zero-bit
fingerprints exercise the exact candidate checks. All 35 integration and 102
runtime unit tests pass, as do minimal/all-feature checks and README
compile/run/bench commands. Bench repeat 1 is a command smoke, not throughput
evidence. Logs are retained in the ignored execution directory.

The complete sum-bits and Raytrace final states and all 1,428 / 16,883 ordered
Run signatures equal the control. All effect counters, Sieve filters, actual
Spine seeds, known-result reuse and absorption agree. Raytrace is a relative
regression check, not an independent native semantic proof. The unchanged
sum-bits native acceptance returns **pass / exit 0** using the saved contract.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
cp target/release/eggfuse-cell-runtime ROOT/runtime
ROOT/runtime --program SUM_PROGRAM --output ROOT/sum --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
ROOT/runtime --program RAY_PROGRAM --output ROOT/ray --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/parallel-cell-partition/collect.py ROOT CONTROL_ROOT RESULTS.json
```

Use the frozen `cell-fixed-reads` programs and fresh output directories.
`ROOT/semantic` contains the saved reviewed native contract with the new
sum-bits export. Raw artifacts stay ignored under `out/parallel-cell-partition`.

Relevant tests (the additional feature enables ordered effect/resume audits):

```sh
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test parallel_residuals --test parallel_publication --test query_workers --test entry_publications --test cell_absorption
CELL_CPU_HASH_BITS=0 cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test parallel_residuals --test parallel_publication
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
```
