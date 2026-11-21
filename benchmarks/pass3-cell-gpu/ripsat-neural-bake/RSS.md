# Fresh-process resident memory of the four neural Bake paths

The leaf, trace, native RipSat and union arms use one native Cell CPU binary with the same frozen neural parent scorer. Only their admitted static composite programs differ. The RipSat artifacts are verified and relinked before invoking the target. All measured and unsampled control processes must reproduce the corresponding independent source study's exact final state, original Run count, emitted single/multi-parent packet counts and internal commits. The production checker must report zero audit-only score evaluations.

Each workload uses the previously frozen [independent default CPU calibration](../verified-wave-rss/README.md). The primary comparison is time to a **common absolute amount of resident growth** above each process's inference entry: 9,490 KiB (+9.27 MiB) for sum-bits and 270,446 KiB (+264.11 MiB) for 3mm. These amounts are 90% of the respective calibration peak growth, and do not depend on any tested arm's own peak. We also retain crossings of the absolute calibrated RSS levels, 266,530 and 679,982 KiB. A process already above an absolute level at entry is left-censored; a level never observed is unreached. Neither receives an invented crossing time.

The native executable puts the entry and exit markers around `Executor::execute`. Initial graph construction, model/plan loading, offline proof checking, final graph export and serialization are outside the window. An external observer samples Darwin `PROC_PIDTASKINFO.pti_resident_size` at a nominal 1 ms interval and includes exact native endpoint RSS values. First-passage times are the *observed* crossings, with the preceding sampling interval saved. Shorter excursions between samples can be missed.

Each arm gets four fresh sampled processes and four fresh unsampled controls per workload. The arms cycle through all four order positions, and the sampled/control order for each arm alternates across rounds. The sampled peak, maximum observed gap, interval surrounding the threshold, and count of points are recorded separately for each process. The unsampled controls characterize combined observer/marker overhead and timing variation.

## Results

| Workload | Arm | Samples per process, range | Entry RSS, MiB | Peak RSS, MiB | Peak rise, MiB | Common growth first crossing, ms | Common absolute first crossing, ms | Unsampled inference, ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | leaf | 30–32 | 258.97 | 269.91 | 10.94 | 27.93 | 2.82 | 34.31 |
| sum-bits | trace | 28–34 | 259.09 | 270.00 | 10.91 | 28.45 | 2.86 | 34.82 |
| sum-bits | ripsat | 28–31 | 259.03 | 270.00 | 10.97 | 27.13 | 2.62 | 33.22 |
| sum-bits | union | 29–34 | 259.09 | 270.05 | 10.95 | 29.38 | 2.57 | 34.27 |
| 3mm | leaf | 1344–1511 | 409.91 | 720.69 | 310.78 | 1034.54 | 988.59 | 1781.72 |
| 3mm | trace | 1347–1527 | 410.29 | 720.20 | 309.91 | 1039.34 | 970.76 | 1785.53 |
| 3mm | ripsat | 1352–1501 | 410.27 | 706.44 | 296.16 | 995.92 | 929.36 | 1769.25 |
| 3mm | union | 1414–1468 | 410.28 | 706.80 | 296.52 | 1063.15 | 990.93 | 1775.68 |

All 32 sampled processes reached both levels in the inference window; none were left-censored or unreached. Medians above use four independent processes per arm. All 64 measured/control requests agreed on original Run count, final graph digest, issued roots and confirmed internal commits. Filters and verified state changed costs before reaching the common growth level, but this four-process comparison cannot identify the contributors to each page or determine a stable latency ranking. The per-process traces, maximum sampling gaps, own observed peak times and paired timing deltas remain in the numerical archive.

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/ripsat-neural-bake
python "$d/rss.py" "$EXP" "$NATIVE" "$TRACE_LIBRARY" "$SEMANTIC_STUDY/results.json" "$OUT"
```

The adjacent per-target `*-ripsat.json` files must be the semantic study's verified artifacts. [Full trajectories and counters](rss.json)
