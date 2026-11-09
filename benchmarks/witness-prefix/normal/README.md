# Witness, prefix and fragment pilot

The two-workload inference/process gate did not pass. Sum-bits inference did
not improve consistently; Raytrace improved slightly in all three pairs. Both
remain slower than the archived fastest configuration. This measures the
standalone Cell CPU, not the native egglog runtime.

| Workload | Baseline inference / process | Candidate inference / process | Archived fast inference / process |
|---|---:|---:|---:|
| sum-bits, ms | 30.772 / 197.790 | 31.459 / 187.763 | 21.437 / 147.146 |
| Raytrace, s | 12.557 / 15.920 | 12.335 / 15.649 | 8.130 / 10.469 |

These are medians. Candidate inference was faster in 1/3 sum-bits pairs and
3/3 Raytrace pairs; process time was faster in 3/3 pairs for both workloads.
Descriptive paired-bootstrap 95% ratio intervals (candidate / baseline) are
0.9664–1.0334 for sum inference, 0.9392–0.9955 for sum process,
0.9818–0.9984 for Ray inference and 0.9811–0.9972 for Ray process. Three pairs
do not establish a robust general performance improvement. No samples were
removed. The candidate's first sum warmup took 613.449 ms and remains in the
raw file, excluded from medians under the same planned warmup policy as every
other lane.

The prefix and local-witness mechanisms saved **zero queries** on both samples.
Sum had six prefix donor attempts and 25 Spine donor attempts; Ray had 239 and
1,380 respectively. All were stale and fell back. Register-prefix resumes were
zero; key lookup calls remained exactly 19,222 (sum) and 4,330,682 (Ray).
The positive correctness fixtures establish the implementation's behavior, but
these workloads do not demonstrate its useful coverage.

Fragment publication did execute: 3,421 sum receipts in 1,447 packets and
593,054 Ray receipts in 237,782 packets. The new path also performed temporary
Pending writes/reads: 5,505/4,533 for sum and 1,028,028/780,458 for Ray.
Packetless Entry notification reuse suppressed 271 and 98,528 duplicate
enqueues. The old binary lacks these newly introduced counters, so missing
baseline fields are not treated as zero cost. This combined campaign does not
isolate fragment publication's elapsed-time contribution.

The mean sum process reduction was 7.656 ms: loading contributed −4.467 ms,
export −0.687 ms and the after-report residual −2.885 ms, while inference
increased 0.316 ms. Ray's mean process reduction was 154.700 ms, including
−117.850 ms inference, −25.535 ms loading and −20.037 ms export. These are
paired **mean** differences, which add to mean wall differences; they need not
equal the differences between the median columns above. Every phase and
residual sample is retained in [phase-attribution.json](phase-attribution.json).

Raw state and complete ordered Run schedule hashes agree across all lanes,
warmups and measured samples. Per-lane counters are deterministic across all
four executions. The source manifest was unchanged during timing. Normal
builds do not collect allocation counts; separate diagnostic audit results
must not be interpreted as timings from this campaign.

See [validation.json](validation.json), [metadata.json](metadata.json),
[sum-bits.json](sum-bits.json), [raytrace.json](raytrace.json), and the complete
[sum](sum-bits-samples.json) / [Ray](raytrace-samples.json) sample files.

Each workload uses one warmup and three paired repetitions. Every repetition
contains the prior query-class runtime, the new candidate and the archived
fastest runtime, executed serially in a fixed-seed shuffled order. Baseline and
candidate use the exact same classified artifact. The older fast runtime uses
its compatible original artifact and remains a visible performance reference.

The runtime was frozen at `f5bc98ca`; candidate SHA256 is
`31b135fc7da867f42df931d9e55ab5aa80d2ba48bc3382ead26bfcc4671993cd`.
The root agent released the CPU before timing and ran no concurrent build or
workload. Reproduce from the worktree root with the frozen files in metadata:

```sh
python3 benchmarks/witness-prefix/prepare.py benchmarks/witness-prefix/normal --candidate-sha256 31b135fc7da867f42df931d9e55ab5aa80d2ba48bc3382ead26bfcc4671993cd
python3 benchmarks/witness-prefix/measure.py benchmarks/witness-prefix/normal/sum-bits-manifest.json out/witness-prefix/normal/sum-bits --repeat 3 --warmups 1
python3 benchmarks/witness-prefix/measure.py benchmarks/witness-prefix/normal/raytrace-manifest.json out/witness-prefix/normal/raytrace --repeat 3 --warmups 1
python3 benchmarks/witness-prefix/collect.py out/witness-prefix/normal benchmarks/witness-prefix/normal
python3 benchmarks/witness-prefix/validate.py benchmarks/witness-prefix/normal
```

The wrapper reuses the existing blocking-wait process harness without changing
its timing, raw state hash, ordered schedule checks or historical files. It
captures extra report fields after child termination and before report cleanup.
Every measured and warmup sample is retained, including per-Run phase sums,
report time and available whole-process residuals. Missing old report phases
are never replaced by zero. Normal allocation metrics remain explicitly
missing; an allocator build must be measured and audited separately.

The report checks deterministic counters across all samples, including warmup,
and records whether each group actually existed in each binary. New counters
measure producer dispatch, current donor validation, prefix continuation and
fragment/Entry publication. A decrease in any one counter is insufficient to
establish a speedup. Three pairs form a bounded pilot; confidence intervals are
descriptive and no outliers are removed.
