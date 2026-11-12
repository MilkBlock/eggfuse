# One completion slot through producer registration

This measures the actual standalone Cell CPU, not native egglog. The work-count
control is frozen `076a923a`; programs, catalogs, release features and arguments
are unchanged. This is the fifth implementation after timing checkpoint
`83ac944b`, following `c0dd0034`, `68fb07a4`, `4516c4a7` and `076a923a`.

## Opportunity from actual executions

The preceding Raytrace execution used fused producer registration for 12,204
Cells and 17,011 constructor rows. Each completed computation entered a prefix
slot array, then moved into a separate array after registration. The first
array alone accumulated 6,053,184 bytes of capacity; sum-bits accumulated
36,208 bytes. The compiled terminal constructor plan already proves the needed
dependency/effect boundary. A second copy of the queue's slot storage supplies
no additional proof or value.

The same original result now occupies one slot with three states: empty,
computed, and registered. A producer takes the existing directory owner and
continues the ready prefix outside the mutex. While it installs one Cell,
other workers may deposit computed inputs, and the source may consume earlier
registered outputs. A computed input never satisfies source readiness. Returning
ownership and testing the next computed input happen under the same mutex,
preventing a lost handoff. No second prefix array or second event mutex remains
in this covered path.

The result's bindings, actual reused witnesses, row allocations and fact slots
retain their original owners. This changes the completion store, not the Cell
facts or compiler representation. Shared Entry and iterative Bake still use
original instance slots across the original Run boundary. Catalog evidence is
compared unchanged; this does not invent a new cross-Run proof.

## Costs and live boundaries

The source's temporary ready vector remains; this change does not claim to
eliminate every result move. Registration still has one mutable directory owner
and still returns that owner before its readers resume. The fixed Run visibility
boundary, error/effect order, exact key checks, duplicate aliases, retirement
and failure-suffix invalidation are unchanged. Background admission and Unit
tails keep their existing handling. The implementation neither expands the
admitted region nor delays ongoing queries to obtain ownership.

Ordinary background completion has an uninhabited computed-state type. Tests
verify its actual Cell slot layout is unchanged. Continued completion uses a
tagged slot large enough for either the computed result or registered result;
its actual size is recorded, including the tag. Shared control/header capacity
and the source ready vector are still charged to event bytes. The historical
`constructor_fused_staging_bytes` field stays present and must be zero here.

Work counts and all added/removed capacity are retained in `results.json`.
Capacity is cumulative allocation capacity, not peak memory or an allocation
trace. No coverage, queue byte or early-completion counter establishes a speedup.

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Separate computed-prefix capacity, bytes | 36,208 / 0 | 6,053,184 / 0 |
| Total completion events plus that prefix, bytes | 1,060,536 / 1,024,040 | 193,037,352 / 189,394,560 |
| Cells through fused registration | 73 / 73 | 12,204 / 12,216 |
| Actual rows through fused registration | 91 / 91 | 17,011 / 17,035 |
| RHS dispatch regions | 247 / 247 | 9,064 / 9,062 |
| Second registration pool calls | 4 / 5 | 2,683 / 2,775 |
| All constructor rows registered by workers | 152 / 181 | 188,028 / 193,676 |
| Ordinary key lookups | 13,028 / 13,028 | 3,830,073 / 3,830,073 |
| Source execution frames | 5,176 / 5,176 | 1,020,600 / 1,020,600 |

The new slot is 600 bytes, the same as the old completed slot; it replaces that
slot plus a separate 496-byte computed slot. Across the entire execution,
combined completion capacity falls 3.44% / 1.89%. Raytrace's net reduction is
3,642,792 bytes, rather than the entire old prefix capacity, because event
arrival changes other event-buffer growth. Registration grouping also changes:
there are more second registration calls and registered rows in this execution.
Those counts and their additional capacities remain in the evidence, not hidden
behind the deleted-prefix metric. The eligibility proof itself is unchanged.

## Validation and reproduction

