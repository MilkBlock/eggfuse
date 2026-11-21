# Inference-window RSS and external wire avoided in integral Cell inference

> **Metric clarification.** The measured RSS curves and wire suppression concern external transport and native memory. An internal activation or an earlier memory crossing does not supply a model-emitted explicit parent tuple. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

This study runs the real frozen sum-bits and 3mm Pass 3 in native CPU processes. The independent CPU uses the default engine. The five neural arms use the identical frozen model, allocator and original Run schedule. Raw sends external singleton proposals. Filter drops proved negative scalar proposals. Closed internalizes a complete, certified singleton bank. Filter + closed combines both; filter + mixed also accepts an authenticated subset of a bank while the remaining lanes follow the original external issuer. The model still scores causal candidates and the verifier performs all original correctness checks in the timed executable. Source-only audits, graph export and compiler work sit outside the inference window. [Joint native execution](../integral-filter-joint/README.md)

**Resident memory.** The measurement reuses the external macOS `proc_pidinfo(PROC_PIDTASKINFO)` sampler and the default CPU binary from the [verified wave RSS study](../verified-wave-rss/README.md). It reads the target process's OS resident set at nominal 1 ms intervals. Timestamps and endpoint RSS surround `Executor::execute`. Each process runs a single request. Three separate fresh default-CPU calibrations per workload define common 50% and 90% observed growth levels and corresponding absolute levels; controls and treatments then run in four rotated rounds, each with one sampled and one unsampled fresh process. The first observed crossing is timed, or marked left-censored at entry or unreached. An equal RSS rise can reflect index pages, retained allocator memory, old payloads or new useful work.

**What the traffic counters mean.** At every completed original source Run the native executor publishes the current ordinal, cumulative actual external root wire bytes, emitted single- and multi-parent root counts and actually source-committed internal bindings to one fixed shared page. The OS sampler records its latest complete snapshot. To compute wire avoided at a threshold, we subtract the measured arm's actual wire from the raw arm's actual wire **at that same completed source Run**. Comparing the raw process at the same wall time would conflate throughput with representation. Both arms' original ordered effective writes and published result are aligned. The measured arm's next Run may already be executing at the sampling instant. Its partial traffic is excluded from this comparison. Internal commits are accepted RHS bindings; a binding may reuse an existing constructor or write nothing. The measured bytes use the original root wire counter and exclude internal proof/checking memory, selected child-packet bytes and unrelated process allocations.

Detailed audits retain the original Run-by-Run wire and receipt trajectories. The sampled process keeps only the latest values and a rolling digest. It stores no Run trace or graph snapshots in the measured address space. Every sampled checkpoint is independently checked against the matching detailed ledger. End counts on sampled and unsampled runs must also match the original joint experiment. [Complete per-Run source evidence](audit.json)

## Reproduce

## Same-growth crossings

The reference CPU calibrates the 90% rise at **9.27 MiB** for sum-bits and **264.08 MiB** for 3mm. The table uses four fresh-process observations. Wire avoided compares the raw external stream at the same completed source Run. Fractional counts arise from taking the median across an even number of trials.

| Workload | Arm | Peak RSS (MiB) | Time to 90% rise (ms) | Wire B avoided at crossing | Committed internal bindings at crossing |
|---|---|---:|---:|---:|---:|
| sum-bits | cpu | 261.32 | 18.6 | — | — |
| sum-bits | raw_external | 270.86 | 24.5 | 0.0 | 0.0 |
| sum-bits | filter_external | 270.81 | 23.3 | 29,336.0 | 0.0 |
| sum-bits | raw_closed | 270.81 | 23.7 | 19,352.0 | 529.0 |
| sum-bits | filter_closed | 270.84 | 23.3 | 49,152.0 | 530.0 |
| sum-bits | filter_mixed | 270.91 | 23.0 | 52,968.0 | 777.0 |
| 3mm | cpu | 693.38 | 583.1 | — | — |
| 3mm | raw_external | 731.88 | 1,070.7 | 0.0 | 0.0 |
| 3mm | filter_external | 744.90 | 1,027.1 | 1,764,708.0 | 0.0 |
| 3mm | raw_closed | 742.65 | 1,046.8 | 148,896.0 | 5,764.0 |
| 3mm | filter_closed | 749.03 | 1,038.9 | 1,911,312.0 | 5,648.5 |
| 3mm | filter_mixed | 765.11 | 1,020.2 | 2,073,848.0 | 14,208.0 |

On 3mm, filtered mixed reaches the common growth level 50.48 ms before raw external and has avoided about 2.07 MB of external root wire at that observed point. It also reaches a higher peak RSS (765.11 versus 731.88 MiB). Earlier growth can coexist with more retained proof/index storage. The counters establish the actual ordered activations and savings already present at the crossing. [sum-bits curves](sum-bits.svg) · [3mm curves](3mm.svg) · [Individual measurements](results.json)

```sh
d=benchmarks/pass3-cell-gpu/integral-yield-rss
python "$d/build.py" "$EXP/integral-yield-rss-build" "$EXP/verified-wave-rss-native-v1/vanilla"
python "$d/measure.py" "$EXP" "$EXP/integral-yield-rss-build" "$EXP/integral-yield-rss-audit" --audit
python "$d/measure.py" "$EXP" "$EXP/integral-yield-rss-build" "$EXP/integral-yield-rss-curves"
python "$d/analyze.py" "$EXP/integral-yield-rss-curves" "$EXP/integral-yield-rss-audit" "$d"
python "$d/plot.py"
python "$d/verify.py"
```
