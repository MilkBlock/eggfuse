# Capacity versus training-family diversity on a fixed whole-pass proof vocabulary

The network has access to the initial program and graph and its own generated nullary-root latents. A decision activates one typed continuation to a root's effect port. Every model can choose exactly the same certificates. Its output is sealed before the first Run. The device verifier and residual search then process the same source program. All arms preserve ordered RHS inputs, effective writes, actual Spine resumes, class roots, union history and final graph.

The 3 × 2 experiment uses a shared two-hidden-layer tanh scorer with 40,093, 159,633 or 640,665 trainable parameters (four bytes per parameter). Each hidden width is chosen before training. For each size we train on the first two or all four preassigned source families. For a given seed, optimizer, initialization at each matched width, 400 updates, 400 program draws, 51,200 candidate draws and the 0-logit decision threshold are fixed. Changing the number of families changes which graphs and candidate examples appear. The two-family group is nested in the four-family group. Training uses MPS over reference labels from the training families. Each compiled source program in this experiment has the same static rule schema; no unseen-template generalization is assumed.

| Complete Pass 3 | Two families, ascending widths | Four families, ascending widths | Source RHS |
|---|---|---|---:|
| sum-bits | 89/90, 89/90, 89/90 | 91/92, 90/93, 89/90 | 7,265 |
| dot-product | 173/173, 173/173, 173/173 | 188/196, 197/197, 195/197 | 6,704 |
| gemm-bias-relu | 207/204, 207/207, 207/207 | 209/208, 209/208, 207/208 | 15,462 |
| stable-argmax | 129/128, 129/128, 128/128 | 130/130, 130/129, 128/129 | 8,190 |

Entries count distinct neural child RHS, with seeds 1703/1709 separated by a slash. Keep the two compiler-projected nullary roots and all exact residual RHS separate. At two training families, dot-product stayed at 173 neural RHS at all three widths and both seeds. After broadening the families the 160k model reached 197/197; another 4× capacity produced 195/197. More weights alone do not address the dominant missing work outside this proof vocabulary. The exact obligations left by the most accurate arm remain in the timing. This is a single two-family subset and two seeds. Generalizing to arbitrary training corpus compositions would require more family splits.

Each measurement records clean resident complete-pass samples, separate synchronized GPU time for policy plus token formation, the number of candidate scores, source nonempty coverage, published neural winners, remaining exact RHS, verifier attempts, cost/size of training and per-training-family labels versus predictions. The workload table uses neural RHS; fit to the offline positive labels can differ from winning the actual source ordinal. [Raw per-arm results](results.json)

```sh
dir=benchmarks/pass3-cell-gpu/neural-capacity
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/capacity.py" "$e/repair-bake-families-20261120" "$e/recurrent-compositions-train-20261120" "$e/NEW-capacity-weights"
python "$dir/evaluate.py" "$e/repair-bake-families-20261120" "$e/pass3-atlas-integration-20261120" "$e/rotary-axes-20261119/packed-1703/final.pt" "$e/NEW-capacity-weights" "$e/NEW-capacity-results"
```
