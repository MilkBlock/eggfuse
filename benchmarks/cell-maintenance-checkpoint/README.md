# Maintenance checkpoint: reduced counters did not establish a speedup

Candidate `d7b2b9ac`, previous checkpoint `2af82c27`, historical fastest
`8fffff65`. These are normal release executions of the **standalone Cell CPU**,
not the native egglog runtime. The historical baseline is unchanged.

The five implementations since the preceding checkpoint removed unused narrow
projection Bloom maintenance, added optional reverse Entry selection, grouped
summary updates by field influence, specialized complete publication, and moved
fingerprint arrays/reused publication buffers. Their individual work reductions
do not establish a cumulative latency improvement.

## Normal-binary comparison

Each lane has one warmup, then seven sum-bits and five full Raytrace samples,
interleaved in reproducibly shuffled order. All observations, including outliers,
are retained in [timing.json](timing.json). No allocation instrumentation or
profiler is enabled. Binaries are frozen before timing. Compilation was complete
before the campaign; shared-machine interference cannot be excluded.

`current` has reverse selection compiled but disabled. `reverse` enables it in
the same binary. `current4` uses four query workers, grain 64, reverse disabled.
All nonhistorical lanes enable the previously implemented absorption.

| Median | Historical fast | Previous checkpoint | Current | Reverse | Current, 4 workers |
|---|---:|---:|---:|---:|---:|
| sum-bits inference, ms | 17.024 | 14.801 | 14.771 | 14.954 | 15.059 |
| sum-bits process, ms | 117.020 | 118.853 | 122.205 | 120.312 | 118.748 |
| Raytrace inference, s | 6.291 | 5.429 | 5.774 | 5.672 | 5.701 |
| Raytrace process, s | 10.689 | 9.759 | 10.559 | 10.382 | 10.636 |

Paired median ratios with paired-bootstrap 95% intervals; lower is faster:

| Comparison | sum-bits inference | Raytrace inference | Raytrace process |
|---|---:|---:|---:|
| Current / previous checkpoint | 1.004 [0.965, 1.077] | 1.030 [0.969, 1.154] | 1.021 [0.987, 1.275] |
| Reverse / current | 0.984 [0.977, 1.015] | 1.004 [0.957, 1.113] | 0.983 [0.955, 1.003] |
| Four workers / current | 1.004 [0.954, 1.032] | 0.989 [0.948, 1.032] | 1.000 [0.969, 1.073] |

The five changes do **not** establish a net inference improvement. The
Raytrace current/checkpoint interval permits both improvement and regression;
the worse median alone does not quantify a causal regression. Sum-bits process
time does regress in these samples: ratio 1.038 [1.013, 1.047]. Neither reverse
selection nor four workers establishes an independent improvement. Do not
promote this candidate to fastest or count its omission counters as speed gains.

The current/historical Raytrace inference paired ratio is 0.880 [0.843, 0.924];
the ratio of medians is 0.918. These different summaries are both retained,
and neither is close to 2x. Process time includes setup/report/export and must
not be substituted for inference or compared with an older campaign's numbers.

## What this says about sparsity and Cell completion

Current serial Raytrace phase medians are search 2.418 s, RHS 1.674 s,
query-index publication 1.151 s, repair 0.510 s, and delivery GC 0.017 s.
Independent medians do not sum to the inference median. Repair alone is about
9% of inference; eliminating that phase at unchanged other costs would yield
only about 1.10x. This is a budget bound, not proof that the phase can disappear.

Serial point queries remain **2,584,660**, equal to the previous checkpoint;
sum-bits remains 12,139. The different worker counts predate these changes and
earn no new credit. The earlier absorption still omits 509,296 Raytrace and
41 sum-bits executed bindings/pure writes; actual graph mutations stay equal.
These are existing savings, not gains from the new maintenance changes.

The [actual change-locality census](../cell-change-locality/README.md) found
small one-step Get neighborhoods in selected hot windows, together with
repeated changes to scalar attributes on otherwise stable constructors.
That sample establishes neither global sparsity nor global density. A low
one-step degree also does not bound the affected transitive closure, the number
of Runs, or the cost of locating the relevant work.

The [Entry-admission census](../cell-entry-admission/README.md) likewise found
that exact repeated whole-batch guards cover only 0.245% of all Sieve probes.
This rejects that particular cache proposal, not every cross-stage Cell reuse.
Neither observation supports assuming a 2x speedup from structural sparsity.

## Decision and next implementation gate

