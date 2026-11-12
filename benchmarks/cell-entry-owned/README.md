# Worker Entry ranges, Unit continuation and table ownership

This is the actual standalone Cell CPU executor, not a native egglog runtime
measurement. The frozen control is `11056467`. Both lanes use the same programs
and four-worker flags, including `--cell-execution-grain 1`. The ordinary default
does not enable this scheduler.

The previous catalog/sample showed workers idle in the pool rather than blocked
inside jobs. This iteration moves Entry preparation and more Cell effects to
those workers. It uses existing query/effect instructions and actual instance
slots, without a new runtime fact graph or per-producer consumer lists.

## Takeovers and remaining boundaries

1. **Entry ranges:** an unowned residual Entry with no reverse-selected subset
   supplies its scheduler node, compiled query, watermark and source position.
   Workers enumerate the existing immutable epoch runs, skip retired positions,
   obtain actual rows from the sealed Run, filter, bind and finish the query.
   This removes per-entry Rc queue owners, physical-Cell grouping and borrowed
   query headers within coverage. Ranges smaller than the configured grain
   retain the existing combined Cell queue; giving each tiny range its own
   scratch/result chunk lost useful locality. Cursor-owned Entries retain their
   own continuation proofs. Tree epochs retain ordered traversal; contiguous
   epochs split without coordinator row enumeration.

2. **Query-to-RHS continuation:** a typed input-only Cell with scalar computation
   and total old/new Unit writes generates actual Function/key/decoded-row
   candidates in its existing query task. Source winners adopt these allocations
   and actual receipts instead of reinterpreting Set or reconstructing operands.
   Constructor and Unit preparation are mutually exclusive variants of the same
   Instance state; there is no extra Unit field or boxed vector header on every
   successful match. Small inline Runs retain their ordinary source write path.
   Compact Unit storage is excluded during plan construction. Missing scalar
   results, source union changes and pending unions still prevent invalid reuse.

3. **Table-owned registration:** a bounded batch whose Cells have all reached
   their terminal operation can classify Unit keys on workers. Exact equality
   resolves duplicates; no Bloom hit acts as proof. A short source-order scan
   assigns compact Function IDs, preserving delta-owner tie semantics. The
   source adopts each actual row once. Exclusive table workers then install the
   real key directory, membership, query version and ChangeBatch entries before
   another RHS group or query observes them. First source adoption preserves
   table activation order relative to constructor changes. Error cleanup installs
   only rows actually appended, never directory entries pointing at absent rows.
   Fewer than 32 candidates, fewer than two tables, partial/fallible suffixes,
   pending repair and compact Unit tables retain ordinary registration.

The third takeover removes source key lookups/insertions and table publication
maintenance for the accepted rows. It adds a temporary exact-key partition,
source ID scan and two pool phases; those costs are included. Shared Eq-root
subscriptions, constructor intern registration, Cursor completion, arbitrary
mutable effects and original Run visibility remain real boundaries. This is
not continuous unrestricted execution across Runs or full CPU saturation.

## Work and costs

| Actual Raytrace work | Control | Final candidate |
| --- | ---: | ---: |
| Per-entry queue owners/headers | 3,780,387 | 1,783,538 |
| Entries enumerated directly on workers | 0 | 1,996,849 |
| Range descriptors / chunks | 0 | 4,042 / 38,865 |
| Query-prepared Unit rows consumed at source | 0 | 138,593 |
| Duplicate query-prepared rows invalidated | 0 | 89,350 |
| Unit candidates classified by table owners | 0 | 119,841 |
| New Unit index/publication registrations on workers | 0 | 79,171 |
| Table registration batches / table tasks | 0 | 818 / 1,636 |

Range chunks account for about 3.18 MB of cumulative payload;
query Unit preparation accounts for 47.76 MB, including payload adopted into
permanent storage and discarded duplicate rows. Table registration accounts for
about 10.16 MB of partition/dispatch payload. These are neither peak heap nor
complete allocator totals; map control bytes and allocator headers are excluded.
Existing constructor-tail row allocation is not credited again as a new saving.
The range counter is a subset of removed headers, not an additional saved query.

Exact counters live in `query_workers.stats.entry_range_*`,
`query_workers.stats.execution.units`, `stats.unit_prepared_*` and
`stats.unit_registry_*`. The final sum-bits run uses 762 range entries and 54
query-prepared Unit rows; its small terminal batches do not enter table-owned
registration. Both final workloads have zero prepared-row storage/generation
fallbacks. The union invalidation path remains covered by a dedicated fixture.

## Validation and timing

The 82 relevant compiler/integration tests and 140 runtime unit tests pass.
They cover exact per-Run snapshots and ordered matches, duplicate Unit rows,
multi-argument keys, foreign results, union invalidation, deletion/recreation,
late inputs, scalar failure and publication/completion boundaries. The new
registration fixture asserts that real worker index installation occurs.
All-features compilation and README compile/run/bench commands pass.

Frozen sum-bits (1,428 Runs) and Raytrace (16,883 Runs) retain identical final
state hashes, every ordered Run summary and logical effect counts against
`11056467`. The unchanged `choice_diagnosis.py` accepts the reviewed sum-bits
native contract with `status: pass`, reusing native exports. Whole-state equality
and Run checks remain separate from that final-state proof.

All timing attempts are retained: `initial-results.json` precedes the range-grain
guard; `grain-results.json` precedes preparation-state compaction and the inline
Unit guard; `results.json` contains the final candidate. Initial work-count gains
did not establish a speedup on both workloads. Small-sample timing is noisy,
including active background system storage work in this session. No samples
are discarded, and process CPU/wall ratios include startup and export rather
than measuring inference-only worker utilization.

Reproduction uses fresh directories and the frozen manifests:

```sh
python3 benchmarks/witness-prefix/measure.py out/cell-entry-owned/sum-manifest.json FRESH_SUM_TIMING --repeat 5 --warmups 1 --timeout 120
python3 benchmarks/witness-prefix/measure.py out/cell-entry-owned/ray-manifest.json FRESH_RAY_TIMING --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-entry-owned/semantic-acceptance.json
python3 benchmarks/cell-entry-owned/check.py out/cell-entry-owned out/cell-dispatch-batches benchmarks/cell-entry-owned/results.json
```

The collector expects final runs/timings under `out/cell-entry-owned`, the saved
control reports in `out/cell-dispatch-batches/candidate-{sum,ray}`, and the frozen
control executable copied to `out/cell-entry-owned/control-runtime`. Compile
control `11056467` and the candidate with identical
`cell-absorption,view-ports,parallel-publication` runtime features. Binary/program
hashes, full command flags and every measured sample are in the result files.

Final interleaved results (one warmup per lane, all samples retained):

| Workload | Samples per lane | Control inference median | Candidate inference median | Change |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 5 | 21.672 ms | 23.257 ms | 7.3% slower |
| Raytrace | 3 | 5.893 s | 5.756 s | 2.3% faster |

This does **not** pass a both-workloads performance gate or establish a general
speedup. Raytrace's whole-process CPU/wall median is about 1.04 cores in both
lanes, including loading/export and interference from other processes; it is
not a new inference-only utilization measurement. The semantic takeovers are
implemented, but thread saturation remains unachieved. Smaller header counts
are insufficient evidence that the dominant serial work has been removed.
