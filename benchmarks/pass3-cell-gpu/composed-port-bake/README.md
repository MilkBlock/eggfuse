# Runtime cost of composing a pair of Cell rules

A selected SubTuple producer owns a future equality or greater-than continuation on its integer length port. For a recursive step the compiler proves that the new published length is the previous length minus the source constant. Source initialization and external producers can still install different parents. The baseline already inherits this request across Runs and knows which branch it may take. It still walks every visible row at each consumer and builds a separate compact child recipe before sealing that row again. The experiment changes these specific costs inside the real standalone Rust Cell CPU path. It preserves each original stage and published data object.

## What is shared

- A boundary partitions the constructor table into ordinary external rows and template-owned rows. The latter are indexed by their checked branch and visible epoch. On entry it sends the external rows and the fresh owned rows selected for this consumer, keeping their original physical order. The generator restores skipped row counts, freshness sums and serial positions so later neural state and source ticket IDs agree. The compiler limits aggregate freshness arithmetic to a range where integer counts are represented exactly in f32.
- The first fused verifier reuses the exact instance just constructed and its known physical parent. It checks the template, source Run, physical parent and version. The ordinary path decodes that parent again and verifies each projected field a second time.
- The inline form reserves the original source serial and keeps the enclosing owner's checked child port. It creates the bound external root when the source can use the projected binding. It eliminates the independent intermediate child recipe, its per-port projection copy and its reference packet. The visible RHS, original root serial, source graph row and published Spine ticket remain separately identifiable. All source graph insertions, unions, rebuild and retained consumers still execute. [Runtime and compiler hooks](overlay.py) · [Source boundary](boundary.rs)

The action-granularity macro already lets one proposal name two source bindings. The ownership experiment stores certified cross-template references but paid higher overall maintenance in its 31-sample sum-bits measurement. Here the unit of accounting is a real publication and each later lookup or proof operation it can bypass. [Prior macro issuance](../action-granularity/README.md) · [Prior cross-template storage](../../ownership-composition/README.md)

## Runtime gate and training records

A caller can pass higher_config.composed and higher_config.macro_policy in a native request. Mode 0 executes separate leaves, 1 uses the ordered boundary, 2 also reuses the exact sealed projection and 3 also embeds the intermediate proof in the enclosing owner. Mode 4 uses post-rebuild source changes to maintain the same boundary. A missing policy admits every actual parent. A supplied policy consumes eight f32 fields, uses sequential multiplication and addition from its bias, and admits the parent when the result reaches its threshold. The input contains a constant, the original producer rule modulo 64 scaled by 63, clamped effect position scaled by 15, clamped signed length scaled by 32, clamped depth scaled by 16, equality and strict-greater guard bits and the recursive-depth bit. Training can pass its own weights. The fixed mixed control admits only instances that already have an inherited ancestor.

The native audit returns higher.charges with one row per guard-bearing publication. Each row gives the visible features, source ordinal, owner, producer and effect, issue epoch, row version, generation and transfer depth. Its four counts give visible encounters with the consuming pair, encounters with the correct fresh branch, source-winning children and owner header checks while updating the frontier. The ablation compares the full per-generation encounter, positive and winning counts even when the runtime chooses to leave some instances on the old path. In an inline arm, positive encounters give the number of standalone child recipes removed. Global frontier maintenance on external rows is charged separately. Row ordinals and outcomes are withheld from the policy. [Measurement and native gates](measure.py)

## Attribution

For each input and seed we compare leaf execution, the ordered boundary, single sealing and inline proof, plus frozen all-off and partial admission controls. Each arm has an independent source audit. Each within-family comparison also hashes the complete publication sequence, winning parent/child receipts, source root recipes, fresh physical IDs, merge children and every committed single-witness ticket. Separate resident timings alternate the arm order over eight samples. Direct physical allocation coverage exceeds 98% throughout. [Primary results](receipts.json)

| Source | Leaf entry row reads removed | Stale / fresh other / fresh selected | Intermediate recipes and repeat seals removed | Repeated field checks removed | Versioned header reads for complete refresh / incremental | Net entry visits after incremental header reads |
|---|---:|---:|---:|---:|---:|---:|
| Sum-bits | 4,468 | 4,288 / 90 / 90 | 90 | 446 | 6,054 / 512 | 3,866 |
| Dot-product | 1,242 | 1,154 / 44 / 44 | 44 | 220 | 2,237 / 320 | 878 |

Most omitted reads come from stale singleton premises. That work is also a target for a standalone seminaive entry index. The additional comparison unique to the composed proof is the second seal and its field checks. Only 90 and 44 fresh transitions actually issue a child. On sum-bits 104 of 194 publications never won a child. Some still supplied valuable negative evidence. Source root 693, issued by rule 138 effect 5 at Run 106, had 84 further consumer encounters, zero eligible positive branches and zero wins. The full-refresh implementation re-read its indexed header 42 times.

The two Run-boundary indexes illustrate how the same selection policy can have different costs. The first mode rebuilds the whole partition whenever the source table or its request generations change. After charging every header read, net entry visits increase by 1,676 on sum-bits and 1,039 on dot-product. The incremental mode consumes immutable post-rebuild changed addresses and higher-order publication updates. It starts on the first selected owner, refreshes a complete snapshot when the journal cannot account for a version change, and checks the source generation at each consuming entrance. Audit mode independently compares the resulting index with the complete live source table. [Incremental index](delta.rs) · [Interleaved results and counters](incremental.json)

| Source / seed | Independent leaves | Inline, full refresh | Inline, incremental | Incremental all refused | Incremental recursive only |
|---|---:|---:|---:|---:|---:|
| sum-bits/1703 | 112.19 | 111.84 | 112.20 | 112.93 | 111.45 |
| sum-bits/1709 | 110.61 | 111.74 | 110.88 | 109.77 | 111.60 |
| dot-product/1703 | 111.02 | 110.95 | 111.00 | 111.64 | 110.40 |
| dot-product/1709 | 112.00 | 111.05 | 110.57 | 113.74 | 112.73 |

Times are complete resident source inference in milliseconds. The incremental engine performs 7,694 rank lookups, moves 471 live-vector entries and consumes 293 graph change addresses on sum-bits. Dot-product incurs 3,210 rank lookups, 458 moves and 150 changed addresses. Accepted owners account for 193 of the 512 sum-bits header reads and 99 of the 320 dot-product reads. The remaining global maintenance includes external rows and retired addresses. Measured savings in graph reads did not translate into a repeatable full-pass acceleration across the two sources.

## Reproduction

The build pins the original request-bearing runtime revision. The real source bundles and captures are those used in the higher-order Bake study. Full conformance checks run outside the timed requests. The native executable and its installed source hashes are recorded for the initial and incremental comparisons. [Initial build](build-receipt.json) · [Incremental build](incremental-build-receipt.json)

```sh
dir=benchmarks/pass3-cell-gpu/composed-port-bake
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-composed-port-build"
python "$dir/measure.py" "$e/NEW-composed-port-build/session" "$e/pass3-atlas-integration-20261120" "$e/repair-bake-families-20261120" "$e/recurrent-compositions-20261120" "$e/recurrent-compositions-train-20261120" "$e/NEW-composed-port-study" --arms leaf inline delta delta-none delta-mixed --save-charges
python "$dir/verify.py"
```
