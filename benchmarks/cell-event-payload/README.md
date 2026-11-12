# Query completions carry only task-produced accounting

This is the actual standalone Cell CPU, not native egglog performance. The
work-count control is `f48eb140`. Programs, catalogs, features and runtime flags
are unchanged. This is implementation five since the last full timing campaign;
the separate periodic checkpoint below determines performance acceptance.

## Opportunity and scope

The preceding Raytrace execution issued 77,621 query chunks. Each completion
contained the entire executor `Counts`, including source-only queue admission,
Cell template capacity, event counters and per-worker arrays. Residual query
completion contained another copy and the entire residual executor `Work`.
Those fields remained zero in a worker task, but their storage, initialization
and movement were still part of the task/event representation.

The existing Cell instruction host determines exactly which query, guard,
constructor and local RHS counters a task can produce. Source scheduling and
per-worker aggregate totals are properties of the executor, not an individual
Cell execution. The same compiled switch and Entry projection remain authoritative
across Runs; there is no new learning catalog, binding copy or fact graph here.
This change removes unnecessary per-task state before the next timing checkpoint.

## Removed work and accounting

The executor keeps its original full statistics record. Query hosts use only
task-produced `Counts`; residual hosts similarly use `InputWork`. Source helpers
cannot accidentally receive a task counter record in place of executor stats.
Existing aggregation retains every old report key, constructor/read count,
execution count, coverage decision and worker attribution. No synchronization,
query, binding, actual effect or publication behavior is changed.

| Release layout | Previous per task | Current per task |
| --- | ---: | ---: |
| Query accounting | 1,480 bytes | 736 bytes |
| Residual input accounting | 544 bytes | 136 bytes |

The full query/executor and residual/executor records remain 1,480 / 544 bytes
once per executor. They no longer appear in every completion. The current
completion event is 2,064 bytes with the normal experiment features. Both the
point and residual task records used by a mixed completion shrink.

| Frozen observation | sum-bits control / current | Raytrace control / current |
| --- | ---: | ---: |
| Query chunks | 920 / 920 | 77,621 / 77,621 |
| Event/task capacity, cumulative bytes | 10,065,856 / 7,395,184 | 211,929,984 / 155,041,976 |
| Answer allocation/growth events | 1,116 / 1,116 | 189,499 / 189,499 |
| Answer capacity, elements | 7,843 / 7,843 | 2,315,372 / 2,315,372 |

Event capacity decreases about 27%; this is cumulative capacity, not peak live
memory, allocator traffic or an elapsed-time saving. Completion arrival can
change queue capacity, so exact capacity totals are observations of these runs.
Coverage/answer-span heap spill is separately retained and unchanged. The source
still retains completed chunk accounting until read-view release; this change
does not claim to remove that final aggregation or the source Run fence.

## Validation

163 runtime tests, 87 relevant integration tests and 20 forced hash/Bloom
collision tests pass. All-feature, sparse-only and legacy builds pass. The README
compile/run/single-repeat bench smoke also passes. This layout-only change reuses
the existing error, origin, deletion, late input, union and Run visibility tests.

Both frozen final exports and all 1,428 / 16,883 ordered Run summaries match the
control, along with logical effects, Sieve counts, query work, iterative Bake
evidence and coverage decisions. Run summaries do not replace full intermediate
graph tests. Native sum-bits acceptance is `pass`, linked to the new CPU export by
hash. Raytrace is exact differential validation, not an extended native proof.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

