# Worker-owned scalar Cell RHSs

This experiment executes actual standalone Cell CPU RHSs. It is not a native
egglog speed measurement. Enable the existing `--cell-execution-grain` experiment
with multiple query workers; the ordinary default remains unchanged.

The previous catalog's real executions expose 1,569,156 single-write RHSs on
Raytrace. These Cell templates already prove their Eq key, i64 value calculation,
and old/min/max merge. Their source effect is the last instruction. A successful
match provides the inputs; no new marker or maintained fact graph is needed.
A later Run observes the merged row, not intermediate private producer frames.
This permits a worker-owned completion before the existing publication boundary.

The source owner resolves keys and allocates shared row/Cell addresses. Workers
compute all candidates, including candidates targeting the same row, in one pool
call per admitted rule group. Workers borrow disjoint
**actual Function storage**, fold each row's candidates in source order, and
write its value, epoch, decoded row and final producer slots. Losing and
superseded private slots are dropped on workers. The winning query allocation
becomes the writer's storage. There is no RHS instruction log for coordinator
replay, no graph-wide lock, and no requirement that all input targets be distinct.
An exact destination index already exists here, so a Bloom filter would add a
screening step without replacing that index.

The final writer is the same source winner as the serial execution, including
equal-value ties. Its old allocation is reused if no external parent retains it.
Otherwise the old immutable producer is promoted through the existing lifecycle
path. Constructor-backed parents stay immutable during this scalar-only batch;
inline mutable writer parents, live continuation origins, slot-tracking histories,
compact views, callbacks and other effects retain their existing path. Queries
do not execute during mutation. Source completion and Entry publication preserve
their original ordering and Run visibility. The implementation uses ordinary
exclusive Rust references, without unsafe shared Graph access.

The compiler's existing `PortWrite` and scalar merge contracts authorize this
takeover. Arithmetic already completed by the query needs no second preparation
call. Unchecked arithmetic runs speculatively, before any mutation. If any
candidate fails, the untouched original Instances run in source order, preserving
earlier effects and the first source error. The query bindings are never copied.

The removed work is per-instance source `apply_write`, merge execution, decoded
row construction, intermediate writer installation and repeated dirty-row
notifications within the proven batch. Source receipt completion still runs for
each logical application; its cost is not counted as removed. Logical improvements
and ordered audit events match the serial semantics, whereas `row_writes` counts
actual final row stores. Invalidating a candidate drops its owned slots; it is
not a claim that deallocation has zero cost.

Metrics are under `cell_execution.runtime.stats.writes`: candidate/duplicate
counts, row stores, logical improvements, invalidations, superseded improvements,
writer allocations/reuses, worker row ownership, temporary metadata capacity and
four separate phase timers. `preparation_ns` and `execution_ns` include dispatch,
work and join. They are not pure waiting. `boundary_ns` covers shared address and
index/lifecycle maintenance; `source_completion_ns` covers source publication
responsibility. Temporary bytes are cumulative allocations, not peak memory.

The first draft relocated writes but allocated an extra Instance wrapper array
and replaced every writer box. It did not establish a speedup: three Raytrace
samples had inference medians 6.777 s control / 6.739 s candidate, with a large
control outlier; RHS phase medians were 2.519 s / 2.626 s. Subsequent changes borrow
the original Instance array and reuse unretained writer boxes. Source Roots are
created next to publication, so no per-candidate Cursor container survives the
worker call. All-empty query evidence needs no saved array. Batch counters live
in one boxed scheduler record, not the frequently returned per-segment Counts.
All intermediate samples remain under ignored `out/cell-worker-writes`; the
bounded draft samples are retained in `drafts.json`.

Controls are built from `b47cb0fa`; candidate builds use an isolated checkout of
that commit plus these source changes. Other sessions' later storage/reclamation
commits are excluded from the measured binaries. Compilation with all features
also passes in the shared worktree with those changes. The commands below use
fresh output directories and the same frozen programs/flags as
[the prior peer experiment](../cell-peer-results/README.md). Binary, program and
state hashes, every retained timing sample and actual work counters are in
`results.json`. Sum-bits may have no admitted batches at the 32-binding minimum;
that must not be reported as parallel RHS coverage.

```sh
python3 benchmarks/witness-prefix/measure.py MANIFEST TIMING_OUTPUT --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/marker-handoff/choice_diagnosis.py ARTIFACT_ROOT OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-worker-writes/check.py OUTPUT benchmarks/cell-worker-writes/results.json
```

The semantic directory reuses saved native exports and substitutes only this
candidate's sum-bits state. Integration tests compare every Run snapshot and
ordered effective-write audit, including duplicate keys, retained old writers,
union followed by later execution, publication and overflow failure. Strict full
state/Run summaries are also compared on sum-bits and Raytrace; this supplements
the unchanged native sum-bits acceptance entrypoint.

The final candidate passes 91 compiler/integration tests, 140 runtime unit tests,
the README compile/run/bench commands, and the unchanged sum-bits validator
(`status: pass`). It preserves exact final states and ordered Run summaries for
both frozen workloads. These are actual standalone Cell CPU measurements:

| Workload | Control inference median | Candidate inference median | Admitted write batches |
| --- | ---: | ---: | ---: |
| sum-bits, 5 samples | 26.503 ms | 26.126 ms | 0 |
| Raytrace, 3 samples | 7.131 s | 7.023 s | 3,660 |

Raytrace's paired results include both improvements and a regression. The 1.5%
median difference does **not** establish a stable speedup. Sum-bits has no write
takeover at this threshold; its timing difference is not attributable to worker
mutation. Raytrace RHS phase medians are 2.701 s / 2.626 s.

On Raytrace, workers evaluate 840,367 candidates, including 46,829 repeated target
occurrences, and install 755,389 final rows. They discard 84,978 candidate slot
arrays; 7,708 source improvements are superseded before publication. These are
different counts: source improvements remain 763,097. The new path allocates
4,385 writer boxes and reuses 751,004. Cumulative temporary metadata falls from
450,917,328 bytes in the first draft to 197,995,912 bytes. All 3,660 final batches
use one pool call; no arithmetic fallback occurs in this workload.

This is a bounded RHS takeover, not full worker saturation. Constructor merging,
uncovered effects, query preparation and source publication still contain serial
work. The earlier wait diagnosis is retained in
[waits.json](../cell-peer-results/waits.json): workers spent about 81–85% of two
partial wall-sampling windows in condition waits, overwhelmingly idle in the pool.
That observation motivates larger continuous execution; it does not justify
calling every pool timer pure waiting or every relocated write a speedup.

Two final partial samples are in `results.json`. In the clean second window,
workers spend 81.2–84.8% of wall-stack samples in condition waits, with 98.5%
of those waits at the idle pool. The main thread spends 17.8% in condition waits:
120 samples at query joins, 88 at publication joins, 43 at the old synchronous
local RHS path, and 21 at scalar write joins (1,532 total samples). The first
window briefly overlaps the semantic validator and is retained with that caveat.
These windows establish that the workers remain mostly idle; they do not establish
a before/after utilization improvement.

The old constructor path still makes 74,168 synchronous small pool calls outside
the 342 ready batches. Allowing duplicate candidates has not removed these
source-side dispatch barriers. The next structural target is to carry inherited
Cell instances into ready batches while preserving source completion order and
actual result references. Removing the continuation guards without accounting
for early completion/union publication would change effects and visibility.
