# Bounded lookahead ablation: withdrawn

This is a standalone Cell CPU experiment. It adds a four-key lookahead before
seeking past a rejected class, accumulates class counters until iterator drop,
and replaces a report-time linear membership assertion with `TinySet.contains`.
The report assertion remains present. The candidate is **not retained**:
lookahead does not demonstrate additional Raytrace inference improvement over
the simple class-range implementation. Its large whole-process improvement is
explained by the independent report correction, which will be retained.

The frozen executable is `out/condition-bake/runtime-query-classes-adaptive`,
SHA-256 `a7d1fd2eb26ba09ee50ff1f99121032259ce16e36f13ea7be5747422838f74cb`.
It was built alone with release `sparse-cells,view-ports,storage-metrics`.
This campaign has no allocation or ordered-audit instrumentation.

## Same-round comparison

`baseline` is checkpoint `86800d89` shared-code with the original artifact.
`ranges` is the first isolated class executable with the classified artifact.
`adaptive` uses that same classified artifact. These lanes use
`--local-congruence`. `fast_archived` uses the original artifact and
`--repair-ports --entry-publications`. Exact paths and hashes are in manifests
and metadata. Trials run sequentially in shuffled interleaved order, with 15
sum-bits measurements after one warmup per lane and two Raytrace measurements
without another warmup.

| Workload | Lane | Inference median | Process median |
| --- | --- | ---: | ---: |
| sum-bits | baseline | 31.799 ms | 197.224 ms |
| sum-bits | ranges | 30.805 ms | 196.093 ms |
| sum-bits | adaptive | 30.336 ms | 197.501 ms |
| sum-bits | fast_archived | 21.374 ms | 144.614 ms |
| Raytrace | baseline | 13.472 s | 23.096 s |
| Raytrace | ranges | 11.536 s | 21.423 s |
| Raytrace | adaptive | 11.548 s | 14.868 s |
| Raytrace | fast_archived | 7.771 s | 10.031 s |

For Raytrace, adaptive versus ranges has one slower and one faster inference
sample; the descriptive paired ratio interval is `[0.99595, 1.00589]`.
There is no demonstrated inference gain. Median process time falls 30.60%,
while measured report construction falls from 7.280 to 0.694 seconds.
Most of this wall improvement belongs to the report change, not RHS execution
or bounded lookahead. Against shared-code baseline, the combined candidate is
14.29% faster in median inference and 35.63% in median process time; the class
feature from the preceding experiment accounts for the inference improvement.

sum-bits inference improves against baseline and ranges, but whole-process
improvement remains unproven: the paired ratio intervals are respectively
`[0.9770, 1.0238]` and `[0.9505, 1.0511]`. Timing variation includes a 297 ms
ranges process and a 229 ms baseline process; every observation is retained.
The two-workload inference/process gate remains failed, and fast_archived
remains faster. No thresholds were fitted to these two inputs.

## Phase attribution

Phase medians are reported individually; they need not sum to median process
time. `phase-attribution.json` also preserves every sample's phases and residuals
and gives an exactly additive decomposition using paired **mean** differences.

| Workload / lane | Load | Setup | Export | Report | Residual after measured report |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum baseline | 114.048 ms | 3.443 ms | 6.656 ms | Unmeasured | Unavailable |
| sum ranges | 115.198 ms | 3.200 ms | 6.746 ms | 10.513 ms | 29.468 ms |
| sum adaptive | 114.918 ms | 3.031 ms | 6.625 ms | 10.738 ms | 29.499 ms |
| Raytrace baseline | 0.539 s | 0.005 s | 1.709 s | Unmeasured | Unavailable |
| Raytrace ranges | 0.563 s | 0.005 s | 1.748 s | 7.280 s | 0.291 s |
| Raytrace adaptive | 0.547 s | 0.005 s | 1.759 s | 0.694 s | 0.315 s |

The sum-bits adaptive-minus-baseline paired means are: inference −2.754 ms,
setup −0.343 ms, load +1.342 ms, export −0.030 ms, and the not-yet-separated
report/output/teardown residual +0.666 ms. Their sum is process −1.119 ms,
despite the slightly worse process median. This dispersion does not justify a
whole-process speedup claim or a single causal explanation based on medians.

For Raytrace adaptive minus ranges, the paired means are report −6.586 s,
inference +0.012 s, load −0.016 s, export +0.011 s, setup +0.001 s, remaining
residual +0.023 s: process −6.556 s. The remaining residual is a difference of
measured intervals, not an isolated measurement of serialization or teardown.
Missing old report/load fields are never supplied as zero.

## Actual additional work

| Work | sum ranges | sum adaptive | Raytrace ranges | Raytrace adaptive |
| --- | ---: | ---: | ---: | ---: |
| Class probes | 48,367 | 48,367 | 16,067,446 | 16,067,446 |
| Tree range jumps | 34,109 | 1,341 | 11,076,813 | 851,775 |
| Boundary Signal keys read | Not measured | 68,051 | Not measured | 33,602,603 |
| Domain signal visits | 12,048 | 12,048 | 14,543,598 | 14,543,598 |
| Domain slice visits | 19,268 | 19,268 | 14,378,473 | 14,378,473 |

Key reads count actual keys yielded from the boundary iterator, including the
bounded rejected prefix and a retained first key of the next class. Native
signals contribute class probes but are outside this boundary-key counter.
Neither discarded groups nor their members are enumerated to manufacture a
savings count. Fewer seeks are real, but they are exchanged for prefix reads;
the inference measurements do not establish a Raytrace benefit.

## Validation and status

All four lanes have identical strict exported-state and ordered schedule
hashes on both workloads, and deterministic counters match across every normal
sample within a lane. Production source hashes stayed fixed during timing.
The parent ran 344 workspace tests successfully with four preexisting ignored;
log hash and command are in `validation.json`.

No allocator or full ordered RHS/write/resume/Spine audit was run for this
withdrawn candidate. The prepared audit manifests were not executed. Retain
this report and source archive as an ablation; do not promote fewer range jumps
into an additional speedup claim. The final candidate will retain simple class
ranges and report membership lookup, and receive separate measurement/audit.

To recollect this frozen evidence without timing:

```sh
python3 benchmarks/query-classes/collect.py out/query-classes-adaptive benchmarks/query-classes/adaptive --ablation ranges
```

The collector requires the recorded frozen source manifest. When current source
has advanced, use the corresponding archived candidate source in an isolated
checkout. Build/output trees remain untracked.
