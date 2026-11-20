# Charge each learned signature view where it is consumed

For a tied two- or three-view signature, the primary ten bits suffice for most existing maximum-epoch and local consistency directories. The primary-only arm avoids computing extra salted projections at such reads. A second treatment keeps all active bit signatures in one u32 per row of a chosen, immutable source column; stage checks and publications can reuse the word. A separate control widens forward feasibility from the first signature to the full view(s) of each projected column. Two columns and three views fit in a checked u64. This separates the benefit of computing fewer bits from the value of retaining more information in the suffix proof.

The base proposer has two-column forward feasibility, cached within-atom learned literal/equality checks, and the integrated CPU backend. The one-view arm provides a capacity control. All eight neural arms and the default CPU use the complete native Pass 3 source ordering. Each arm has six rotated timed repeats following warm-up, seed 1703. Every raw tuple remains identical when only the computation/storage of a view changes. Wider evidence can safely reduce raw proposals, with independent audits of all winners and actual Cell allocations.

| Case | Vanilla | One view | Two views | Primary only + packed columns | Plus two-view suffix evidence |
|---|---:|---:|---:|---:|---:|
| sum-bits | 22.15 | 33.87 | 33.77 | 33.14 | 33.33 |
| dot-product | 19.14 | 31.60 | 31.50 | 30.98 | 31.64 |
| jacobi-1d | 114.76 | 205.60 | 197.57 | 192.44 | 196.80 |
| conjugate-gradient | 365.51 | 808.94 | 738.67 | 694.25 | 725.76 |

On conjugate-gradient, packing and specializing the same two-view projection reduces full inference to about 694 ms. Extending its evidence directory to both views saves 384 additional tuples but takes longer. This comparison does not include training or graph export in the inference timer.

```sh
python benchmarks/pass3-cell-gpu/tiered-port-projections/build.py "$EXP/tiered"
python benchmarks/pass3-cell-gpu/tiered-port-projections/study.py "$EXP" "$EXP/tiered/session" "$EXP/tiered-results"
python benchmarks/pass3-cell-gpu/tiered-port-projections/verify.py
```
