# Tying query and key weight matrices in a sealed neural pointer index

In each case the same CPU recurrent single-row gate, Rust graph and nested merge certificate run over the full Pass 3. Independent multi-parent tuples are emitted before validation. One comparison applies the previously trained asymmetric query and key weights to the two ports. Another freezes their arithmetic mean as a shared encoder. Equal canonical typed values then necessarily have identical learned signatures. Exact zero-radius bucket lookup replaces an approximate Hamming-neighborhood walk. Colliding unequal values still require exact verification at the end of the batch. Program-calculated complete-key suffixes still run after sealing.

The fixed-code control takes bits from the mixed primitive/e-class identifier. It runs the same source verifier so it measures how much of the effect is simply due to a common identifier representation. Its multi-parent bindings are classified as deterministic, even when they happen to equal the learned arm. A separate unequal-weights/zero-radius control permits an ordinary residual to fill omissions. The primary original, tied and fixed projections run without exact multi- or single-provider fallback.

| Workload / seed | Original three-view radius 2 | Tied one-view radius 0 | Tied three-view radius 0 | Fixed three-view bits | Exact Rust only |
|---|---:|---:|---:|---:|---:|
| sum-bits/1703 | 78.69 | 70.73 | 70.28 | 69.32 | 24.28 |
| sum-bits/1709 | 79.35 | 70.09 | 69.98 | 69.24 | 24.60 |
| dot-product/1703 | 78.62 | 67.56 | 68.43 | 67.19 | 21.68 |
| dot-product/1709 | 76.95 | 67.26 | 67.18 | 66.31 | 20.61 |
| gemm-bias-relu/1703 | 230.83 | 183.83 | 186.42 | 178.94 | 46.92 |
| gemm-bias-relu/1709 | 240.06 | 187.39 | 186.27 | 185.72 | 48.90 |
| stable-argmax/1703 | 76.19 | 66.06 | 65.90 | 65.68 | 26.50 |
| stable-argmax/1709 | 76.89 | 68.19 | 69.16 | 69.08 | 25.86 |

Entries are complete native inference medians in milliseconds over six interleaved measured samples per arm. Every row passed the ordered RHS, effective writes, Spine, union and final-state audit. All tied cases recovered the complete source with no residual. Fixed bits achieved similar retrieval and timing: the present equality-only input domain supplies no clear need for a learned key encoder simply to retrieve equals. Fixed bits do not establish 98% *neural* attribution. This experiment changes the query/key representation and the size of the lookup neighborhood together; the asymmetric zero-radius arm helps identify the effect of mismatched encodings. [Source-verified results](results.json)

Reproduce with `study.py BINARY REFERENCE CORPUS EVAL_CAPTURE NEW_OUT`, using the [bundled native Rust executor](../joint-witness/README.md) built with the shortlist and merge child. No test program contributes to the learned projections.
