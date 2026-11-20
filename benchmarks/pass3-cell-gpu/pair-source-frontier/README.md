# Compile a deterministic scalar suffix into a learned join port

In the frozen 3mm baseline, two-parent rules accounted for 433,057 of 477,862 complete multi-parent receipts and 366.7 ms of the profiled issuance interval. The same profile on Deriche found 483,127 of 574,416 receipts and 482.6 ms. The original rule profiles time both planning and issuance; per-rule medians are descriptive. [Per-rule source measurements](profile.json)

The compiler examines each sealed plan with exactly two independent parents. It looks for a binary i64 primitive whose operands can already be read from columns of one parent or literals, and whose output is an existing slot in the other parent. It can orient this test in either direction. It currently picks the first such primitive, supporting the native checked integer add, subtract, multiply, divide, remainder, min and max operations. A failed or missing type proof retains ordinary evaluation. The rule number and workload name are absent from extraction and admission.

In the actual eggcc Pass 3 rule universe one plan qualified. Rule 144 derives a combined SubTuple from two pieces. Their Expr ports must match and the second start must equal the first start plus its length. The runtime computes a trained port signature for that derived scalar. Two equal values yield the same tied signature. A mismatch safely rules out this pair without supplying a new physical address. A signature match still goes to the original exact verifier, including the Concat lookup, seminaive eligibility and ordered RHS. The first arm recomputes source columns, the second shares them at identical source/union generations, and the third indexes the original join signature plus the derived one. Dropping the optional proof on the anchor controls reproduces the entire unfiltered raw stream.

The paired rows below use frozen seed 1703, the current integrated CPU executor, two-view learned ports and original CPU schedule. Each case independently checks actual winning parents, ordered RHS, writes, Spine, union, final graph and freshly allocated Cell IDs. The two large transfers have four timed repeats and the others have six, excluding audit and export.

| Workload | Vanilla | Original | Cached arithmetic port | Compound index (ms) | Raw tuples, original → cached |
|---|---:|---:|---:|---:|---:|
| sum-bits | 20.71 | 32.83 | 32.40 | 33.92 | 7,970 → 5,912 |
| dot-product | 19.31 | 32.15 | 32.07 | 32.20 | 8,664 → 7,207 |
| jacobi-1d | 112.17 | 191.37 | 190.84 | 188.32 | 50,140 → 33,250 |
| conjugate-gradient | 361.24 | 712.53 | 672.44 | 702.51 | 127,051 → 83,313 |
| 3mm | 936.91 | 2090.02 | 2024.65 | 2116.66 | 477,862 → 220,972 |
| deriche | 1586.47 | 3847.03 | 3827.85 | 3801.34 | 574,416 → 309,277 |

Fewer complete tuples do not necessarily imply lower total CPU cost. The compound index costs more on 3mm than the cached filter despite issuing exactly the same receipts. The number of predicate comparisons rejected can exceed the number of removed raw tuples because other necessary conditions could also have removed a rejected pair. Only the difference in complete issued tuples is credited as a saved certificate.

```sh
python benchmarks/pass3-cell-gpu/pair-source-frontier/build.py "$EXP/pair-equations"
python benchmarks/pass3-cell-gpu/pair-source-frontier/study.py "$EXP" "$EXP/pair-equations/session" "$EXP/arithmetic-study"
python benchmarks/pass3-cell-gpu/pair-source-frontier/study.py "$EXP" "$EXP/pair-equations/session" "$EXP/arithmetic-transfer" --cases 3mm deriche --arms cached indexed --repeats 4
python benchmarks/pass3-cell-gpu/pair-source-frontier/verify.py
```
