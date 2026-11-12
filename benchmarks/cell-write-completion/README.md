# Write completion events transfer the lifecycle owner

This checkpoint covers the actual standalone Cell CPU, not native egglog. The
work-count control is `c27cbcf1`; frozen programs and catalogs are unchanged.
The periodic whole-runtime comparison below includes this change and the five
implementations since `2ae7b97e`. It has not established a stable speedup.

## Opportunity and compiler proof

The preceding Raytrace execution had 793,538 distinct scalar write targets and
755,389 changed rows. Their inputs and actual writes already ran on workers,
but every target returned through a full `Finished` vector before the source
thread retired writers, retained parents, installed producer-directory entries,
updated membership/subscriptions and recorded table changes.

The existing Eq-to-i64 Cell `PortWrite` plan, old/min/max merge proof, immutable
constructor-parent restriction and input-ready/checked-arithmetic boundary make
this region independent of mutable reads and union. Original source ordinal
still determines same-key winners. Target-index order determines lifecycle
retirement exactly as before, including releases that affect a later retained
writer. These typed compiler facts permit the existing table owner to finish
the region; no new runtime fact graph, bindings or producer-consumer lists are
created. Across Runs, the same Cell switch and Shared Entry projections consume
the final rows at their original visibility boundary.

## Connected path

The existing target array owns original mutable Function/decoded-row references
and candidate slices. Workers compute blocks of up to 64 targets and leave
completion metadata in that same array. A completed block transfers its original
slice to the ready-prefix slots. Any worker can take the single lifecycle owner
and consume the ready target prefix while other blocks continue computing.

The event mutex protects only publication and transfer of those original owners.
Retirement, parent-reference updates, writer-directory installation, membership,
ordinary subscription replacement and change notifications run **outside** that
mutex. Other producers can publish and continue while the owner is active. The
owner is returned and readiness checked under the same lock, preventing lost
handoffs. There is no waiting receiver or condition-variable barrier, including
with one worker. Fatal worker/consumer panics still join other jobs and unwind;
this is not a general rollback promise for panics.

The old full `Finished` vector and source per-target maintenance loop are gone.
Ordinary Graph retirement and worker retirement use one shared implementation
over the same directory, Cell storage, parent counts and garbage set. Likewise,
both paths use the same subscription replacement algorithm. For a new typed
scalar row, the Eq input is already canonical in this epoch; inspecting the
i64 output and rereading the row through Graph are unnecessary. Its real Eq
reverse subscription remains present.

Lifecycle work on shared maps remains ordered under one owner. It is overlapped
with row computation, not declared independently parallel. Cell publication,
Cursor processing, constructor-index adoption, ordered effects and the original
Run visibility fence remain outside this takeover. The pool still joins before
returning to source publication; this does not eliminate every batch boundary.

## Work and cost

Features and flags match the preceding checkpoint:

