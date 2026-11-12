# Cell tail batches and duplicate Unit rows

This changes the actual standalone Cell CPU executor. It is not a native egglog
runtime speed measurement. The control is `534bc384`, with identical four-worker
flags and frozen programs. The experiment remains under `--cell-execution-grain`;
the ordinary default does not enable this scheduler.

The last catalog's actual Raytrace executions made 74,168 single-Cell synchronous
constructor dispatches, besides 342 ready batches. The diagnostic patch in
`dispatch-probe.patch` records the rule, operation count, template eligibility,
inherited depth and source position at each dispatch. Of these calls, 72,521
(97.8%) were in templates rejected by the old whole-rule batching test; 53,929
had inherited execution state. Common rejected templates end in Unit marker
writes or have already computed scalar operands before their last constructor
region. `probe.json` records the distribution, not performance.

The compiler now recognizes the final constructor region using the existing
Cell definitions and static aliases. Earlier pure primitives have completed
before a tail enters the queue. A fallible suffix, mutable read, visibility
operation, effectful merge, or constructor assignment still disqualifies the
batch. Total old/new Unit writes and the existing scalar merges can remain at
the source boundary. No new runtime fact graph or producer consumer list exists.

Inherited Cursors travel with their existing execution instead of forcing a
flush. While older tails are outstanding, startup retains actual result inputs
for the queue rather than immediately completing/publishing a later Cell.
The source-ordered drain executes remaining effects and publication. Previously
prepared scalar results are consumed without recomputation. Source Run boundaries,
retirement checks and actual returned constructor identities remain authoritative.

The standalone per-Cell `pool.install` constructor path is removed. The same
local kernel executes inline when it has no admitted concurrent peers; only
ready batches with at least two jobs can dispatch constructor work. This removes
dispatch/join overhead; it does not turn those remaining inline operations into
parallel work. The separate mutable-read scalar-resume path is unchanged and
has zero dispatches in these frozen workloads.

For a proven terminal Unit-only suffix, workers also materialize the actual
`Function` candidate and decoded row from their Cell's completed slots. The
source boundary performs exact key interning, adopts the winning allocations,
records the actual result receipt and drops duplicates. It does not interpret
`Set`, rebuild its key, or allocate its row again. The first source witness and
epoch remain authoritative. Candidates receive no permanent function ID before
acceptance, so invalidation leaves no tombstone or new repair obligation.

This is **parallel candidate writing, with serialized shared-index registration**,
not concurrent mutation of the global hash directory. The existing source path
is retained where pending unions could enable compact Unit view storage. All
constructor and Unit row receipts become observable at the original boundary.
Unions and source-visible non-idempotent effects are not simply discarded.

| Raytrace work | Control | Candidate |
| --- | ---: | ---: |
| Constructor worker invocations | 74,510 | 2,919 |
| Ready batches, including inline singletons | 342 | 3,388 |
| Ready Cell jobs | 14,880 | 81,258 |
| Constructor operations on workers | 151,693 | 127,101 |
| Unit rows materialized on workers | 0 | 128,118 |
| Total Unit candidates in new tail path | 0 | 129,123 |
| Adopted Unit rows | 0 | 85,340 |
| Invalidated duplicate Unit candidates | 0 | 43,783 |
| Cumulative queue allocation bytes | 18,712,528 | 147,171,664 |

Constructor operations on workers decrease because uncovered tiny pieces now
execute inline. The new queue contains much more useful independent work, but
requires more retained execution contexts. Unit candidate payload accounting is
41,319,264 bytes; it includes allocations adopted into permanent storage and
duplicate payloads. These counters are not peak heap or allocator totals. The
queue timer includes dispatch, execution and join, and is not pure waiting.
Existing scalar worker writes from `534bc384` remain enabled in both lanes and
are not credited again.

Fresh processes were interleaved, with one warmup per lane. All samples are
retained in `results.json`:

| Workload | Samples per lane | Control inference median | Candidate inference median |
| --- | ---: | ---: | ---: |
| sum-bits | 5 | 24.028 ms | 22.163 ms |
| Raytrace | 3 | 5.668 s | 5.219 s |

Raytrace improves by about 7.9% in this session; all three paired inference
samples improve. This is a comparison against the current branch, not a claim
about historical binaries measured in other sessions. The small sample count
does not establish a universal speedup. One candidate's whole-process wall time
regresses despite faster inference; complete wall and CPU times are retained.

A separate five-second wall-stack diagnostic has no synchronous local-constructor
wait frames. Main-thread condition waits comprise 139 query, 90 publication,
27 scalar-write and 6 ready-queue samples, out of 1,593 samples. Workers still
spend 84.7–88.3% of their samples in condition waits, predominantly idle in the
pool. Sampling perturbs execution, inclusive frames overlap, and this is not a
CPU utilization percentage. The improvement is not evidence of full saturation.

Validation compares exact frozen final states, every ordered Run summary and
logical effects for sum-bits and Raytrace. The unchanged sum-bits native semantic
acceptance script reports `pass`, using saved native exports. Integration tests
cover duplicate Unit writes, union followed by later Runs, actual Entry delivery,
scalar failure on either side of a constructor tail, inherited results and
source-ordered effective-write digests. Runtime unit tests and the README
compile/run/bench commands validate the local build separately.

```sh
python3 benchmarks/witness-prefix/measure.py MANIFEST TIMING_OUTPUT --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/marker-handoff/choice_diagnosis.py ARTIFACT_ROOT OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-dispatch-batches/check.py OUTPUT benchmarks/cell-dispatch-batches/results.json
```

`dispatch-probe.patch` applies to a separate checkout of `534bc384`; build it with
`cell-absorption,view-ports,parallel-publication` and run the frozen Raytrace program
with the arguments in `results.json`. Its stderr is a work diagnostic only.
Do not use that instrumented executable for performance comparison.
