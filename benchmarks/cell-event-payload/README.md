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

The following measurements are recorded separately after freezing this runtime.
Work-count reductions above do not by themselves pass the earlier performance
regression gate.
