# Inference CPU and completion diagnosis

This measures the actual standalone Cell CPU, not native egglog. It diagnoses
the unresolved sum-bits regression in the frozen publication integration:
`03065edb` versus `50e3822a`. Later main-branch merges do not move that comparison.
The runtime feature `inference-cpu` adds two boundary snapshots around
`runtime.execute()`. It does not enable `storage-metrics`, per-task tracing, or
periodic sampling. Both checkouts contain the exact same instrumentation files.

The previous catalog exposes independent index/Entry owners and charged duplicate
reads; it does not prove mutable reads or Run visibility redundant. No new Bake
catalog, stage switch or execution takeover is introduced here. The missing
evidence is CPU consumed within inference, separate from setup/export, together
with existing completion blocking spans. This is diagnosis, not a speedup claim.

## Reproduce

Use `codex/inference-cpu-control` and `codex/inference-cpu-candidate`, each one
instrumentation commit above its frozen base. Prepare both through the shared
compute queue:

```sh
eggfuse-job run --kind compute -- python3.14 benchmarks/cell-inference-cpu/run.py prepare CONTROL_CHECKOUT CANDIDATE_CHECKOUT out/cell-publication-integration/fresh target out/cell-inference-cpu
```

The script rebuilds the runtime release package before each freeze, checks source
and binary identity, verifies actual candidate path coverage, and checks fresh
states, Run summaries and effects against the accepted uninstrumented versions.
Native sum acceptance must pass and match the fresh CPU state hash; Raytrace
retains its differential checks, without extending the native contract.

From the clean diagnostic candidate checkout, submit one timing job with absolute
paths to the shared `quick.py` and output roots. Fix 15 sum and 7 Raytrace samples,
one warmup each. Run every control group before any candidate group:

```sh
eggfuse-job run --kind timing -- python3.14 /ABS/benchmarks/raytrace-parallel/quick.py --sum-repeats 15 --ray-repeats 7 /ABS/out/cell-inference-cpu/control /ABS/out/cell-inference-cpu/candidate /ABS/out/cell-inference-cpu/timing /ABS/out/cell-inference-cpu/timing.json
python3.14 benchmarks/cell-inference-cpu/run.py summarize out/cell-inference-cpu out/cell-inference-cpu/timing benchmarks/cell-inference-cpu/results.json
```

All samples, warmups and boundary guards are retained. Do not repeat a completed
trial just to improve its medians. Ordinary uninstrumented speed acceptance
remains the separate publication integration result.

## Meaning of the measurements

- Process user + system CPU includes every process thread during inference.
  Dividing it by wall time gives mean consumed cores, not utilization of four
  particular workers. CPU time can change with frequency/cache behavior too;
  it is not an instruction count.
- Coordinator CPU is the launching thread's CPU clock. Wall minus coordinator
  CPU includes blocking and OS preemption. It does not identify lock overhead.
- Process CPU minus coordinator CPU describes other threads collectively. It
  cannot identify which Cell or pool consumed it.
- Sampling calls bracket inference. Their small skew is reported separately as
  `boundary_capture_seconds`; derived differences are not silently clamped.
- Existing query, RHS and registry `event_wait_ns` time condition-variable waits,
  including descheduling/wakeup residence. They can nest and must not be summed
  into a graph-wide synchronization percentage.
- `scheduler.wait_ns` is the whole scope span, including source adoption.
  `births.worker_wait_ns` records much of the same span. They are preserved as
  scope measurements, not additional blocked time. See `runtime_cell_pipeline.rs`,
  `runtime_cell_queue.rs`, `completion_events.rs` and `completion_background.rs`.

The aggregation computes ratios per sample before taking medians. Independent
medians of CPU, wall and component spans need not add or divide consistently.

## Recorded result

Preparation job 104 froze `ec133804` (control) and `0d8e4d21` (candidate),
with identical instrumentation files above the two bases. Their distinct
executables pass exact final state, 1,428 sum / 16,883 Raytrace Run summaries,
logical effects and the unchanged native sum contract. The candidate executes
the intended admission/split paths. The CPU test verifies that a blocked
coordinator does not hide another thread's CPU; all six harness tests also pass.

Timing job 107 completed the predeclared 15/7 samples per lane with all 104 guards
clear. `results.json` records provenance, every measured sample and warmup,
checksums of the raw archives, and independently aggregated medians:

| Metric | sum control | sum candidate | Raytrace control | Raytrace candidate |
|---|---:|---:|---:|---:|
| Inference wall | 26.351 ms | 27.286 ms | 5.738 s | 5.484 s |
| Process CPU | 42.409 ms | 43.350 ms | 9.658 s | 9.665 s |
| Coordinator CPU | 24.210 ms | 25.453 ms | 4.474 s | 4.177 s |
| Other-thread CPU | 17.916 ms | 18.425 ms | 5.184 s | 5.489 s |
| Mean consumed cores | 1.586 | 1.583 | 1.680 | 1.762 |
| Coordinator off-CPU | 2.135 ms | 2.240 ms | 1.264 s | 1.308 s |
| Query event wait | 1.318 ms | 1.348 ms | 0.658 s | 0.648 s |
| RHS event wait | 1.448 ms | 1.485 ms | 0.050 s | 0.050 s |
| Registry event wait | 0.121 ms | 0.141 ms | 0.074 s | 0.069 s |

Boundary capture medians are 6.7–7.1 microseconds for sum and 10.8–10.9
microseconds for Raytrace. These are diagnostic builds, not replacement samples
for the ordinary `26.026 -> 27.763 ms` / `5.501 -> 5.396 s` comparison.

The sum wall median regresses 3.55%, process CPU 2.22%, and coordinator CPU
5.13%. Its measured event-wait medians change only by tens of microseconds;
this does not support attributing the median regression primarily to added
synchronization. Some candidate outliers contain substantial off-CPU time too
(the 51.31 ms sample has 14.92 ms). They remain in the result. Sequential order,
frequency/cache behavior and OS activity are not controlled sufficiently to
prove which instructions caused the CPU increase; no causal correction or
sample removal is applied.

Raytrace wall falls 4.42%, process CPU is almost unchanged (+0.07%), coordinator
CPU falls 6.65%, and mean consumed cores rises 4.93%. This agrees with the
known transfer of table publication work to workers, with charged duplicate
reads, rather than demonstrating removal of all that computation. Coordinator
off-CPU does not fall, and the named event-wait medians barely change. The
remaining 4.177 s of coordinator CPU and only 1.762 mean consumed cores make
coordinator work the next target; eliminating waits alone would leave that CPU
work in place. These aggregates do not identify a particular next Cell takeover
or prove full utilization. The two-workload speed gate remains unresolved.
