# Frozen singleton dispatcher with wide pair-family packets

This native factorial compares the verified packed control, the donor-trained `reinforce-8` singleton dispatcher, the wide pair selector and their composition. The older left-row bucket action is disabled in every arm. The four configurations preserve the same original parent and child identities. The wide selector groups bounded left intervals, projected signatures and windows of right postings. Its emitted descriptors carry up to eight keys, and the receiver reconstructs addresses from its own public index. Its upper-bound combinations, receiver guards, sorting, private row offsets and exact suffix checks remain real work. Width two here means two independently proposed parent addresses. The full rule can contain additional function, primitive or point-bound suffix atoms.

The yield numerator counts constructor origins created under original verified firings that remain independently visible by the end of the workload. A fresh selected nested child receives its own birth credit. Remaining births belong to the actual immediate root literal or generating singleton/pair action. Every arm is checked against the independent source CPU's complete ordered RHS, writes, union and Spine schedule. The original physical roots, children, all raw multi-parent addresses, ordered slot and recurrent digests, original birth ledger, final visible fact identities and collision records must also agree.

The external forward denominator charges all singleton class actions, residual singleton literals, wide pair actions, true residual multi-parent literals and selected children. Feedback-inclusive yield also charges one return for each class action. The paid-group convention further charges absent or entirely stale sender prototypes. Finally, the all-prototype count charges every inspected pair prototype (including occupied ones), each emitted pair action, exact residual multi-parent proposals, learned singleton dispatch gates, accepted class actions, all per-row decisions on residual singleton calls, and all scored child decisions. We report this both with and without recurrent returns. Expanded receiver membership and joins are never treated as model outputs. Separate fields record sender marginal table rows, paid keys, receiver public decodes, cache reuses, upper candidate pairs, private verified pairs and each group's end-to-end productive count.

For the byte budget, singleton actions and returns use the fixed 64/20-byte layouts and pair actions use the actual 72-byte header plus four bytes per transmitted key. Unchanged external literals and selected children use the common declared framing from the joint actor ablation. This experimental transport boundary resides within one native process. Exact checked-source generation per Run and all receiver work are inside the inference and prepared-process wall timers.

## Full factorial

| Workload | Final-visible originals | Forward FEPT: packed / trained singleton / wide pair / joint | Native inference ms: packed / singleton / wide / joint | Prepared caller wall ms: packed → joint |
| --- | ---: | ---: | ---: | ---: |
| 3mm | 92,658 | 0.1660 / 0.4009 / 0.2105 / 0.8185 | 1,851.52 / 2,007.00 / 2,508.79 / 2,686.43 | 2,118.68 → 2,949.20 |
| deriche | 120,436 | 0.1229 / 0.3723 / 0.1435 / 0.6606 | 2,996.93 / 3,217.17 / 3,927.31 / 4,265.07 | 3,348.99 → 4,617.38 |
| sum-bits | 2,691 | 0.2125 / 0.3548 / 0.2862 / 0.6223 | 35.97 / 38.15 / 41.03 / 42.57 | 75.55 → 82.60 |

| Joint workload | Forward packets | With returns | Paid groups | All prototype decisions + returns | FEPT with returns / paid / all decisions + returns | Additional packets to eliminate for FEPT ≥ 2 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 3mm | 113,202 | 120,152 | 3,423,941 | 3,720,668 | 0.7712 / 0.0271 / 0.0249 | 66,873 |
| deriche | 182,318 | 191,749 | 6,120,704 | 6,551,924 | 0.6281 / 0.0197 / 0.0184 | 122,100 |
| sum-bits | 4,324 | 5,752 | 62,723 | 71,282 | 0.4678 / 0.0429 / 0.0378 | 2,979 |

| Joint workload | Sender prototype examinations | Wide actions | Candidates expanded by receiver | Internally materialized pair lanes | Remaining multi literals by number of independent parents | Forward FEPT ceiling under the matched-packing relaxation |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 3mm | 3,570,905 | 58,264 | 4,633,068 | 176,167 | 3 parents: 23,801, 4 parents: 3,180, 5 parents: 17,472, 6 parents: 32, 7 parents: 140, 8 parents: 180 | 0.8469 |
| deriche | 6,301,226 | 76,821 | 5,514,532 | 217,988 | 3 parents: 48,213, 4 parents: 4,664, 5 parents: 37,828, 6 parents: 63, 7 parents: 283, 8 parents: 238 | 0.6761 |
| sum-bits | 63,113 | 1,617 | 29,621 | 4,877 | 3 parents: 848, 4 parents: 38, 5 parents: 124, 6 parents: 1, 7 parents: 8, 8 parents: 16 | 0.6223 |

On 3mm, the receiver's 4,633,068 candidate combinations generated 176,167 pair lanes for the normal verifier. Of 58,264 wide actions, 31,247 generated no such lane. The joint workload retains 44,805 external higher-arity literals. Even a free representation of every wide action would leave 54,938 other choices, exceeding the 46,329 available at FEPT 2 by 8,609. On Deriche, the corresponding figures are 105,497 other choices and a budget of 60,218. Neither workload can break even by changing only the encoding of its wide packets. The relaxation preserves the currently matched candidate combinations and left intervals while allowing optimistic packing; it supplies no bound on a fundamentally different proof system.

The learned actor thus raises external forward FEPT on all three programs with unchanged physical and semantic endpoints. After prototype and recurrent costs the measured yield is much smaller. The joint arm also takes longer than both the control and each individual actor. Timing uses four rotated executions per arm after warmup; corruption of either typed source generation or pair extent is rejected before completion. [Complete counters, budgets, residue by arity and timing samples](results.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/wide-joint-build"
python3 study.py "$exp" "$exp/wide-joint-build/session" "$exp/wide-joint-study"
python3 verify.py
```

The checkpoint and feature layout are frozen before these workloads. The singleton dispatcher trained on sum-bits, dot-product and jacobi-1d. Deriche and 3mm are held out. The experiment excludes additional RSS profiling to preserve the benchmark queue for the requested full-source comparisons.
