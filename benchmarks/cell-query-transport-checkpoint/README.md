# Query transport checkpoint: a small cumulative gain, not 2x

Candidate `48782309`, preceding timed implementation `d7b2b9ac`, historical
fastest `8fffff65`. Scope: **standalone Cell CPU**, not native egglog.

The five implementations add parameterized LazyUnion completion, seal repaired
result receipts, absorb individual completed members of mixed candidate domains,
carry singleton candidate domains inline, and project point-read results before
query handoffs. The same frozen v4 programs run in every lane; v5 LazyUnion
admission remains opt-in. Receipt sealing also benefits existing v4 completion.
This comparison does not separately attribute speed changes to each feature.

## Complete workload timing

Each lane has one warmup, then seven sum-bits and five full Raytrace samples,
interleaved with a fixed shuffled order. All 56 completed processes and all
outliers are retained in [timing.json](timing.json). No profiler or allocation
instrumentation is enabled. No build or other diagnostic from this task ran
during timing; a process check at campaign start found no Cargo/rustc activity.
Other shared-machine interference is not controlled.

The previous checkpoint uses its frozen no-reverse-feature binary. The current
build uses `cell-absorption,view-ports,storage-metrics`, also without the reverse
feature. All nonhistorical lanes enable absorption. All lanes enable repair
ports and Entry publication. Four workers use grain 64, from the same current
binary. These are end-to-end configurations, not a pure scaling experiment.

| Median | Historical fastest | Previous checkpoint | Current serial | Current, 4 workers |
|---|---:|---:|---:|---:|
| sum-bits inference, ms | 17.453 | 14.293 | 14.171 | 14.411 |
| sum-bits process, ms | 118.247 | 113.991 | 113.623 | 118.279 |
| Raytrace inference, s | 5.999 | 5.114 | 4.973 | 5.014 |
| Raytrace process, s | 8.141 | 7.262 | 7.168 | 7.124 |

Paired median time ratios with paired-bootstrap 95% intervals; lower is faster:

| Comparison | sum-bits inference | Raytrace inference | Raytrace process |
|---|---:|---:|---:|
| Current / previous checkpoint | 0.987 [0.966, 0.998] | 0.974 [0.960, 0.979] | 0.975 [0.956, 0.996] |
| Current / historical fastest | 0.809 [0.799, 0.827] | 0.824 [0.821, 0.846] | 0.869 [0.864, 0.897] |
| Four workers / current serial | 1.022 [1.015, 1.082] | 1.005 [1.000365, 1.026] | 1.001 [0.986, 1.009] |

This campaign supports a small cumulative inference gain. Raytrace median time
falls about 2.8% versus the preceding checkpoint; sum-bits falls about 0.9%.
Relative to the historical fastest, ratios of medians imply approximately
**1.21x Raytrace and 1.23x sum-bits inference throughput**, not 2x. Process-time
ratios remain separate. Four workers do not improve inference here; retain the
serial path as the current supported configuration. Five observations and these
bootstrap intervals do not establish performance across different machines.

## Actual work and remaining budget

All logical source Runs and committed graph effects match their references.
Executed bindings and pure writes decrease through the already checked
absorption capability. Full Raytrace reveals coverage absent from the short
1,280-Run prefix: mixed members omit another **194,730** executions, bringing
total absorption to 704,026 versus the previous 509,296. Sum-bits gains 31.
These are executions, not committed mutations or new independent credits.
The mixed-member path also performs 445,455 eligibility attempts and 445,332
output probes. Unsuccessful proofs retain ordinary execution and can repeat its
output lookup. Those costs remain charged; the omission count alone does not
explain the timing gain.

| Current serial work | sum-bits, before / after | Raytrace, before / after |
|---|---:|---:|
| Graph key lookups | 12,139 / 12,115 | 2,584,660 / 2,583,557 |
| Executed bindings | 7,224 / 7,193 | 2,938,195 / 2,743,465 |
| Pure single writes | 1,080 / 1,049 | 1,763,886 / 1,569,156 |
| Constructor requests | 8,033 / 8,014 | 1,619,819 / 1,618,848 |
| Union requests | 2,439 / 2,434 | 508,341 / 508,209 |
| Combined Entry/general materialized refs | 4,203 / 2,658 | 3,167,308 / 2,811,940 |

The domain materialization decrease is 355,368 full-Raytrace references, after
charging 15,537 references shifted to independent general probes. It is not
an allocation count. Inline domains also introduce shape checks and widen
candidate/Subtrie headers; those costs are included in normal execution.
Complete Raytrace performs 2,643,879 new projection-shape checks and delivers
1,886,203 inline domains. These are not additional independent savings.
The final point projection covers 21,899 positive function reads on complete
Raytrace. Cache transfers also use the narrower result, but this counter does
not measure all cache hits or allocations. Work and storage details remain in
the individual experiment documents; the timing change cannot be credited to
that final implementation alone.

Current Raytrace phase medians are search 2.076 s, RHS 1.403 s, query-index
publication 1.022 s, repair 0.450 s and delivery GC 0.014 s. Independent medians
do not sum exactly. Repair remains about 9% of inference. Eliminating only that
phase with all other costs fixed would produce about 1.10x, insufficient for
the goal. Keep targeting substantial query/effect/publication work, with typed
Cell proofs and actual surviving coverage, rather than expanding the template
count or adding workers alone.

## Protocol correction and semantic acceptance

The first warmup stopped because the copied harness classified
`constructor_requests` as a committed effect. Earlier result sealing legitimately
removes repeated constructor requests; that is part of this batch's intended
work reduction. The stopped sample had already passed exact state and logical
Run checks. Its 1,450 function updates, 1,039 committed unions and 3,739 created
facts also matched. [protocol-check.json](protocol-check.json) retains the
original harness hash, complete warmup and reason. No timing comparison is
inferred from that incomplete attempt.

The corrected protocol requires those committed-effect counters exactly and
records constructor/union requests separately as execution work. It also
requires per-lane executed Run signatures and complete statistics to repeat,
and reconciles binding/write reductions with absorption. The complete campaign
then ran in a fresh directory with the same predeclared repetitions and lanes.
The semantic validator, exclusions and equational rules were not changed.

Every completed timing sample matches its accepted control's exact final state
and logical Run signature. The candidate's normal sum-bits export passes the
unchanged `choice_diagnosis.py` contract with `pass` / exit 0 and has the exact
hash observed during timing. Full Raytrace is relative regression evidence,
not independent native acceptance. Individual implementation tests cover the
affected Run boundaries; final-state acceptance does not replace those tests.

## Reproduction

Frozen compatible inputs and accepted controls remain under
`out/cell-current-checkpoint`. Current binaries, a copy of the historical fast
binary, the previous checkpoint's `runtime-plain`, native acceptance and raw
samples are under ignored `out/cell-query-transport-checkpoint`. The successful
campaign directory is `timing-checked`; the stopped first warmup remains in
`timing`. The summary binds binary, program, proof and raw-sample hashes.

Build and freeze the current ordinary runtime before any later build:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,storage-metrics
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_ROOT ROOT/semantic-acceptance.json
python3 benchmarks/cell-query-transport-checkpoint/measure.py INPUT_ROOT ROOT/timing CURRENT PREVIOUS_CHECKPOINT HISTORICAL_FAST 48782309
python3 benchmarks/cell-query-transport-checkpoint/collect.py ROOT/timing RESULTS.json
```

Use new output directories and Python without `-O`. The collector reads saved
samples and does not run workloads. Build products and raw binary/state exports
are not tracked. README bench repeat 1 remains a separate command smoke check.
