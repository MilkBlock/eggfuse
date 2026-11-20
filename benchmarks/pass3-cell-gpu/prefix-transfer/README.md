# Transfer of the learned prefix filter to additional eggcc inputs

3mm and Deriche were selected before running the new transfer benchmark. Their case-specific source parts are 301,650 and 306,028 bytes, respectively, compared with 159,452 bytes for conjugate-gradient. Source size is a selection criterion; actual generated graph size and work are measured separately. Neither workload supplied training windows, rule timing labels, extra projection weights, thresholds or index budgets.

The experiment freezes the certified seed 1703 CPU actor; stale single-parent admission; the compiled constant guard; shared multi-parent pages; and the two-column, two-view port configuration. It compares the original Rust executor, the integrated learned path without the forward filter and the frozen configuration. The conditional Python packaging and 2× targets are judged on real complete passes with both source and physical attribution.

The frozen path uses the integrated CPU source executor, single-parent frontier, constant guard, shared multi-parent pages, two-column forward viability, two learned views at zero radius, occurrence-local signed atom tests and compact typed port columns. Both source programs were compiled through Cargo. All original RHS ordinals have genuine winning neural roots/children and each credited fresh physical ID was allocated by a verified recipe. No exact residual was enabled. Six rotating full resident inference samples follow warm-up at seed 1703.

| Program | Exact source RHS | Direct new Cell IDs / all fresh | Vanilla | Integrated legacy | Frozen prefix (ms) |
|---|---:|---:|---:|---:|---:|
| 3mm | 294,917 | 229,311 / 229,880 | 944.77 | 5,093.01 | 2,191.42 |
| Deriche | 635,818 | 450,414 / 452,913 | 1,600.25 | source divergence, timing excluded | 3,913.87 |

The original finite-budget Deriche control first diverges on source Run 819 in always-run (9,794 instead of 12,914 RHS). Its endpoint is preserved as a failed arm. The narrower frozen route has zero budget exhaustions and passes independently. On 3mm the full raw multi-parent list shrank from 9,616,838 to 477,862 tuples. A speedup over the slow learned control does not meet the parity threshold against vanilla.

```sh
python benchmarks/pass3-cell-gpu/prefix-transfer/prepare.py "$EXP/transfer-bundles"
python benchmarks/pass3-cell-gpu/prefix-transfer/study.py "$EXP" "$EXP/tiered/session" "$EXP/transfer-bundles" "$EXP/transfer-results"
python benchmarks/pass3-cell-gpu/prefix-transfer/verify.py
```

Use the original research build for the legacy divergence. The complete-generation study checks the corrected finite and unlimited contracts.

## Instrumented workload phases

Three resident samples on the complete-generation build separately measured each original source phase. The following inner search clocks are inclusive in the outer search time. Initial graph setup and final export remain outside inference.

| Workload | Measured inference / search | Multi-parent issuance / verification | Single-parent header / score | Outside search | Half vanilla transfer median (ms) |
|---|---:|---:|---:|---:|---:|
| 3mm | 1966.1 / 1499.1 | 601.7 / 163.1 | 251.8 / 1.7 | 467.0 | 472.4 |
| Deriche | 3604.1 / 2740.8 | 796.4 / 209.1 | 450.7 / 3.4 | 870.7 | 800.1 |

On these samples, removing every measured search interval would leave about five milliseconds of headroom for 3mm's 2× target and exceed Deriche's by about 71 ms. These approximate limits compare an instrumented phase study and the separate matched, uninstrumented vanilla transfer timing. They identify the size of the remaining joint search/ordered-work problem; they do not measure a zero-search implementation. [Recorded phase samples](phases.json)
