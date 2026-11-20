# Incremental learned multi-witness generation on the full Rust schedule

Two questions motivated this ablation. Can a previous neural candidate tuple be reused when the chosen parents are still live? When a table genuinely changes, can the compiler identify which old pairs are provably irrelevant without validating each entire candidate first?

All online decisions run on CPU with frozen weights. The executed rules, graph, order of writes, actual Spine resumes, distinct winning source RHS and physical template allocations use the upstream high-coverage joint verifier. For an independent pair of rows, the model only decides the possible pointer relation. Source unification, remaining primitive operations, reads and root allocation still go through the real verifier after the rule's proposed batch is sealed. Clearing the verifier residual does not make the compiler, the source scheduler or canonicalization neural.

## Source-preserving transformations

1. **Whole raw-batch cache.** Cache the generated row offsets and maximum selected epoch under the rule and all independent table versions. The suffix may change. Reuse is legal only when today's projected cutoff is at least the previous cutoff and the old generation never exhausted its budget. A changed cutoff filters the same immutable parents and issues new per-Run receipts. It retains up to 16 MiB of raw-batch payload; over-budget buffers stay on the original generator. Most source tables changed between uses. On sum-bits there were 104 hits / 3,180 nonempty rule occurrences; it was slower, 96.3 → 98.5 ms. [Paired results](memo.json)
2. **Two-parent delta routing.** Precompute candidate columns from the trained port projection. If an independent row must be fresh, enumerate fresh left rows against right plus stale left rows against fresh right. A reverse query compares the *left query* signature with the *right key* signature and checks every additional learned column. It restores the original per-root ordering before issuance. The switch uses table sizes, visible epochs and neighborhood width. This changes enumeration work with the same raw proposal SHA. [Index/ownership comparison](two-parents.json)
3. **Incremental snapshots.** Consume native `ChangeBatch` at the same post-rebuild boundary as the normal indices. On a version change, decode the reported changed addresses, merge them with the ordered visible snapshot, and expire table-version dependent columns. Full rebuild covers untracked transitions. Diagnostic executions independently decode the entire source snapshot after each update and assert identity, epoch and every field. [Snapshot comparisons](deltas.json)
4. **Learned signature factorization.** Store compatibility between the frozen queries and keys across tables. Maintain both directions incrementally when a new signature enters the registry. A typed column indexes the complete packed key across three views. Lookups for a query gather the applicable table rows; a cached or single-bucket response preserves the original ordering and all learned false positives. Only source row offsets and learned signature compatibility are cached, never successful matches. For jacobi-1d this discovered 4,482 compatible code pairs among 3,351 observed query and 3,023 key codes, and served 660,553 shortlist calls. [Full receiver-index ablation](codebook.json)
5. **Before sealing, prove a tuple cannot be fresh.** For each relevant source column record its maximum visible epoch per *key-side* learned signature. Any valid equality has the same key-side projection on the two equal values. A collision can leave excess candidates. It cannot establish a false absence. For a proposed old row or pair, if all possible other source atoms are provably older than the rule watermark, no source delta can belong to the proposed binding. Prune that prefix. The correlated alternative also tests joint column signatures for necessarily absent suffix tuples. These variants deliberately issue fewer raw packets. They preserve the native endpoints and the credited witnesses. [Full-record guard comparison](freshness.json) · [Combined tied-code controls](correlated.json)

## Measurements

Apple M3 Max, seed 1703. The following end-to-end measurements compare a separate actual default-feature vanilla Rust allocator/engine with the same allocator in the neural execution. A resident root recipe still carries the source references and validated compiled layout and really supplies the allocator. Runs rotate and reverse arm order. Each audited input checks the Run schedule, ordered RHS, effective writes, Spine, unions, class partition and final typed graph. The larger cases were frozen before this comparison. Weights came from the original four training families; no workload-specific rule or row is admitted by name.

| Full source | Vanilla ms | 3-view resident neural baseline ms | Shared signatures + delta + freshness ms | Original → remaining sealed multi tuples |
|---|---:|---:|---:|---:|
| sum-bits | 22.30 | 79.71 | 57.80 | 21,443 → 9,000 |
| dot-product | 19.56 | 81.30 | 57.17 | 21,210 → 13,395 |
| jacobi-1d | 117.74 | 959.11 | 470.77 | 221,274 → 101,374 |
| conjugate-gradient | 349.81 | 5816.35 | 1957.46 | 1,157,963 → 276,345 |