```text
features: cell-absorption,view-ports,parallel-publication
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Target rows whose lifecycle/notifications finish on workers | 0 | 793,538 |
| Actual changed rows | 755,389 | 755,389 |
| Worker completion blocks | 0 | 14,067 |
| Blocks fully retired with other write blocks unfinished | 0 | 4,746 |
| Write pool calls | 3,660 | 3,660 |
| All scalar-write payload capacity, cumulative bytes | 197,995,912 | 181,969,416 |
| Event task/slot payload capacity, cumulative bytes | 0 | 450,144 |
| New scalar subscriptions | 4,385 | 4,385 |
| Global query lookups | 4,027,756 | 4,027,756 |

The new event payload is included in total temporary capacity. The 16,026,496
byte reduction is cumulative capacity, not peak memory or a complete allocation
trace. A single target allocation replaces independently grown target and
completion arrays; original row payloads and successful input slots are reused.
Scheduling and short mutex acquisitions add work. The overlap counter checks
actual unfinished computations **after** retiring a block, not queued callbacks;
it is neither CPU utilization nor saved elapsed time.

Typed subscription completion omits 4,385 scalar field visits and root rereads;
subscription calls, reverse-edge occupancy and all reverse-index operations
remain exact. Duplicate candidates, invalidations, final writes, logical
improvements, writer reuse and extra new-key probes also remain exact. sum-bits
has no eligible scalar write batches and retains 14,012 global lookups.

`execution_ns` now includes event retirement, while `boundary_ns` contains only
source setup. Their old and new subdivisions are not directly comparable and
are not isolated wait measurements. The complete timing campaign must determine
whether this and the preceding changes repay their dispatch/storage costs.

## Validation

158 runtime tests and 85 relevant integration tests pass, plus forced hash/Bloom
collision checks, all-feature, sparse-only and legacy builds. A handshake test
blocks a later producer until an earlier prefix retires; whole-batch retirement
would time out. Tests cover empty/single-worker work, reordered completion,
producer and consumer panic, retained writer promotion, later garbage collection,
membership and subscription consistency. Existing min/max/old fixtures compare
source effect digests, duplicate writes, union and downstream Run snapshots.
The checked-arithmetic failure path still preserves the original effect prefix.

Frozen sum-bits/Raytrace final exports, all 1,428 / 16,883 ordered Run summaries
and logical effects match `c27cbcf1`. Run summaries are not whole-graph snapshots;
the small integration fixtures cover those boundaries. Native sum-bits acceptance
is `pass`, with its saved CPU export hash checked against this execution.
Raytrace remains an exact differential check, not an extended native proof.
The README compile/run/single-repeat bench smoke commands also pass.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-write-completion/semantic-acceptance.json
python3 benchmarks/cell-write-completion/check.py out/cell-write-owner out/cell-write-completion benchmarks/cell-write-completion/results.json
cargo cell-compile --case sum-bits --output out/cell-write-completion/readme-program
cargo cell-run --program out/cell-write-completion/readme-program/program.json --output out/cell-write-completion/readme-run
cargo cell-bench --program out/cell-write-completion/readme-program/program.json --repeat 1
```

Use fresh output directories for the Cargo smoke commands. Historical timings
are not used as an apples-to-apples claim about this runtime.

## Periodic whole-runtime checkpoint

The eight lanes use the same frozen program, catalog, release features and flags
above. Each has one warmup, followed by five sum-bits or three Raytrace samples.
All lanes are interleaved in a recorded shuffled order. No local compilation is
active during timing. The pre-event historical runtime is `8335929d` (saved at
`cf452ed6`); the last full checkpoint is `2ae7b97e`, immediate control is
`c27cbcf1`, and current runtime is `79e6fe0f`. These are newly measured binaries
in this one campaign, not a comparison of timings from different dates.

| Inference median | Historical 1 / 4 | Last checkpoint 1 / 4 | Immediate control 1 / 4 | Current 1 / 4 |
| --- | ---: | ---: | ---: | ---: |
| sum-bits, ms | 18.325 / 21.569 | 19.112 / 22.345 | 19.383 / 22.547 | 19.249 / 24.771 |
| Raytrace, s | 5.979 / 5.238 | 6.199 / 5.811 | 6.154 / 5.166 | 5.871 / 5.389 |

Current four-worker medians regress **9.86% / 4.31%** against the immediate
control. Against the five-change checkpoint, sum-bits regresses 10.86% while
Raytrace improves 7.26%. Against the pre-event runtime, both four-worker
medians regress (14.84% / 2.89%). This does not pass the two-workload performance
criterion. Current Raytrace scales only 1.089x from one to four workers;
sum-bits becomes slower. Whole-process CPU/wall averages about 1.36 cores on
four-worker Raytrace, including load and export, not inference-only utilization.

Variation is material. The immediate-control Raytrace four-worker samples are
5.422, 5.166 and 5.059 s; current samples are 5.389, 6.149 and 5.059 s. Ratios
within the same interleaved iteration give a median change of +0.012%, unlike
the +4.31% ratio of lane medians. The five-change comparison has an iteration
paired median change of -0.82%, rather than -7.26%. Neither estimator establishes
a stable causal improvement from three pairs. sum-bits current samples range
22.27–28.19 ms and this scalar path has zero coverage there. No outlier is
removed, and no replacement campaign is used to obtain a favorable result.
The saved background snapshot shows other active desktop processes; it does
not isolate the cause of the variation.

