# RipSat constructor-Set publication with and without the ordinary trace library

This compares four actual native executions using the [opt-in publication ABI](../ripsat-publication-chain/README.md) and its pinned executor. The default Let-only experiment remains separate. Leaf uses individual filtered neural parents, trace installs only the donor trace library, RipSat installs the authenticated Let prefix plus its separately typed two-hop Set publication, and union installs the deduplicated ordinary Let paths **and** that same explicitly authorized Set. The Set is never placed in the ordinary Let library. Each target rederives the full certificate from immutable donor inputs, verifies its program SHA-256, and passes that identity to the native loader. A fifth, semantic-only control disables the Set capability on the exact same union of ordinary paths.

## Strict source-aligned FEPT

| Program | Arm | Explicit root + selected child packets | Ordinary internally committed / Set terminal | Final-visible source nodes per packet | Complete inference median |
|---|---|---:|---:|---:|---:|
| sum-bits | Leaf | 12,662 | 0 / 0 | 0.212526 | 32.99 ms |
| | Trace | 12,595 | 67 / 0 | 0.213656 | 32.88 ms |
| | RipSat | 12,601 | 35 / 26 | 0.213554 | 33.55 ms |
| | Union | 12,534 | 102 / 26 | 0.214696 | 34.23 ms |
| 3mm | Leaf | 558,074 | 0 / 0 | 0.166032 | 1,757.95 ms |
| | Trace | 556,500 | 1,574 / 0 | 0.166501 | 1,778.62 ms |
| | RipSat | 555,913 | 1,229 / 932 | 0.166677 | 1,801.68 ms |
| | Union | 554,339 | 2,803 / 932 | 0.167150 | 1,771.14 ms |

**Actual incremental Set effect inside the union.** Keeping the exact same ordinary trace+RipSat Let capabilities but withholding the Set gives 12,560 / 555,271 external packets on sum-bits / 3mm. Enabling the Set reduced those totals by **26 / 932**. We counted source commit ordinals during each independent arm. All 26 / 932 terminal ordinals and their middle ordinals still appeared in the true union; none was already internal in trace-only or in the Set-withheld union. No original trace-covered ordinal was lost. The measured union saved 61 / 2,161 packets relative to trace-only, including 35 / 1,229 first-hop Let activations. These are measured set differences for this fixed pair of programs. Different template families can compete for the same middle or winner.

Every confirmed second hop checked the emitted first root, signed middle, middle's actual fresh Get FactRef at Set op 1, generation, named terminal atom and original later Run; no terminal had its own duplicate external packet. The terminal RHS invocations directly created 26 / 932 new original constructor identities, of which **6 / 139** survived the original final export. Those identities also exist in ordinary execution. The numerator therefore remains 2,691 / 92,658 in every arm. We charge all actual root proposals including failures and every selected nested packet. Three-way source and physical origin checks include each Run's ordered RHS, effective writes, unions, Spine, root/child IDs, resulting constructor origin/visibility and final state. The whole native inference times use one warmup and four order-rotated resident measurements per arm. The true union took longer than leaf in these medians. [Paired measurements, original-ordinal comparisons and terminal provenance](results.json)

## Independent inference-window resident memory

| Program | Metric | Leaf | Trace | RipSat | Union |
|---|---|---:|---:|---:|---:|
| sum-bits | First passage at +9.27 MiB, ms | 25.59 | 27.42 | 26.60 | 26.13 |
| | Observed peak, MiB | 269.97 | 270.11 | 270.02 | 270.08 |
| 3mm | First passage at +264.11 MiB, ms | 1,011.73 | 1,075.11 | 1,037.52 | 1,085.09 |
| | Observed peak, MiB | 718.82 | 720.36 | 706.33 | 706.88 |

Thresholds come from the [independently frozen default CPU calibration](../verified-wave-rss/README.md) and use each measured process's own starting RSS. The paired absolute thresholds are 266,530 and 679,982 KiB. Each arm used four fresh sampled processes and four fresh unsampled controls per workload. The external observer samples Darwin process RSS at nominal 1 ms, starting immediately before the native executor and ending before graph export. Acquisition intervals, maxima and all observed points are recorded. All processes reached both thresholds, with no left-censored or unreached trials. Each process independently repeated the expected state digest, Run count, emitted packets, signed commits and Set confirmations; production audit-only score inputs were zero. RSS includes allocator retention, model state and ordinary graph maintenance. The lower 3mm sampled peak was not accompanied by faster time to the common growth threshold. [Raw traces, calibration identity and unsampled controls](rss.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/ripsat-publication-matrix
native="$EXP/ripsat-set-receipt-pinned/session"
python "$d/study.py" "$EXP" "$native" "$EXP/publication-matrix"
python "$d/rss.py" "$EXP" "$native" "$EXP/publication-matrix/results.json" "$EXP/publication-matrix-rss"
python "$d/verify.py"
```

The study uses the original dot-product and jacobi-1d donor recipes for authorization; only the untouched static target program is used to relink each certificate. Target executions are held out from selection.