Keep the previous checkpoint and historical fastest binary as explicit
controls. Diagnose the cumulative maintenance cost before retaining the new
configuration as a speed improvement. The follow-up below compares the same
candidate built without the reverse-selection feature to distinguish its
dormant representation/code cost from the other four implementations; it does
not individually attribute all five changes.

Do not expand Cell templates merely to raise coverage. Start from one frequent
actual query/effect chain and identify a completed state that survives relevant
input changes. The existing min-absorption proof is one concrete, already
implemented example; repeating it under another name earns no new credit.
For a new scheduled block switch, the typed query/effect facts must prove which
point reads, RHS operations and intermediate Entry publications become
redundant. The same instance slots and existing lifecycle metadata must carry
that proof; no parallel fact graph or per-producer subscriber lists.

Charge witness acquisition, boundary validation, dispatch, retained storage,
invalidation and fallback. Preserve actual returned witnesses, residual and
late-input matches, union-enabled matches, delta ownership, retirement,
visibility and original Run/effect ordering. Reject the proposed takeover if
its proof acquisition still repeats the original per-row work or its total
opportunity is too small. Parallelizing necessary remaining work is a separate
opportunity; it is not evidence that the work has been eliminated.

## Targeted reverse-feature ablation

[ablation.json](ablation.json) retains a separate, single follow-up campaign:
the same frozen checkpoint/current binaries and a `plain` candidate at the same
source commit built without `cell-entry-reverse`. All runtime flags are equal,
including absorption, serial execution and reverse selection disabled. The
other build features remain `cell-absorption,view-ports,storage-metrics`.
One warmup and seven sum-bits/five Raytrace samples are retained per lane.

| Median | Previous checkpoint | Current | Plain |
|---|---:|---:|---:|
| sum-bits inference, ms | 14.987 | 14.509 | 14.874 |
| sum-bits process, ms | 120.816 | 252.408 | 125.556 |
| Raytrace inference, s | 5.437 | 5.334 | 5.419 |
| Raytrace process, s | 8.978 | 8.435 | 8.625 |

Raytrace plain/current paired inference ratio is **0.994 [0.963, 1.073]**;
sum-bits is **1.036 [0.975, 1.085]**. Omitting the compiled feature does not
establish an inference improvement. It does not identify dormant reverse
selection as the cause of the main campaign's worse medians.

The follow-up current/checkpoint Raytrace ratio is 0.973
[0.957288, **0.999958**], a small within-campaign improvement with an upper
bound just below parity. The direction differs from the main campaign. Retain
both rather than replacing the initial unfavorable result or averaging unmatched
medians. The follow-up sum-bits process bimodality is also retained: its
current/checkpoint paired ratio is 2.088 [1.036, 2.116]. These process samples
do not isolate inference, dormant metadata or operating-system interference.
The two campaigns do not establish a stable incremental improvement or a
specific causal regression. No additional retiming to seek a favorable result
is part of this checkpoint.

All ablation states, logical Runs, actual graph effects and absorption accounting
pass the same checks. To reproduce the follow-up, append the separately frozen
plain binary to the `measure.py` command and use a new output directory.

## Acceptance and reproduction

Every sample matches its accepted control's exact final state and logical Run
signature; executed Run signatures repeat within each lane. Actual constructor
requests, function updates, unions and created facts remain equal. Nonhistorical
executed-binding reductions reconcile exactly with absorption. The unchanged
sum-bits native choice validator returns `pass` / exit 0 on the normal candidate
export. Raytrace checks are relative regression evidence, not an independent
native equivalence proof. No new intermediate-window capture is claimed.

Inputs and accepted controls are frozen under `out/cell-current-checkpoint`.
The checkpoint binary is `out/cell-absorption-checkpoint/runtime`; the new
ordinary binary is `out/cell-maintenance-checkpoint/runtime`. Binary, program,
proof and raw-sample hashes are retained in the result. Build the candidate with:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,cell-entry-reverse,view-ports,storage-metrics
```

Copy the executable to a separate frozen path before any further build. Prepare
the native semantic input directory as documented by the choice-diagnosis
contract, then use new output directories:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-maintenance-checkpoint/measure.py INPUT_ROOT ROOT/timing CURRENT CHECKPOINT HISTORICAL_FAST d7b2b9ac
python3 benchmarks/cell-maintenance-checkpoint/collect.py ROOT/timing RESULTS.json
```

The collector uses saved exports and does not run workloads. Assertions are
required; do not use Python `-O`. Build products, raw reports and state exports
remain ignored under `out/`.