The frozen binary and program paths are in `out/cell-event-payload/manifest.json`.
Use fresh output directories for the Cargo commands:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-event-payload/semantic-acceptance.json
python3 benchmarks/cell-event-payload/check.py out/cell-query-coverage out/cell-event-payload benchmarks/cell-event-payload/results.json
cargo cell-compile --case sum-bits --output out/cell-event-payload/readme-program
cargo cell-run --program out/cell-event-payload/readme-program/program.json --output out/cell-event-payload/readme-run
cargo cell-bench --program out/cell-event-payload/readme-program/program.json --repeat 1
```

## Periodic timing gate

The runtime is frozen at `7b13f259`. All four revisions are remeasured in this
campaign with the same programs, catalogs, release features and flags. Each
revision uses one and four workers: one warmup followed by five sum-bits or three
Raytrace samples, interleaved in a recorded shuffled order. All 80 executions,
including warmups, have exact final hashes, ordered Run-summary hashes and
logical effects. No timing sample is discarded or replaced.

| Inference median | Historical `8335929d`, 1 / 4 | Pre-regression `c27cbcf1`, 1 / 4 | Prior checkpoint `79e6fe0f`, 1 / 4 | Current `7b13f259`, 1 / 4 |
| --- | ---: | ---: | ---: | ---: |
| sum-bits, ms | 18.268 / 21.739 | 19.519 / 22.566 | 18.742 / 22.435 | 18.171 / 23.185 |
| Raytrace, s | 5.668 / 5.105 | 5.789 / 5.119 | 5.762 / 5.079 | 5.910 / 4.862 |

The current four-worker Raytrace median improves 5.03% against the pre-regression
control and 4.27% against the preceding five-change checkpoint. All three paired
Raytrace comparisons improve against both; the respective paired median changes
are -5.57% and -4.27%. This is a modest observed improvement, not evidence of
saturated workers or an isolated effect of the last accounting-layout change.

sum-bits four-worker medians regress 2.74% / 3.34% against those same controls,
with paired median changes +3.35% / +0.95%. Its samples vary materially and its
current single-worker median is lower. **The two-workload speed criterion still
fails.** The historical four-worker configuration also remains faster on sum-bits.
The prior campaign's 24.771 ms / 5.389 s values are not the control measurements
in this campaign; comparing across those campaigns would overstate recovery.

Current Raytrace scales 1.216x from one to four workers, versus 1.131x for the
pre-regression control. Current single-worker Raytrace is 2.09% slower than that
control, so the parallel path still carries additional total work. Four-worker
process CPU/wall averages about 1.31 cores (control 1.24), including load and
export. It is not inference-only CPU utilization.

Phase medians localize the observed improvement; medians need not sum to the
median total and they do not isolate mutex or handoff time:

| Four-worker Raytrace phase, seconds | Pre-regression | Current |
| --- | ---: | ---: |
| Search | 1.840 | 1.692 |
| Query-index update / publication | 1.055 | 0.977 |
| RHS | 1.726 | 1.719 |
| Repair | 0.458 | 0.459 |

Thus the query/publication changes improved those phases, while the broader RHS
and repair paths barely changed. The measurements do not establish which of the
five changes produced each saving. Smaller tasks and migrated work counts alone
remain insufficient to accept a speedup.

## Remaining waiting and next ownership boundary

Separate three-second, two-millisecond-interval macOS stack samples cover only
inference with progress logging disabled. They are not timing samples, and they
cover a partial execution window. Inclusive stack counts overlap; neither the
main entries nor worker waits are additive CPU utilization measurements.

| Main-thread sampled residence | Pre-regression | Current |
| --- | ---: | ---: |
| Condition waits | 20.07% | 23.16% |
| Entry `Scheduler::batches`, including callbacks | 10.26% | 9.58% |
| Query finishing, including waits | 14.94% | 16.82% |
| Finished-table publication, including waits | 21.85% | 21.94% |
| Repair | 11.71% | 11.80% |

Worker condition-wait fractions remain 75.3%–81.1% in the current sample, mostly
pool-idle contexts, versus 76.5%–81.2% in the control. The current main-thread
sample has 106 query-wait samples, 85 publication-wait samples, 16 scalar-write
wait samples and one other wait out of 898 inference samples. These observations
show that the remaining barriers and source work still leave workers idle.

Source-side `start_cell_execution`, constructor adoption/collision and ordinary
subscription/retirement maintenance remain visible. `adopt_cell_event` still
restores an RHS owner and calls `commit_local_job` / `finish_attached_cell` on the
source. The next structural investigation should identify which of these actual
constructor-result, index and lifetime obligations a compiled Cell owner can
finish directly. Private duplicate rows can still be computed and invalidated;
actual returned aliases, ordered effects/errors and visibility must remain exact.
Expanding an already-small Unit registration path alone would not address the
unchanged 1.719-second RHS phase.

For small Runs, the sum-bits result also requires addressing dispatch and join
costs using real Cell work, rather than forcing more pool calls. The existing
eight-row filter weight is a heuristic, not a demonstrated optimum. This report
does not claim either follow-up has been implemented.

Fifty-six separate background snapshots recorded no compiler process during the
campaign. Other desktop activity remains possible; these OS snapshots cannot
prove isolated hardware or exclude shorter background work. The normal measurement
harness, sample order, raw samples, profiles, binary/program hashes, native proof
and background checks are retained in [timing-results.json](timing-results.json).

Reproduce with the recorded manifests and fresh timing/profile output locations:

```sh
python3 benchmarks/cell-event-payload/campaign.py ARTIFACT_ROOT
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-event-payload/ray-manifest.json out/cell-event-payload/timing-ray/samples.json out/cell-event-payload/profile-control4 --lane control4 --duration 3 --interval-ms 2 --start-delay 0.5
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-event-payload/ray-manifest.json out/cell-event-payload/timing-ray/samples.json out/cell-event-payload/profile-candidate4 --lane candidate4 --duration 3 --interval-ms 2 --start-delay 0.5
python3 benchmarks/cell-event-payload/timing_check.py out/cell-event-payload benchmarks/cell-event-payload/timing-results.json
```
