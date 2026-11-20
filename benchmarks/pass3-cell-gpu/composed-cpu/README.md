# Combining published single-parent headers and lazy arithmetic ports

In the standalone native Cell CPU engine, a single-parent rule can reuse a source header updated by the preceding publication. A multi-parent rule can test a compiler-proved arithmetic relation on learned port signatures before sealing a full proposal. The lazy variant delays arithmetic until a candidate survives its other filters and caches integer signatures. Each admitted proposal still passes the exact verifier. The two changes affect different parts of the same resident execution.

We ran six source Pass 3 programs at checkpoint seed 1703. All learned arms use one executable with frozen weights, an identical source schedule and the same two learned views. “Off” uses the prior frozen model with both optimizations disabled. Vanilla uses the separate default EggFuse CPU executable. We interleaved all configurations, rotated and reversed trial order, and excluded the first warmup. The reported medians include issuance, verification and ordered execution. Loading the process and offline Bake are outside the resident inference interval.

| Source | Vanilla ms | Off ms | Headers ms | Eager arithmetic ms | Both eager ms | Lazy arithmetic ms | Headers + lazy ms | Headers + lazy / vanilla | Paired wins over off |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.76 | 32.25 | 31.60 | 32.02 | 31.41 | 31.57 | 31.35 | 1.51× | 5/6 |
| dot-product | 18.70 | 30.91 | 31.29 | 30.66 | 31.44 | 30.89 | 30.93 | 1.65× | 3/6 |
| jacobi-1d | 116.89 | 195.82 | 182.52 | 186.95 | 182.88 | 184.39 | 180.92 | 1.55× | 6/6 |
| conjugate-gradient | 328.93 | 671.95 | 636.08 | 669.38 | 639.24 | 644.11 | 620.82 | 1.89× | 6/6 |
| 3mm | 894.72 | 2,144.36 | 2,002.35 | 2,069.80 | 1,952.09 | 2,041.71 | 1,924.21 | 2.15× | 4/4 |
| deriche | 1,594.99 | 3,806.96 | 3,718.61 | 3,826.69 | 3,689.25 | 3,752.78 | 3,626.14 | 2.27× | 4/4 |

On 3mm the combined path reduced the learned median by 10.27%. On Deriche the reduction was 4.75%. Dot-product stayed within 0.03 ms of the disabled median, with three wins out of six. The two largest programs still take over twice the vanilla time. A single checkpoint and four to six pairs per program limit conclusions about effect size.

## Work and correctness

| Source | Sealed multi-parent tuples, off → headers + lazy | Lazy checks | Actual port encodes | Distinct source RHS | Fresh Cells with traced recipe / all fresh |
|---|---:|---:|---:|---:|---:|
| sum-bits | 7,970 → 5,912 | 2,290 | 7 | 7,265 | 5,867 / 5,868 |
| dot-product | 8,664 → 7,207 | 1,595 | 9 | 6,704 | 5,666 / 5,682 |
| jacobi-1d | 50,140 → 33,250 | 18,134 | 13 | 41,319 | 32,721 / 32,819 |
| conjugate-gradient | 127,051 → 83,313 | 46,944 | 14 | 131,371 | 97,026 / 97,139 |
| 3mm | 477,862 → 220,972 | 267,175 | 25 | 294,917 | 229,311 / 229,880 |
| deriche | 574,416 → 309,277 | 277,385 | 26 | 635,818 | 450,414 / 452,913 |

The audit compares ordered RHS inputs, effective writes, Spine resumes, union events, Run boundaries, schedule and final graph with vanilla. Across the learned arms it also compares winning single- and multi-parent proposals and physical Cell IDs. The source winner ledger accounts for every committed RHS binding and the issuer reports zero exhausted searches on all six programs. The sealed tuple count measures work done before verification. It includes proposals that never commit.

## Reproduce

Use the experiment artifact root containing the frozen source programs, vanilla controls and trained port tables referenced by the shared pair-source-frontier harness. Supply fresh output directories.

```sh
d=benchmarks/pass3-cell-gpu/composed-cpu
python "$d/build.py" "$EXP/new-composed-build"
python "$d/study.py" "$EXP" "$EXP/new-composed-build/session" "$EXP/new-composed-core"
python "$d/study.py" "$EXP" "$EXP/new-composed-build/session" "$EXP/new-composed-large" --cases 3mm deriche --repeats 4
python "$d/verify.py"
```

The final command checks the archived measurements, sample counts, source equivalence flags and activation counters. [Four program runs](core.json) · [Larger held-out programs](large.json)
