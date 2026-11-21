# Forecasting demand from a sealed proposal wave

Each training sample is one rule in a scheduled Run. The inputs are an intercept, log previous offers, log previous verified wins, log previous fresh allocations, previous fresh/offer ratio, log query atom count, log RHS instruction count, and log currently offered lanes. All logs use log1p. The seven prior/static coordinates come unchanged from the existing Run capture. The sealed count replaces the eighth coordinate, which was zero in the entry-time capture. The training target is the number of fresh allocations assigned to this rule later by the original commit order. It is only used as a label.

The training corpus consists of sum-bits, dot-product and jacobi-1d from the original frozen donor capture. Of 180,455 rule × Run events, 9,637 have at least one proposal. The donor histogram preserves each event's multiplicity. Each of the three independent heads has eight double-precision weights, including the intercept. Balanced and coverage minimize count-space pinball loss at 0.5 and 0.8 using a bounded expm1 link. Fraction fits a binomial log-loss with one trial per offered lane. Each deployed forecast is rounded half-up and bounded by offered lanes and the per-Run cap. The allocator subsequently shares that cap across rules.

| Head | Donor grants requested | Overlap with 43,618 fresh allocations | Unneeded grants | Missed fresh allocations |
| --- | ---: | ---: | ---: | ---: |
| Balanced | 40,032 | 29,951 | 10,081 | 13,667 |
| Coverage | 69,576 | 41,023 | 28,553 | 2,595 |
| Fraction | 43,398 | 30,020 | 13,378 | 13,598 |

Overlap sums the minimum of the forecast and label for each rule × Run event before the shared budget, authenticated allocation and any cross-rule reuse. These donor-fit statistics do not measure held-out physical publication or native performance. The corpus records completed whole-Run counts. A native deployment encountering multiple waves can only observe offers available at the first issue boundary; its timing and publication checks must measure that case separately.

Reproduce with CPU PyTorch using `python train.py`, then `python check_training.py` from this directory. The checker compares the fitted objectives, autograd and central differences, scalar Rust-style forecasts and all archived donor totals.
