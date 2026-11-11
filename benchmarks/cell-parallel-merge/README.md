# Merge Cell inheritance with parallel query/publication

Parents: `b2428807` (`codex/cell-parallel-admission`) and `17d8dbe6`
(`codex/cell-state-inheritance`, worktree `7c16`). Common ancestor: `50316626`.
The entire incoming branch is merged: eight implementation commits and two
measurement/documentation commits. Neither parent's history is rewritten.
The incoming worktree was clean and is not modified.

This is **standalone Cell CPU** evidence. The merge has complete work and
semantic checks, not a new timing campaign or a full-utilization claim. The
parents' separate timing campaigns cannot be added or compared as if they
measured the merged executable under identical conditions.

## Which optimizations overlap?

| Incoming change | Relationship to parallel Cell work |
|---|---|
| `c073c460`: inline singleton domains | Same removed handoff in different hosts. Worker residual queries already borrow index membership without a candidate vector; inline domains improve the remaining coordinator queries. A worker-owned Entry never also executes coordinator Free Join. |
| `48782309`: project point results before handoff | Worker reads already return only the result, epoch and actual witness. This improves remaining ordinary reads/caches and the serial configuration. It cannot earn additional Row-removal credit for the worker path. |
| `4abd900b`, `5197c099`, `d7b2b9ac`: field-scoped summary updates and storage ownership | Complementary. Parallel publication moves index partitions to workers; incoming code reduces downstream summary work and transfers fingerprint arrays without a clone. Worker notifications must preserve the field mask. |
| `3c4dc524`: absorb members of mixed domains | Complementary. The query plan continues excluding absorption kernels from residual takeover, preserving their compiler-proved omission of bindings/RHS work. |
| `6fe472f4`, `6e6f51dd`: LazyUnion programs and repaired result sealing | Complementary. Actual result receipts and ordered completion remain authoritative after query join; thread placement grants no new equality or cross-Run visibility proof. v5 admission remains opt-in. |

There is no duplicate execution of both query hosts for a covered Entry. There
are two useful representations for different ownership requirements: an inline
or shared candidate handed to the ordinary matcher, and a read-only borrowed
domain in a worker. Unifying them into another runtime container would recreate
the handoff the worker route removed. Existing Cell queries, bindings, Entries,
actual result slots and source Run boundaries remain shared authority.

## Integration work

- Preserve incoming `Candidates::One/Shared` through ordinary query domains and
  frontier observations. Shared domains use the existing conditional `DomainRc`
  alias, so parallel builds retain `Arc` without duplicating membership.
- Extend parallel column notifications and retained empty buffers from
  `(witness, table)` to `(witness, table, changed_fields)`. Charge the additional
  eight bytes per notification in capacity metrics. A unit regression covers
  both an inserted row's complete mask and a result-only update's selective
  mask through move, update and restoration. Exact-collision invalidation stays
  in the original writer.
- Preserve compact Point payloads in neighbor publication, including its
  parallel ownership path. Keep the serial fallback and all original lifetime
  and visibility checks.
- Combine both optimization-catalog entries/metrics and regenerate category
  pages. Historical reports retain their original configuration and scope.
- Exercise the incoming absorption fixtures with residual workers and parallel
  publication enabled together. Preserve their native and per-Run checks.
  The first forced-zero run exposed an incoming test's unconditional demand
  for a whole-domain cached bound, already failing on its serial iteration.
  A mixed-key collision bucket cannot prove that bound. Its zero-bit branch
  now requires zero whole-domain bounds and positive checked-member absorption;
  normal fingerprints still require bound reuse. Every semantic assertion
  remains unchanged. Three query tests likewise required singleton or negative
  support coverage that their all-colliding nonempty buckets cannot provide.
  Their zero-bit cases now require the shared-domain/exact-query fallback;
  ordinary cases retain the positive coverage assertions. All 23 selected
  forced-collision tests pass, including every Run and binding comparison.

## Complete execution evidence

