# Merged Cell CPU multithread checkpoint

Frozen current code: `9ac332c4`. This measures the **standalone Cell CPU**, not
native egglog. The subsequent canonical-subscription change is not included.
Host: Apple M3 Max, 16 physical/logical cores, 48 GiB RAM, macOS 27.0.1.

Complete programs, interleaved lanes, one warmup per lane, seven sum-bits and
five Raytrace repetitions. All samples and warmups are retained in
[results.json](results.json); no allocator/progress profiling in timing runs.
The unchanged harness verifies final-state hashes, ordered Run signatures and
graph effect counts for every execution. Programs are the frozen
`out/cell-fixed-reads/{sum,ray}-program.json` inputs from worktree `7c16`.

| Configuration | sum-bits inference | Raytrace inference | Raytrace process | Process-average cores |
|---|---:|---:|---:|---:|
| Incoming branch `17d8dbe6`, serial | 14.869 ms | 5.671 s | 8.635 s | 0.94 |
| Current, serial | 14.659 ms | 5.507 s | 8.523 s | 0.93 |
| Merge `10588f41`, 4 workers | 17.960 ms | 5.448 s | 8.336 s | 1.10 |
| Current, 1 worker path | 16.801 ms | 6.383 s | 8.979 s | 0.93 |
| Current, 4 workers | 18.069 ms | 5.240 s | 7.907 s | 1.10 |
| Current, 8 workers | 23.598 ms | 5.734 s | 8.424 s | 1.25 |

These are medians. Four workers reduce Raytrace inference by 4.8% against
current serial (ratio of medians); the paired median ratio is 0.972 with a
small-sample bootstrap 95% interval [0.811, 0.998]. Eight workers are 9.4%
slower than four, and sum-bits with four workers is 23.3% slower than serial.
Four workers are 3.8% faster than the merge before per-Run column preparation,
and 7.6% faster than the incoming branch's serial path. The last comparison
combines all branch changes; it is not an isolated parallelism ablation.
The same incoming serial binary is the checkpoint used here; historical
campaigns under different conditions are not substituted into these ratios.

The one-worker lane executes the residual/publication path inline; it still
pays its transport and completion costs. Serial does not enable those paths.
Average cores are process `(user + system) / wall`, including loading/reporting
and export. They are not inference-only utilization. Warmups, system drift and
the broad intervals remain visible. This establishes a modest local Raytrace
gain, not full utilization, a 2x gain, or an application-independent speedup.

## Separate stack sample

A five-second, 2 ms sample of current four-worker Raytrace starts at inference.
Progress logging is enabled only for this diagnostic; its stderr writes appear
in stacks and must not be mistaken for a production bottleneck. There are
1,689 samples per thread. Worker condition waits occupy 1,536 / 1,542 / 1,559 /
1,568 samples (90.9–92.8%). Inclusive coordinator frames include:

| Frame | Samples |
|---|---:|
| Match queries | 466 |
| Publish finished tables | 328 |
| Entry scheduler batches | 287 |
| RHS frame execution | 234 |
| Repair | 164 |
| Finish worker queries | 126 |
| Subscribe reverse edges | 121 |

Inclusive frames overlap and cannot be added. The sample covers only a window
and measures stack residence, not CPU percentages. Existing complete execution
work also shows 1,879,948 subscription calls visiting 6,000,001 values. The next
implementation therefore reuses the Cell's checked Eq footprint and canonical
Row fields to remove redundant scalar inspection/root lookup in that serial
path. It does not remove needed reverse edges or claim union is parallel.

All 1,428 sum-bits and 16,883 Raytrace Run signatures match across lanes. The
saved reviewed sum-bits native contract is `pass`; Raytrace agreement is relative
regression evidence, not a new independent native proof.

## Reproduce

The scripts below are reused unchanged. `checkpoint_serial` denotes the frozen
incoming `17d8dbe6` code (`48782309` executable), and `before4` denotes `10588f41`.
All lanes enable repair ports, Entry publication and Cell absorption. Worker
lanes additionally enable residual/publication execution with grain 64.

```sh
python3 benchmarks/parallel-cell-publication/measure.py CURRENT MERGE INCOMING SUM_PROGRAM RAY_PROGRAM ROOT/timing
python3 benchmarks/parallel-cell-publication/profile.py CURRENT RAY_PROGRAM SAVED_CURRENT_RAY ROOT/profile
python3 benchmarks/parallel-cell-publication/collect_timing.py ROOT RESULTS.json
```

Collector inputs `ROOT/runtime`, `ROOT/{sum,ray}/state.json` and
`ROOT/semantic-acceptance.json` are the frozen current artifacts. Raw reports,
stacks and complete samples remain under ignored `out/cell-parallel-current`.
Results preserve executable/program/report hashes, every timing sample, work
counts, execution order and sampled frame totals. Builds and timing were run
sequentially; no own compilation overlapped the campaign.