The optimized lane covered 41,319/41,319 RHS and directly constructed 32,721/32,819 fresh physical Cells on jacobi-1d. Reducing candidate visits substantially improves the learned route on the large inputs. On conjugate-gradient the learned route committed 131,371/131,371 RHS and directly constructed 97,026/97,139 new physical Cells. It remains slower than vanilla on all four. The vanilla timing makes no neural coverage claim; it executes the original exact programme. [Conjugate-gradient raw timing and checks](conjugate.json)

### Interaction with a baked projection table

A second comparison ties the two trained weight matrices, uses one view with Hamming radius zero, bakes all 65,536 projections of a 16-bit bipolar input, and enables direct packed lookup. Both arms read the same actual exported LUT. The codebook factorization is unnecessary for zero-radius packed lookup. For the retained mode request `multi_mode="rowdeltapairguardstackseallearned"`, `radius=0`, `packed_lookup=true` and `baked_row_index=false`. The incremental option runs after source frame publication, ahead of the same native verifier.

| Source, same baked weights | Vanilla ms | Packed lookup ms | Plus incremental snapshot and freshness ms | Plus correlated guard ms |
|---|---:|---:|---:|---:|
| sum-bits | 21.42 | 57.41 | 52.95 | 52.16 |
| dot-product | 18.07 | 53.37 | 49.70 | 49.88 |
| jacobi-1d | 110.78 | 464.80 | 400.85 | 413.28 |
| conjugate-gradient | 360.52 | 2315.81 | 1922.96 | 1892.33 |

For jacobi-1d the correlated guard removed more raw tuples than the freshness-only guard, 117,544 vs 142,365, yet it took longer. Its extra per-prefix lookup is part of the measured cost. The two additional index variants should remain optional. [Baked/packed isolated delta and guard](baked.json)

### Where time remains in the retained configuration

The diagnostic build clocks multi-parent source frame acquisition, raw proposal issuance plus sealing, and the native verifier separately. Each entry is the median of four executions after a warmup. The full inference column includes the rest of Cell CPU execution. Timing comparisons above use the clock-free path. [Per-rule phase costs and top eight issuers per workload](phase-profile.json)

| Source | Inference ms | Frames ms | Issue and seal ms | Verify ms |
|---|---:|---:|---:|---:|
| sum-bits | 56.41 | 0.89 | 11.63 | 3.79 |
| dot-product | 54.59 | 0.79 | 11.96 | 5.30 |
| jacobi-1d | 425.36 | 4.08 | 89.96 | 41.06 |
| conjugate-gradient | 1933.75 | 12.51 | 441.48 | 168.00 |

On the larger holdouts, rule 10 ranks first by issuance cost. These measurements concern compiled multi-parent candidate search with trained, baked signatures. They do not establish how much time a higher-order template can save downstream.

### Reproduction

All data and builds live on the external workspace. Use a fresh output directory per command. `build.py OUT` composes the original checked Rust program with this isolated installer and the CLI allocator. `--baked` additionally composes the common LUT and code-table exporter.

```sh
dir=benchmarks/pass3-cell-gpu/incremental-neural-index
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-neural-index" --baked
python "$dir/holdout.py" "$e/NEW-neural-index/session" "$e/compact-vanilla-20261121" "$e/compact-holdouts-20261121-v1" "$e/NEW-pair-guard" \
  --cases sum-bits dot-product jacobi-1d conjugate-gradient --modes stackseallearned rowdeltapairguardstackseallearned rowdeltacorrguardstackseallearned --tied-packed
```

For the three-view unfactored and factored comparison, use mode names `stackseal3xlearned`, `globalrowdeltapairdeltastackseal3xlearned` and `globalrowdeltapairguardstackseal3xlearned` without the `--tied-packed` flag. Run `python verify.py` in this directory to check the archived results.

The earlier `memo`, `two-parents`, `deltas` and `freshness` reports use the older full-wire proof representation and the joint binary's unassisted exact lane (its allocator differs from the separate vanilla CLI). Read timing differences within each paired study. `codebook` and later holdout results use the CLI allocator, resident root layout and the independent vanilla executable. The index tables consume memory proportional to encountered code pairs and live snapshots; these experiments did not measure peak RSS or cross-machine behavior.
