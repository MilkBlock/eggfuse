# Direct compiled single-parent verification

Once the network has named one source pivot, the existing Cell query compiler can lower its determinate suffix to reads from anchor columns, previous step results or source literals. The experimental verifier reuses that compiler. It checks the real anchor table, arity, version, literals and repeated variables. The mutable graph is borrowed only for the original source rule view. It then computes each source point/primitive in order, verifies result predicates, tests the original seminaive watermark and constructs the actual source receipts. Nullary and unsupported entries retain the ordinary single verifier. The optional canonical-key arm sends eligible repaired non-set operands directly to the existing canonical lookup. During auditing it independently canonicalizes each such operand. The same upstream multi-parent prefix viability runs in every projected treatment.

Full native Pass 3 at seed 1703, six paired resident samples, ms. Ordered winners and actual Cell allocation identities agree with the independent original executor; no residual source search.

| Workload | Vanilla | Integrated | + forward | + compiled projection | + canonical lookup |
|---|---:|---:|---:|---:|---:|
| sum-bits | 21.47 | 33.49 | 32.55 | 32.53 | 32.54 |
| dot-product | 19.54 | 34.18 | 31.97 | 32.71 | 32.05 |
| jacobi-1d | 119.18 | 237.96 | 206.66 | 205.99 | 209.38 |
| conjugate-gradient | 345.31 | 958.29 | 760.74 | 753.89 | 762.14 |

On CG, 243,380 projected checks executed 317,344 exact point reads and 90,336 primitives. Both representations perform identical logical checks. This change did not establish a consistent end-to-end advantage.

```sh
python benchmarks/pass3-cell-gpu/projected-single-verifier/build.py "$EXP/projected"
python benchmarks/pass3-cell-gpu/projected-single-verifier/study.py "$EXP" "$EXP/projected/session" "$EXP/projected-results"
python benchmarks/pass3-cell-gpu/projected-single-verifier/verify.py
```
