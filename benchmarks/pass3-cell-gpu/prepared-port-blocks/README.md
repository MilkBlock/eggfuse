# Compile the column projections for a sealed multi-parent block

At entry to a rule, bind the primary learned bucket index once per stage and, separately, cache the frozen code of each published or compared column in immutable source order. A column stores two bytes per source row. The current compact representation is legal only for one tied learned Q/K projection at Hamming radius zero. Table and union generation stamp each array. The optional index and projection treatments execute on top of two-column prefix feasibility. No code is an authoritative fact or a replacement for the original source receipt.

| Case | Original / primary index / columns / both (ms) | Vanilla (ms) |
|---|---:|---:|
| sum-bits | 33.01 / 32.78 / 32.72 / 32.67 | 21.33 |
| dot-product | 30.33 / 30.58 / 29.79 / 29.74 | 18.13 |
| jacobi-1d | 196.37 / 191.81 / 190.82 / 187.57 | 115.01 |
| conjugate-gradient | 803.01 / 785.64 / 780.70 / 783.01 | 369.89 |

At seed 1703 on conjugate-gradient, the combined arm served 3,961,255 column values and prepared 1,500,015 during table generations. The maximum retained payload of these compact columns was 78,892 bytes. Full reachable-state, source schedule, ordered receipts and resolved physical Cell IDs are identical; the standalone experiment clock measures complete resident inference. These samples have their own paired baseline. Other learned-branch controls remain in their original experiment directories.

```sh
python benchmarks/pass3-cell-gpu/prepared-port-blocks/build.py "$EXP/prepared"
python benchmarks/pass3-cell-gpu/prepared-port-blocks/study.py "$EXP" "$EXP/prepared/session" "$EXP/prepared-results"
python benchmarks/pass3-cell-gpu/prepared-port-blocks/verify.py
```
