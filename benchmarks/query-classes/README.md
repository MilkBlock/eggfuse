# Cross-stage operator classes: first single-thread pilot

This measures the **standalone Cell CPU**, not native egglog. The first complete
class implementation improves Raytrace relative to the shared-code experiment,
but **does not pass the two-workload inference/process performance gate**.
sum-bits whole-process time has no demonstrated improvement, and the archived
fast path is still substantially faster on both workloads.

## Compared lanes

All normal executables use release `sparse-cells,view-ports,storage-metrics`,
without allocator or ordered-audit instrumentation. The new runtime was built
**alone**, without adding the compiler package to the Cargo build invocation.

| Lane | Executable | Artifact | Runtime flags |
| --- | --- | --- | --- |
| `baseline` | Frozen `runtime-code`, checkpoint `86800d89` source | Original baked input | `--local-congruence` |
| `receipts` | `runtime-query-classes-isolated` | Same original input | `--local-congruence` |
| `classes` | Same new executable | Same input with checked query-class certificate | `--local-congruence` |
| `fast_archived` | Archived fast runtime, source `8fffff65` | Original baked input | `--repair-ports --entry-publications` |

`receipts` includes receipt-demand pruning, class infrastructure/origin tracking,
and the new report timer. It is **not** an isolated estimate of receipt pruning.
`classes` versus `receipts` isolates certificate-enabled class filtering in the
same executable. The certificate does not change the source workload, selected
fragments or schedule. Full paths and SHA-256 values are in the manifests and
`metadata.json`; the isolated candidate SHA-256 is
`3a08768d1f22ec248d2f905c93fa24728f3a0732fe9798636660f0afb174624e`.

The machine is an Apple M3 Max with 16 logical CPUs and 48 GiB memory. Each child
is single threaded for this workload; no guard workers were requested. Processes
run sequentially in a shuffled interleaved order with blocking `waitpid` wall
timing. sum-bits has one warmup per lane and 15 measured repetitions; Raytrace
has two measured repetitions per lane and no additional warmup. The parent
agent held production source fixed and avoided CPU/Cargo work during timing.

## Actual timing

Values are medians. The Raytrace sample is a bounded pilot; its two paired
observations are insufficient for a precise general speedup estimate.

| Workload | Lane | Inference | Whole process |
| --- | --- | ---: | ---: |
| sum-bits | baseline | 31.758 ms | 195.602 ms |
| sum-bits | receipts | 31.472 ms | 196.668 ms |
| sum-bits | classes | 31.200 ms | 197.124 ms |
| sum-bits | fast_archived | 21.544 ms | 145.856 ms |
| Raytrace | baseline | 13.328 s | 23.084 s |
| Raytrace | receipts | 13.687 s | 23.265 s |
| Raytrace | classes | 12.448 s | 22.311 s |
| Raytrace | fast_archived | 8.061 s | 10.362 s |

Relative to baseline, classes reduces Raytrace median inference by 6.61% and
process time by 3.35%; both pairs improve. Against receipts in the same binary,
the reductions are 9.06% and 4.10%. The receipts lane itself is slower than
baseline in both Raytrace pairs (median increases 2.69% and 0.79%). These results
do not support a standalone receipt-pruning speedup claim.

For sum-bits, classes improves inference: the descriptive paired-bootstrap
95% ratio interval is `[0.9576, 0.9927]` against baseline. The process interval
is `[0.9972, 1.0161]`, crossing one, with a worse median. The receipts lane
comparisons are inconclusive on sum-bits. Raw points, distributions, pairing,
and intervals are in `sum-bits.json` and `raytrace.json`; the `*-vs-receipts.json`
files give the same-binary class ablation. No further repetitions were added to
seek a favorable result.

## Report construction explains most of the Raytrace residual

`process_unattributed_seconds` is wall minus load, setup, inference and export.
For the new binary, `report_seconds` measures report construction and report
additions before export. A second residual additionally subtracts this measured
report interval. Old binaries have no report measurement; it is never set to
zero or silently deducted. Phase medians need not sum to median wall.

| Workload / lane | Unattributed before deducting report | Measured report | Remaining residual |
| --- | ---: | ---: | ---: |
| sum-bits baseline | 40.233 ms | Unmeasured | Unavailable |
| sum-bits receipts | 40.177 ms | 9.935 ms | 30.211 ms |
| sum-bits classes | 41.508 ms | 10.521 ms | 31.061 ms |
| Raytrace baseline | 7.466 s | Unmeasured | Unavailable |
| Raytrace receipts | 7.303 s | 7.024 s | 0.279 s |
| Raytrace classes | 7.496 s | 7.191 s | 0.305 s |

