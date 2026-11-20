# Two learned parents and opposite guards

The compiler groups seminaive source rules with the same ordered table selections, argument signature, typed output projection and ruleset membership. Their last instruction must compare the same two signed integers using opposite strict inequalities. The source type checker ensures the guard result occupies a fresh Unit slot. Four training workloads exercised both branches of rules 509 and 510. Rules 349 and 350 also satisfy the structural test but had zero training RHS. The frozen library admitted only 509 and 510. [Extracted catalog](pair-catalog.json)

For each original Run the network proposes two physical parent rows from the sealed query. Its packet names the sibling as an alternative. Independent execution generates the two packets separately. Raw sharing reuses the ordered parent proposals and checks them again at the sibling. Verified sharing checks the physical pointer prefix once, compares the two exact signed values and retains the binding and conditional recipe for the selected sibling. Equal values produce no child. Source rules consume the result at their original schedule position. A changed Run, watermark or table generation invalidates the waiting batch. The stale control deliberately discards every waiting batch. [Native implementation](pairs.rs) · [Compiler and engine integration](pair_overlay.py)

The audit compares every multi-parent winner's source ordinal, ordered physical parents, and identity of the exact earlier published functional port. This measures earlier committed parents that the sibling actually reads. The sibling experiment saves work between two consumers in one Run. The separate SubTuple continuation can directly install a future consumer from a prior Run's winning output. [Full audit](pair_study.py)

## Larger programs held out during discovery

Both frozen template families transferred to Jacobi and conjugate-gradient. The independent vanilla process executed the same input program and generated the reference digests. Every arm matched its ordered RHS, effective writes, Spine resumes, union sequence, schedule and final graph. Resident times are medians of six alternated samples per seed. The two seeds use their own frozen weights. [Holdout test and native receipts](larger-holdouts.json)

| Program / seed | Source RHS | SubTuple child RHS / max depth | Earlier-Run parents represented among sibling winners | Shared raw tuples | Vanilla / original joint / both (ms) |
|---|---:|---:|---:|---:|---:|
| Jacobi / 1703 | 41,319 | 413 / 11 | 445 | 980 | 109.55 / 1,128.23 / 1,130.50 |
| Jacobi / 1709 | 41,319 | 413 / 11 | 445 | 966 | 115.27 / 1,182.24 / 1,153.49 |
| Conjugate-gradient / 1703 | 131,371 | 1,006 / 13 | 543 | 1,173 | 369.47 / 6,964.71 / 7,123.28 |
| Conjugate-gradient / 1709 | 131,371 | 1,006 / 13 | 543 | 1,207 | 385.44 / 7,168.31 / 7,159.94 |

The learned root and merge tokens directly account for 32,721 of 32,819 fresh physical Cells on Jacobi and 97,026 of 97,139 on conjugate-gradient. The two families operate on larger graphs with the same proofs and longer chains. The combined joint engine still takes roughly 10–19 times the inference time of the ordinary Cell engine on these two source programs.

## Four frozen-program ablations

All times cover the full source inference phase. Work counts include the new routed comparison. Each row has eight warm paired samples with a rotating arm order. [Per-arm timings, source counters and proof receipts](siblings.json)

| Program / seed | Reused sibling calls | Raw tuples saved | Net comparisons saved | Winners with earlier parents / winners | Base / independent / raw / verified (ms) |
|---|---:|---:|---:|---:|---:|
| sum-bits/1703 | 83 | 206 | 206 | 100 / 200 | 113.16 / 114.63 / 112.37 / 114.12 |
| sum-bits/1709 | 83 | 207 | 206 | 100 / 200 | 113.14 / 116.67 / 113.13 / 111.41 |
| dot-product/1703 | 94 | 267 | 266 | 130 / 260 | 110.69 / 109.39 / 108.88 / 109.28 |
| dot-product/1709 | 94 | 268 | 266 | 130 / 260 | 111.77 / 109.94 / 110.82 / 110.26 |
| gemm-bias-relu/1703 | 79 | 348 | 346 | 164 / 328 | 331.62 / 331.53 / 325.98 / 326.40 |
| gemm-bias-relu/1709 | 79 | 349 | 346 | 164 / 328 | 322.86 / 331.28 / 338.13 / 328.42 |
| stable-argmax/1703 | 62 | 202 | 202 | 99 / 198 | 107.89 / 106.81 / 106.54 / 106.99 |
| stable-argmax/1709 | 62 | 207 | 202 | 99 / 198 | 108.53 / 109.52 / 110.19 / 108.92 |

The work reduction is repeatable. The timing changes include both signs across seeds, and shared verification does not reliably accelerate the whole Pass.

## Reproduce

Use the environment and frozen directories in the main README.

```sh
python "$dir/pair_bake.py" "$families" "$e/NEW-siblings.json"
python "$dir/build.py" "$e/NEW-pairs-build" --pairs
python "$dir/pair_study.py" "$e/NEW-pairs-build/session" "$ref" "$families" "$caps" "$train" "$e/NEW-siblings.json" "$e/NEW-pairs-study"
python "$dir/holdout.py" "$e/NEW-pairs-build/session" "$e/compact-vanilla-20261121" "$ref" "$e/compact-holdouts-20261121-v1" "$e/NEW-pairs-holdouts"
python "$dir/verify_pairs.py"
```