`reference` is the frozen incoming executable (`48782309`, code unchanged by
`17d8dbe6`) with four point-query workers. `point` is the merged executable with
the same options. `parallel` additionally enables residual queries and parallel
publication. All use the same frozen `cell-fixed-reads` programs, repair ports,
Entry publication and Cell absorption. The previous parallel parent's saved
exports are also checked.

| Full Raytrace | Incoming reference | Merged point workers | Merged residual/publication workers |
|---|---:|---:|---:|
| Executed bindings | 2,743,465 | 2,743,465 | 2,743,465 |
| Newly absorbed mixed members | 194,730 | 194,730 | 194,730 |
| Total absorbed matches | 704,026 | 704,026 | 704,026 |
| Sieve summary updates | 6,983,829 | 6,983,829 | 6,983,829 |
| Sieve field-group checks | 1,318,220 | 1,318,220 | 1,318,220 |
| Coordinator inline-domain deliveries | 1,886,203 | 1,886,203 | 758,293 |
| Coordinator projection-shape checks | 2,643,879 | 2,643,879 | 1,122,397 |
| Ordinary positive function Point reads | 21,899 | 21,899 | 0 |
| Neighbor-cache publication checks | 1,124,415 | 1,124,415 | 0 |
| Partitioned uncovered Entries on workers | 0 | 0 | 1,112,319 |

The drop in inline-domain and Point counters is reduced use of those ordinary
hosts, not lost matching coverage. In particular, **zero ordinary Point reads
does not mean zero point queries**. The worker still performs authoritative
lookups. No combined credit is awarded for overlapping Row/domain removals.
The incoming group-check and failed absorption-proof costs remain live.
Logical matches/absorbed executions are not committed mutations.

Complete sum-bits similarly preserves 31 newly absorbed mixed executions (72
total). Its inline-domain deliveries are 4,493 with point workers and 1,727
with residual workers; the latter executes 759 partitioned Entries on workers.
Both workloads preserve result sealing (409 / 85,533 slot reads), which does
not authorize retaining stale or deleted witnesses.

`results.json` preserves all selected before/after work, report/binary hashes
and costs. All lanes have identical final states and ordered logical Runs:
1,428 sum-bits Runs and 16,883 Raytrace Runs. Merged executions also have the
same ordered executed-binding counts and absorption work as the incoming
reference. Against the earlier parallel parent, executed counts legitimately
decrease through mixed absorption; committed function updates, unions and facts
remain equal. Constructor/union *requests* are not used as mutation counters.

Validation includes 108 runtime unit tests, 15 compiler unit tests and 49
selected integrations, including repaired receipt sealing, v5 LazyUnion,
parallel queries/publication, deletion, union and current-value reads. Forced
zero-bit fingerprint tests exercise the combined paths. Minimal/all-feature
checks and the README compile/run/bench smoke are required. The bench smoke
uses repeat 1 and supplies no throughput conclusion.

The unchanged reviewed sum-bits native validator returns **pass / exit 0**.
Raytrace agreement is relative regression evidence, not a new independent
native semantic proof. Full thread utilization and an overall speedup from this
merge remain unestablished.

## Reproduction

Freeze both executables before building other features. Use fresh output
directories and the saved native acceptance inputs.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
cp target/release/eggfuse-cell-runtime ROOT/runtime
cp INCOMING_RUNTIME ROOT/reference-runtime
# For each CASE in sum/ray:
INCOMING_RUNTIME --program CASE_PROGRAM --output ROOT/reference-CASE --repair-ports --entry-publications --cell-absorption --query-workers 4
ROOT/runtime --program CASE_PROGRAM --output ROOT/point-CASE --repair-ports --entry-publications --cell-absorption --query-workers 4
ROOT/runtime --program CASE_PROGRAM --output ROOT/parallel-CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-parallel-merge/check.py ROOT PARALLEL_PARENT_ROOT RESULTS.json
```

`ROOT/semantic/run-values/state.json` is the merged parallel sum-bits export.
Raw artifacts remain ignored under `out/merge-cell-inheritance`.
