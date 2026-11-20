# Charge ordering of the verified binding batch

The exact source commit sorts each rule's matches by its input slot values and retains the first instance at a duplicate key. A new experiment verifies a shared physical slot layout for every row of the current batch, then compares its fields directly. The optional varying-column arm excludes columns proved equal across every row of that batch. The ordinal arm sorts indexes before permuting original bindings; ties are broken by original input order. A numeric-prefix treatment packs up to two leading integer/e-class fields before the remaining exact comparisons. Signed i64 order is preserved by a sign-bit flip. Mixed or nonnumeric columns use the original Value ordering. Incompatible layouts always go to the original canonical source path. No approximate sort or hash determines a winner.

An independent instrumented execution times only the complete dedup/order call (including validation and movement). The main interleaved measurements disable that clock. Each treatment had identical model-emitted raw tickets, selected parent tuple/child, effective writes, ordered RHS, union, Spine and physical Cell IDs on the full six workloads. Seed 1703, six samples on the first four and four samples on the two additional transfers.

| Program | Vanilla | Original / direct / varying / ordinal + numeric prefix (ms) | Time in original ordering → numeric prefix in separate diagnostic (ms) |
|---|---:|---:|---:|
| sum-bits | 21.77 | 33.83 / 33.56 / 33.76 / 33.87 | 0.67 → 0.76 |
| dot-product | 18.51 | 31.02 / 30.95 / 32.18 / 31.31 | 0.54 → 0.64 |
| jacobi-1d | 108.83 | 186.33 / 185.48 / 178.59 / 183.81 | 3.87 → 3.51 |
| conjugate-gradient | 358.70 | 691.07 / 681.32 / 709.09 / 694.24 | 13.72 → 11.00 |
| 3mm | 936.02 | 2070.52 / 2130.68 / 2071.29 / 2080.62 | 35.06 → 26.21 |
| deriche | 1550.99 | 3742.20 / 3705.31 / 3748.04 / 3766.54 | 79.22 → 54.73 |

The sort is a small fraction of total inference, and the shorter measured comparison path did not yield a consistent end-to-end win across all workloads. This study retains the source's stable tie choice, including when multiple physical proofs encode the same input tuple.

```sh
python benchmarks/pass3-cell-gpu/binding-order/build.py "$EXP/order"
python benchmarks/pass3-cell-gpu/binding-order/study.py "$EXP" "$EXP/order/session" "$EXP/order-core"
python benchmarks/pass3-cell-gpu/binding-order/study.py "$EXP" "$EXP/order/session" "$EXP/order-large" --cases 3mm deriche --arms source direct varying prefix --repeats 4
python benchmarks/pass3-cell-gpu/binding-order/verify.py
```
