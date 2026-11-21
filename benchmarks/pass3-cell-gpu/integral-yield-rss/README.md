# Inference-window RSS and external wire avoided in integral Cell inference

This study runs the real frozen sum-bits and 3mm Pass 3 in native CPU processes. The independent CPU uses the default engine. The five neural arms use the identical frozen model, allocator and original Run schedule. Raw sends external singleton proposals. Filter drops proved negative scalar proposals. Closed internalizes a complete, certified singleton bank. Filter + closed combines both; filter + mixed also accepts an authenticated subset of a bank while the remaining lanes follow the original external issuer. The model still scores causal candidates and the verifier performs all original correctness checks in the timed executable. Source-only audits, graph export and compiler work sit outside the inference window. [Joint native execution](../integral-filter-joint/README.md)

**Resident memory.** The measurement reuses the external macOS `proc_pidinfo(PROC_PIDTASKINFO)` sampler and the default CPU binary from the [verified wave RSS study](../verified-wave-rss/README.md). It reads the target process's OS resident set at nominal 1 ms intervals. Timestamps and endpoint RSS surround `Executor::execute`. Each process runs a single request. Three separate fresh default-CPU calibrations per workload define common 50% and 90% observed growth levels and corresponding absolute levels; controls and treatments then run in four rotated rounds, each with one sampled and one unsampled fresh process. The first observed crossing is timed, or marked left-censored at entry or unreached. An equal RSS rise can reflect index pages, retained allocator memory, old payloads or new useful work.

**What the traffic counters mean.** At every completed original source Run the native executor publishes the current ordinal, cumulative actual external root wire bytes, emitted single- and multi-parent root counts and actually source-committed internal bindings to one fixed shared page. The OS sampler records its latest complete snapshot. To compute wire avoided at a threshold, we subtract the measured arm's actual wire from the raw arm's actual wire **at that same completed source Run**. Comparing the raw process at the same wall time would conflate throughput with representation. Both arms' original ordered effective writes and published result are aligned. The measured arm's next Run may already be executing at the sampling instant. Its partial traffic is excluded from this comparison. Internal commits are accepted RHS bindings; a binding may reuse an existing constructor or write nothing. The measured bytes use the original root wire counter and exclude internal proof/checking memory, selected child-packet bytes and unrelated process allocations.

Detailed audits retain the original Run-by-Run wire and receipt trajectories. The sampled process keeps only the latest values and a rolling digest. It stores no Run trace or graph snapshots in the measured address space. Every sampled checkpoint is independently checked against the matching detailed ledger. End counts on sampled and unsampled runs must also match the original joint experiment. [Complete per-Run source evidence](audit.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/integral-yield-rss
python "$d/build.py" "$EXP/integral-yield-rss-build" "$EXP/verified-wave-rss-native-v1/vanilla"
python "$d/measure.py" "$EXP" "$EXP/integral-yield-rss-build" "$EXP/integral-yield-rss-audit" --audit
python "$d/measure.py" "$EXP" "$EXP/integral-yield-rss-build" "$EXP/integral-yield-rss-curves"
python "$d/analyze.py" "$EXP/integral-yield-rss-curves" "$EXP/integral-yield-rss-audit" "$d"
python "$d/plot.py"
python "$d/verify.py"
```
