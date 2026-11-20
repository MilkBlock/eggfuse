# Train only the extra port bits on actual failed bindings

The original tied Q/K projection and both baseline CPU policies stay fixed. During four training programs we collect only the first failing source constraint in an already issued parent tuple. Two unequal typed values form one negative example; we retain two salted 16-bit feature words and the observed frequency. The corpus contains 4,056 failures and 258 distinct pairs. It contains no source rows, labels or costs from any of the four evaluation programs. The regularizer also uses independent uniform synthetic words. Equal inputs pass by construction because the added query and key projections share identical parameters.

The new bipolar linear head, trained offline in PyTorch, emits two, four or eight additional bits (32, 64 or 128 coefficients). The original CPU scoring function compiles all feature words into a 262,216-byte table per checkpoint. Unused bits are zero. At runtime the original first view still operates, the secondary view refines its learned parent bucket, and full Rust verification charges all reads and ordered source mutations. One random two-bit initialization, a uniformly trained two-bit head and the original ten-bit weights reused at the new input salt are explicit controls. The initial embedding, source budget and verifier are identical across the capacity arms.

| Refinement | Remaining collisions among 4,056 training occurrences |
|---|---:|
| Random, two bits | 1,069 |
| Uniform synthetic training, two bits | 500 |
| Source failures + synthetic, two bits | 92 |
| Source failures + synthetic, four bits | 1 |
| Source failures + synthetic, eight bits | 0 |

Freezing these heads and running new real Rust Pass 3 programs gives the following complete inference medians (ms); the driver interleaves six samples after warm-up, seed 1703. Coverage, signatures of the winning source parents, schedule, union and final graph are checked independently. The original validator decides every accepted binding.

| Workload | Vanilla | One view | Random +2 | Uniform +2 | Hard +2 | Hard +4 | Hard +8 | Reuse original +10 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.36 | 33.80 | 34.21 | 35.48 | 34.48 | 34.24 | 34.61 | 34.42 |
| dot-product | 19.02 | 32.22 | 33.23 | 33.17 | 32.93 | 31.60 | 31.97 | 32.57 |
| jacobi-1d | 114.66 | 204.39 | 200.30 | 194.53 | 197.78 | 195.16 | 204.45 | 202.65 |
| conjugate-gradient | 354.25 | 777.74 | 739.29 | 735.04 | 724.62 | 696.54 | 708.26 | 700.61 |

On conjugate-gradient the hard two-bit head issued 179,337 tuples and the hard four-bit head issued 140,017, versus 480,246 without the refinement. Eight bits removed every observed training collision but took longer on this independent large program than four bits. Reusing the existing ten bits requires zero additional trained coefficients. The experiment does not establish a universal preferred width.

```sh
python benchmarks/pass3-cell-gpu/collision-trained-ports/build.py "$EXP/collision"
python benchmarks/pass3-cell-gpu/collision-trained-ports/train.py "$EXP" "$EXP/collision" "$EXP/collision-heads"
python benchmarks/pass3-cell-gpu/collision-trained-ports/study.py "$EXP" "$EXP/collision" "$EXP/collision-heads" "$EXP/collision-results"
python benchmarks/pass3-cell-gpu/collision-trained-ports/verify.py
```