All 80 executions, including 16 warmups, have exact final-state hashes, ordered
Run-summary hashes and logical-effect counts. [timing-results.json](timing-results.json)
keeps every sample/warmup, lane identity, execution order, both comparisons,
background observations and the separate profiles. The unchanged native
sum-bits proof is linked by its CPU state hash. Raytrace remains differential
validation only.

## Remaining waits and next takeover

Separate five-second macOS stack samples compare immediate control and current
four-worker Raytrace, with progress logging disabled. More than 98% of the main
thread window lies under inference. These diagnostic executions are not included
in timing samples. The profile's inclusive counts overlap; do not sum them or
interpret them as CPU consumption or isolated lock cost.

| Main-thread sampled residence | Control | Current |
| --- | ---: | ---: |
| Condition-variable waits within inference | 17.64% | 20.33% |
| Query finishing, including its waits | 13.72% | 12.74% |
| Entry `Scheduler::batches`, including callbacks | 12.28% | 11.61% |
| Finished-table publication, including its waits | 20.71% | 21.64% |
| Repair | 9.73% | 9.54% |
| Scalar write region, including pool wait | 3.14% | 3.64% |

Workers spend 79.6–83.3% of control samples and 78.1–82.7% of current samples
in condition-variable waits. These include pool-idle and inside-job waits,
and are not utilization percentages. The current main-thread wait samples
split into publication 134, queries 121, scalar writes 58 and other 11; the
total inference sample count is 1,594. Symbolication and optimized inlining
limit attribution. The stacks confirm worker execution of `Completion::accept`,
but the source still waits for the scalar pool before Cell publication.

The remaining ownership boundaries are therefore concrete:

1. Query admission still traverses `Scheduler::batches` and its source callback
   before `finish_queries`; source Cursor sealing and the Run error fence remain.
   The inclusive profile alone cannot identify how much is enumeration versus
   callback work. Next inspect the callback's Entry/route ownership and reuse
   the existing Cell input layout before adding more tasks or queues.
2. Finished-table publication still joins table/index tasks before launching
   the condition DAG. The existing DAG already releases parents from child
   events, but it does not yet consume independent table-ready events. A next
   takeover must join only the tables and children required by each condition,
   while retaining index validity and the original Run visibility boundary.
3. Shared constructor adoption, ordered mutable effects and ordinary repair
   remain outside scalar ownership. Allowing duplicate private rows is already
   useful, but exact adoption, actual result aliases and lifecycle checks still
   have to complete. Moving these to workers without removing their global
   rendezvous does not by itself create more parallel work.

The immediate priority is the first two boundaries, whose remaining source work
and waits are larger than this scalar region. More migrated rows or fewer
barriers alone will not count as a performance result.

Reproduce the campaign using fresh output directories and the recorded manifest
paths (runtime/program hashes are verified by the checker):

```sh
python3 benchmarks/witness-prefix/measure.py out/cell-write-completion/sum-manifest.json out/cell-write-completion/timing-sum --repeat 5 --warmups 1 --timeout 120
python3 benchmarks/witness-prefix/measure.py out/cell-write-completion/ray-manifest.json out/cell-write-completion/timing-ray --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-write-completion/ray-manifest.json out/cell-write-completion/timing-ray/samples.json out/cell-write-completion/profile-control4 --lane control4 --duration 5 --interval-ms 2 --start-delay 0.5
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-write-completion/ray-manifest.json out/cell-write-completion/timing-ray/samples.json out/cell-write-completion/profile-candidate4 --lane candidate4 --duration 5 --interval-ms 2 --start-delay 0.5
python3 benchmarks/cell-write-completion/timing_check.py out/cell-write-completion benchmarks/cell-write-completion/timing-results.json
```
