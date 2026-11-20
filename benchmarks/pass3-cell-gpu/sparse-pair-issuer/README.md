# Demand-restricted generation for asymmetric fresh pair inputs

The ordinary pair issuer may prepare a full right signature index, both projected columns and two epoch orderings even when only a small fresh cohort can produce any new tuple. This experiment considers a seminaive pair with two independent source parents, zero learned radius, an older suffix and a right table at least as large as the left. It never generates rows for the verifier. It changes which learned buckets are constructed.

The epoch control bypasses both epoch sorts when a delta-only traversal cannot apply. If all left rows are old, the narrow treatment encodes only right rows at/after the watermark. In the mixed treatment, old right rows are also retained when their code is actually requested by one of the fresh left rows. Multiple shared slots use a compound learned key, including both views. Posting lists preserve original physical order, and source effects still execute at the original commit point. The arithmetic-derived-port family uses its separate compiled plan.

The six-program study uses frozen seed 1703 and an independent exact-source executable. The timings rotate full resident inferences. A separate same-binary replay on the identical configuration verifies all active branch counters and the raw proposal digests against the timed study's audited arms. Its inputs and timing-file checksums are retained in capture.json. This replay was necessary because the first harness stored the shared equation counters without invoking the sparse observer callback. Exact source and physical winner comparisons did run in the first pass.

| Case | Vanilla | Original | Skip unused epoch sorts | Old-left / mixed sparse preparation (ms) | Mixed visits / encoded right rows |
|---|---:|---:|---:|---:|---:|
| sum-bits | 21.43 | 34.39 | 34.84 | 33.80 / 34.53 | 112,481 / 26,092 |
| dot-product | 19.33 | 31.46 | 31.29 | 31.06 / 31.87 | 86,915 / 19,185 |
| jacobi-1d | 113.43 | 185.04 | 185.10 | 194.22 / 192.01 | 1,012,931 / 208,290 |
| conjugate-gradient | 351.42 | 672.60 | 674.22 | 670.74 / 668.45 | 5,698,870 / 977,690 |
| 3mm | 924.43 | 2138.52 | 2106.03 | 2072.48 / 2062.12 | 17,520,600 / 2,311,851 |
| deriche | 1577.82 | 3773.47 | 3760.18 | 3788.05 / 3781.84 | 15,691,974 / 3,049,714 |

The raw learned stream and fresh physical allocation IDs remain exactly aligned. On 3mm the mixed strategy reduced elapsed inference modestly; Deriche did not benefit consistently. A smaller set of projected codes still requires inspecting source epochs and constructing ordered buckets.

```sh
python benchmarks/pass3-cell-gpu/sparse-pair-issuer/build.py "$EXP/sparse-pairs"
python benchmarks/pass3-cell-gpu/sparse-pair-issuer/study.py "$EXP" "$EXP/sparse-pairs/session" "$EXP/sparse-study"
python benchmarks/pass3-cell-gpu/sparse-pair-issuer/study.py "$EXP" "$EXP/sparse-pairs/session" "$EXP/sparse-large" --cases 3mm deriche --arms epochs narrow mixed --repeats 4
python benchmarks/pass3-cell-gpu/sparse-pair-issuer/verify.py
```