The remaining residual includes serialization, output, teardown and other
unmeasured intervals; it is not a direct measurement of any one of them. The
archived fast executable does not report load time, so this decomposition is
unavailable there. Report construction contains ownership validation, including
boundary membership scans. The new timer localizes the large interval to report
construction; it does not by itself attribute every second to a particular
assertion. No validation was removed during this campaign.

## Work removed and work added

These are actual executed counters, identical across every measured and warmup
sample within each lane. Baseline and receipts have the same domain work.

| Work | sum-bits receipts | sum-bits classes | Raytrace receipts | Raytrace classes |
| --- | ---: | ---: | ---: | ---: |
| Signal visits | 58,494 | 12,048 | 55,413,157 | 14,543,598 |
| Slice visits / type guards | 59,462 | 19,268 | 63,490,061 | 14,378,473 |
| Type rejections | 49,625 | 9,431 | 53,395,879 | 4,284,291 |
| Class probes | 0 | 48,367 | 0 | 16,067,446 |
| Tree range jumps | 0 | 34,109 | 0 | 11,076,813 |
| Domain results | 5,693 | 5,693 | 6,235,405 | 6,235,405 |
| Exact key candidates | 17,491 | 17,491 | 8,475,767 | 8,475,767 |
| Port domain queries | 6,165 | 6,165 | 1,962,583 | 1,962,583 |

Class filtering avoids much instance/slice inspection, while leaving the exact
candidate/Eq proof work unchanged. The large number of tree range restarts is
real additional dispatch work. A count of rejected classes does not measure
the number of skipped members; no rejected group was scanned just to count
imagined savings. Work counters explain why fewer visits alone cannot establish
a whole-process improvement.

The compiler emits 541 classes / 3,780 mask words / 2,410 symbol slots for
sum-bits, and 583 / 4,074 / 15,666 for Raytrace. Classified artifacts grow by
26,181 and 71,198 bytes respectively. These are static inventories, not runtime
allocation savings. Allocation instrumentation and a complete binary-to-binary
RHS/write/resume/Spine audit have not been run for this pilot.

## Validation and the rejected build

All normal pilot samples match strict raw exported-state SHA-256 and ordered
Run schedule SHA-256 across all four lanes. sum-bits completes 1,428 Runs and
Raytrace completes 16,883 Runs. Source hashes did not change during timing.
`validation.json` records the parent-run checks: 343 workspace tests pass with
four preexisting ignored, 49 non-sparse tests, 12 final focused tests and the
no-default runtime check. Workspace/non-sparse precede the conservative one-line
restoration of the original receipt fallback; final focused follows it. This
source boundary is recorded explicitly.

The first warmup campaign used a joint runtime-plus-compiler Cargo build.
Dependency feature unification changed JSON object key order. The strict state
SHA check correctly stopped it, even though fully parsed states and every array
were identical. That binary and all its pilot/diagnostic timings are excluded.
`build-order-diagnosis.json` and the `build-mismatch-*-manifest.json` files retain
the evidence. The runtime was then rebuilt alone, which restored the original
raw state checksum; the complete campaign above starts fresh in `out/query-classes`.

## Reproduction

Build the normal runtime separately from the compiler and preserve frozen
executables before changing source. Original artifacts come from the preceding
ownership-fragment experiment; their exact hashes are recorded in metadata.
Create classified copies without retraining:

```sh
out/condition-bake/compiler-query-classes bake-cell-ownership --program out/stable-port-congruence/sum-program.json --query-classes true --output out/condition-bake/query-classes-sum
out/condition-bake/compiler-query-classes bake-cell-ownership --program /private/tmp/eggfuse-signal-lifetime/out/signal-lifetime/baked-raytrace/program.json --query-classes true --output out/condition-bake/query-classes-ray
python3 benchmarks/raytrace-parallel/measure.py benchmarks/query-classes/sum-bits-manifest.json out/query-classes/sum-bits --repeat 15 --warmups 1 --timeout 30
python3 benchmarks/raytrace-parallel/measure.py benchmarks/query-classes/raytrace-manifest.json out/query-classes/raytrace --repeat 2 --warmups 0 --timeout 180
python3 benchmarks/query-classes/collect.py out/query-classes benchmarks/query-classes
```

Output directories must be new. The collector performs no workload execution;
it rechecks frozen source hashes, sample semantics and deterministic counters
before producing both comparison views. Build artifacts and raw output trees
are not tracked.