185 runtime tests and 89 relevant integration tests pass, plus forced hash/Bloom
collisions and all-feature, sparse-only and legacy checks. New tests hold the
first registration open while a later producer deposits its result, verify
that neither result is prematurely visible, then release the same source
prefix. Empty regions, producer/registration panics and reader lifetimes are
covered. Existing native-backed fixtures retain source Run snapshots through
same-Run reads, deletion, recreation and late union, for both foreground and
background admission. Prefix rollback and reused actual results remain covered.

README compile/run/one-repeat bench commands are smoke checks. Native sum-bits
acceptance returns `pass` and matches the fresh CPU export hash. Whole-state,
all 1,428 / 16,883 ordered Run summaries, logical effects, reverse occupancy and
Bake evidence match the preceding runtime; Raytrace remains differential
validation only.

Use fresh output directories. The checker requires successful validation and
README records using the commands in `results.json`. Local disk space is bounded
by running integration binaries sequentially and removing only generated test
executables after their successful recorded checks; sources and logs remain.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-completion-slots/run.py out/cell-fused-registration FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-completion-slots/check.py out/cell-fused-registration FRESH_OUTPUT RESULTS.json
```

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

The periodic comparison uses the existing shuffled harness, including every
warmup and sample. The immediate control isolates this completion-store change;
the preceding checkpoint charges the five cumulative implementations. Separate
stack samples are diagnostics, never timing samples.

```sh
python3 benchmarks/cell-completion-slots/prepare_timing.py ARTIFACT_ROOT
python3 benchmarks/cell-completion-slots/campaign.py ARTIFACT_ROOT
python3 benchmarks/raytrace-thread-bottlenecks/profile.py ARTIFACT_ROOT/ray-manifest.json ARTIFACT_ROOT/timing-ray/samples.json ARTIFACT_ROOT/profile-control4 --lane control4 --duration 3 --interval-ms 2 --start-delay 0.6
python3 benchmarks/raytrace-thread-bottlenecks/profile.py ARTIFACT_ROOT/ray-manifest.json ARTIFACT_ROOT/timing-ray/samples.json ARTIFACT_ROOT/profile-candidate4 --lane candidate4 --duration 3 --interval-ms 2 --start-delay 0.6
python3 benchmarks/cell-completion-slots/timing_check.py ARTIFACT_ROOT TIMING_RESULTS.json
```

## Fifth-change timing gate: failed

Runtime `8df9de2a` is frozen before the campaign. All four revisions are
remeasured with the same programs/catalogs and release flags, with one and four
workers. Each lane has one warmup followed by five sum-bits or three Raytrace
samples, in a recorded shuffled order. All 80 executions, including 16 warmups,
have exact final states, ordered Run-summary hashes and logical effects. No
timing sample is discarded or rerun. Background observations record no compiler
activity; ambient desktop load is still possible.

| Inference median | Historical `8335929d`, 1 / 4 workers | Last checkpoint `916ebf7c`, 1 / 4 | Immediate control `076a923a`, 1 / 4 | Current `8df9de2a`, 1 / 4 |
| --- | ---: | ---: | ---: | ---: |
| sum-bits, ms | 17.705 / 20.887 | 18.158 / 21.804 | 18.762 / 24.939 | 18.445 / 25.283 |
| Raytrace, s | 5.815 / 5.108 | 5.924 / 5.034 | 5.971 / 5.142 | 5.961 / 5.178 |

Against the immediate control, four-worker medians regress **1.38% / 0.69%**;
iteration-paired medians regress 1.30% / 0.49%. All five sum-bits pairs are
slower, while one of three Raytrace pairs is faster. The Raytrace difference
is small relative to the control's 5.031–5.273 s variation. This change has
removed storage but has not passed the two-workload speed criterion.

Against the five-change checkpoint, four-worker medians regress **15.95% /
2.87%**, with paired median regressions of 20.02% / 2.90%; every paired comparison
is slower. The cumulative work also fails the performance gate. The historical
four-worker runtime is faster on both workloads. Earlier campaigns' quoted
24.77 ms / 5.389 s must not be substituted for this campaign's controls.

Raytrace scales only 1.151x from one to four workers, versus checkpoint 1.177x;
sum-bits gets slower with four workers. Current four-worker process CPU/wall
averages about 1.42 cores, including load/export, not inference-only utilization.

## Where the cumulative extra work appears

| Four-worker phase median | Last checkpoint | Immediate control | Current |
| --- | ---: | ---: | ---: |
| sum-bits RHS, ms | 5.759 | 8.972 | 9.124 |
| sum-bits search, ms | 11.102 | 11.008 | 11.232 |
| Raytrace RHS, s | 1.762 | 1.923 | 1.934 |
| Raytrace search, s | 1.732 | 1.726 | 1.736 |
| Raytrace publication/query update, s | 1.011 | 0.993 | 1.010 |
| Raytrace repair, s | 0.484 | 0.470 | 0.467 |

RHS is the main phase showing growth. Phase medians do not add to the median
total and do not isolate lock or dispatch time. The recorded actual executions
show the structural change behind the next investigation:

| Work since `916ebf7c` | sum-bits checkpoint / current | Raytrace checkpoint / current |
| --- | ---: | ---: |
| Local jobs | 255 / 984 | 81,223 / 210,835 |
| RHS dispatch regions | 72 / 247 | 3,406 / 9,062 |
| Constructor operations on workers, including reuse | 386 / 1,335 | 127,059 / 324,431 |
| Ordinary key lookups | 14,012 / 13,028 | 4,027,756 / 3,830,073 |
| Source execution frames | 5,173 / 5,176 | 1,020,508 / 1,020,600 |

The new root path avoids ordinary lookups but adds 1,912 / 278,896 root bucket
probes, including 928 / 80,760 fallbacks. More worker work now travels through
many more regions; source instance setup/adoption has not disappeared. This is
not an isolated causal decomposition of all elapsed time, but it rules out
treating increased worker coverage as a speedup. The checker links this work to
the saved root-birth control evidence and verifies matching programs, states,
Run summaries and logical effects.

Code inspection finds a concrete remaining artificial boundary:
`apply_cell_batch` creates a fresh `Ready` queue for each rule and unconditionally
drains it at the end; `Executor::run` calls it separately for each patch group.
That rule-local lifetime is not itself a compiler proof of a necessary fence.
The next takeover should retain compatible Cell continuations across rule groups
within the same sealed source Run, draining at real dependency/effect/visibility
boundaries. Existing scalar-write ownership, absorbed Cells, fallback effects,
source errors and the original Run end must be audited explicitly. Do not just
raise queue capacity or weaken those obligations. Query/ordinary RHS paths still
need later integration; this is not full worker ownership or thread saturation.

## Separate waiting diagnostics

Successful three-second, two-millisecond-interval profiles cover 885 main-thread
inference samples in each lane, with progress logging disabled. Inclusive counts
overlap; they are neither additive phase time nor CPU utilization.

| Main-thread sampled residence | Immediate control | Current |
| --- | ---: | ---: |
| Condition waits | 21.92% | 23.84% |
| Query finishing, including waits | 15.59% | 16.05% |
| Finished-table publication, including waits | 20.00% | 20.34% |
| Repair | 11.98% | 11.41% |

Worker wait fractions range 73.2%–81.2% in control and 70.2%–78.4% in current,
predominantly pool idle. Current source wait contexts include 97 query, 78
publication, 12 scalar-write and 24 other samples. Fewer worker wait samples
have not translated to a throughput gain. Neither these short windows nor the
small immediate-control timing delta isolates the new shared mutex's cost.

Two candidate diagnostic exports failed with ENOSPC after their state export;
their failed logs and losslessly archived artifacts remain under
`profile-candidate4-disk-failure` and `profile-candidate4-disk-retry-failure`.
They are excluded diagnostics, not timing samples or semantic passes. After
removing the already-validated generated debug runtime/compiler libraries, the
diagnostic completed and passed exact state/Run checks. No performance sample
was repeated. Library paths/sizes and failed-log hashes are recorded locally
and in the timing evidence respectively. The validated native sum proof is
unchanged; native Raytrace equivalence is still outside its scope.
