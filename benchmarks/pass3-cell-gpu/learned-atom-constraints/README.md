# Attribute and eliminate false multi-parent proposals

For each frozen candidate page, an audit classifies the first parent constraint rejected by the authoritative checker: a literal, a repeated variable in the same atom, a mismatch across separate parents, or a missing/wrong row header. For across-parent mismatches it separately records whether the original 16-bit feature word was identical or the trained projection mapped different words to the same ten-bit signature. Only the first failure is counted. Source validation still sees full exact typed rows.

The compiler can test a known literal or repeated column using the same learned projection while the parent is being selected. A collision leaves the parent for verification. The cached variant records the pass/fail bit for this exact row on this immutable rule occurrence. The additional independent view uses a different input salt with the same trained projection, adding zero learned coefficients. Every variant keeps the original source scheduler, trained single-parent frontier, root/merge-child allocator and two-column forward feasibility. These are resident whole-program measurements in the standalone Rust Cell CPU runtime, six interleaved samples after warm-up at seed 1703.

| Program | One view / two views (ms) | One / two views, sealed tuples | Two views + cached local test, tuples / ms | Vanilla (ms) |
|---|---:|---:|---:|---:|
| sum-bits | 34.83 / 33.97 | 9,384 / 8,262 | 7,970 / 33.97 | 22.01 |
| dot-product | 31.20 / 31.29 | 9,955 / 8,845 | 8,664 / 32.59 | 19.12 |
| jacobi-1d | 191.55 / 185.34 | 84,705 / 51,372 | 50,140 / 188.61 | 110.12 |
| conjugate-gradient | 769.00 / 683.79 | 531,346 / 130,413 | 127,051 / 700.63 | 345.10 |

On conjugate-gradient, 353,391 one-view candidates failed a cross-parent equality, 50,991 failed a literal and 109 failed the remaining local or header checks. Two views reduced failed cross-parent equalities to 196. With three views and cached local checks all 126,855 sealed tuples passed the parent checks. Only 57,695 multi-parent RHS actually committed; exact suffix requirements and source ownership still matter. Local checks improve candidate quality but did not uniformly improve wall time.

```sh
python benchmarks/pass3-cell-gpu/learned-atom-constraints/build.py "$EXP/atoms"
python benchmarks/pass3-cell-gpu/learned-atom-constraints/study.py "$EXP" "$EXP/atoms/session" "$EXP/atom-results"
python benchmarks/pass3-cell-gpu/learned-atom-constraints/verify.py
```
