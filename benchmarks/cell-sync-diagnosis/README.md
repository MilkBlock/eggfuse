# Raytrace synchronization diagnosis

This measures the **actual standalone Cell CPU executor**, not native egglog.
The normal executable is the frozen `3dc84223` four-worker candidate from
[cell-entry-owned](../cell-entry-owned/README.md). No new production optimization
is enabled here. Diagnostic code is gated by `cell-sync-diagnostics`.

The evidence supports two different findings: query/publication handoffs are
material, while the newly added terminal Unit registration handoffs are small
in the full workload. Workers still spend most of the sampled window idle in
the pool while substantial work runs on the coordinator.

## Evidence

Two five-second wall-stack samples with progress logging **disabled** show:

| Observation | Sample 1 | Sample 2 |
| --- | ---: | ---: |
| Main-thread samples / inference samples | 1,569 / 1,564 | 1,576 / 1,575 |
| Main condition-variable wait | 17.34% | 18.15% |
| Wait under query work | 159 samples (10.13%) | 154 (9.77%) |
| Wait under publication | 80 (5.10%) | 92 (5.84%) |
| Wait under scalar RHS writes | 21 (1.34%) | 26 (1.65%) |
| Wait under the Cell ready queue | 12 (0.76%) | 14 (0.89%) |
| Each worker's total condition wait | 84.4%–86.9% | 82.7%–85.4% |
| Each worker's pool-idle wait | 80.6%–86.1% | 79.8%–85.3% |

These are **wall-stack residences, not CPU utilization or removable overhead**.
Waiting for useful worker computation also parks the coordinator. Worker
`inside_job` waits can include Rayon joins; the samples do not establish that
these are graph conflicts or unresolved Cell inputs. The two original samples
with progress logging are retained as well; logging occupied 7%–9% of their
main-thread stacks, motivating the separate quiet samples. Quiet sampling starts
0.5 seconds after launch, calibrated from the approximately 0.4-second logged
startup; actual inference coverage above is checked from the stack tree.

Main-thread inclusive stacks in the quiet samples place `Executor::matches` at
27%–29%, `Scheduler::batches` at 15%–18%, `publish_finished_tables` at 19%–21%,
and `repair_selected` at about 10%. **These overlap and must not be added.**
`Scheduler::batches` is within matching, and publication includes its pool waits.
Other visible source work includes boundary resolution, subscriptions and Cell
startup. This is evidence for moving/removing coordinator work, not a proof
that all of it can execute concurrently under the current ownership model.

## New registration path: bounded ablation

All three lanes use identical frozen input and four-worker flags:
`--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1`.
`pool` and `inline` use the **same diagnostic binary**. Only the two terminal
Unit registration loops change host; classification, compact IDs, row adoption,
index updates, activation order and visibility remain the same.

One warmup and three interleaved samples per lane, none discarded:

| Lane | Inference samples (s) | Median (s) |
| --- | --- | ---: |
| Normal frozen binary | 6.183, 5.305, 6.277 | 6.183 |
| Diagnostic, pooled registration | 6.091, 5.490, 6.199 | 6.091 |
| Diagnostic, inline registration | 6.044, 5.441, 6.081 | 6.044 |

There is active background system storage work and considerable timing noise.
This small experiment does not establish a general speedup or a diagnostic
instrumentation overhead percentage. The more directly bounded measurements are:

- 818 accepted batches, each with two pool calls: 1,636 new dispatches.
- Calls average two table tasks. Splitting such a batch by table alone supplies
  only two runnable tasks.
- Registration including host preparation/finalization: **38.39 ms** median
  pooled, **26.98 ms** inline. The difference is **11.41 ms**, about **0.19%**
  of pooled diagnostic inference. This is a net algorithm placement difference,
  including lost parallelism and changed locality, not pure synchronization time.
- Pooled registration intervals with **no registration task active** total
  **14.43 ms** median, about **0.24%** of inference. These include dispatch,
  wakeup, scheduling, return and instrumentation overhead. They do not measure
  all synchronization in the runtime.
- The entire measured registration path is about **0.63%** of inference.
- Source adoption for these registered batches is another **101.76 ms** median;
  this is outside the two registry loops and remains on the coordinator.
- In sum-bits these registration batches are **zero**. They cannot directly
  explain its previously observed 7.3% regression.

The coarse query completion call measured 17.84 ms host preparation, 444.48 ms
inside execution/joins, and 84.18 ms afterward (individual medians). Its prepare
counter starts at `finish_queries`; it **does not include** the much larger
preceding `Executor::matches` / Entry enumeration. Constructor ready-queue
execution/joins measured 61.26 ms. Neither pool timer is pure wait, and neither
covers all other runtime pool entrypoints. `source_adoption_ns` can include
nested work and must not be added blindly to other phase totals.

## What the current catalog tells us to do next

The latest actual executions already identify which opportunities are large:
1,783,538 individual Entry headers remain, alongside 1,996,849 entries already
enumerated from worker-owned ranges. Shared Cell/Cursor facts can support
further range admission and eliminate repeated source preparation; merely
increasing the number of small registry tasks has limited absolute scope here.

A scheduled Cell switch can discharge proven input binding, existing-witness
lookup and internal result publication across Runs. The compiler must prove
matched/completed operations, actual result provenance, terminal effects and
fixed Entry projections. Remaining obligations include delta ownership,
foreign-result forwarding, generations, retirement, mutable effect order and
original source Run visibility. A switch cannot make those facts true by itself.

Priority is therefore the remaining Cell/Entry preparation and publication
handoffs, retaining instances and ownership over a longer execution span. The
current diagnostic adds no new fact graph, does not claim a new takeover and
does not count avoided queries from hypothetical Bake composition.

## Counters and validation

`stats.sync_diagnostics` records each selected call's host prepare, pool/inline
execution and post-join interval. Registry tasks additionally record first/last
execution, elapsed task residence, per-worker counts and a concurrency-time
histogram. The event sweep checks simultaneous/adjacent/zero-duration tasks.
`collect.py` verifies wall-time partitions and weighted task-time identities.
For coarse query/constructor phases, `traced_calls == 0`: zero gap fields mean
**not collected**, rather than zero synchronization. Task residence includes OS
descheduling; task clocks and histogram allocation perturb diagnostic builds.
The ordinary build has no added clocks, task-span fields or environment reads.

142 runtime tests pass. Relevant integration suites pass (35 Cell execution,
14 Entry publication, 14 query-worker tests); the 35 execution tests also pass
with inline registration, including exact intermediate Run snapshots, duplicate
writes, scalar failure, union invalidation and visibility. One work-counter
comparison now excludes only the optional wall-timer object. An initial test
launch encountered an invalid cached executable; rebuilding that artifact
allowed all runtime tests to execute and pass.

All timing/profile Raytrace runs preserve the frozen final-state and ordered
16,883 Run hashes. Timed runs also retain the logical effect and registration
counts. Both diagnostic sum-bits modes retain the frozen state, effect counts
and 1,428 ordered Run summaries. The unchanged `choice_diagnosis.py` returns
`pass` using saved native exports whose CPU state hash equals both new runs.
This is the reviewed sum-bits native contract; Raytrace uses frozen state/Run
comparison, not an extended native-choice proof. README compile/run/bench
commands are checked separately from these diagnostic timings.

## Reproduction

Use fresh output paths. Retain the previous `out/cell-entry-owned` frozen
executables, programs, reference reports and semantic exports described there.
Build the runtime with `cell-absorption,view-ports,parallel-publication` plus
`cell-sync-diagnostics`, and copy it to `out/cell-sync-diagnosis/diagnostic-runtime`.
Construct a three-lane manifest from the previous Raytrace candidate manifest:
`normal` keeps that executable; `pool` and `inline` use the diagnostic executable
with `environment.CELL_SYNC_REGISTRY_INLINE` set to `"0"` / `"1"`. Keep all other
arguments and the program identical. Hashes and environments are in results.json.

```sh
python3 benchmarks/raytrace-parallel/measure.py out/cell-sync-diagnosis/manifest.json out/cell-sync-diagnosis/timing --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-sync-diagnosis/manifest.json out/cell-sync-diagnosis/timing/samples.json out/cell-sync-diagnosis/profile-1 --lane normal --duration 5 --interval-ms 2
# Repeat as profile-2. Then run two quiet profiles with --start-delay 0.5,
# named quiet-profile-1 and quiet-profile-2. Do not sample during timing runs.
# Run the diagnostic binary on the frozen sum program as sum-0 / sum-1,
# with CELL_SYNC_REGISTRY_INLINE=0 / 1 and the same candidate CLI flags.
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-sync-diagnosis/semantic-acceptance.json
python3 benchmarks/cell-sync-diagnosis/collect.py out/cell-sync-diagnosis out/cell-entry-owned benchmarks/cell-sync-diagnosis/results.json
```
