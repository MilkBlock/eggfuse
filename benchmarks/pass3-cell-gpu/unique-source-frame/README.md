# Apply source changes to a uniquely held multi-parent row frame

These are the immutable full Row snapshots used to produce multi-parent tokens; single-parent headers are an independent representation. The existing decoder merges sorted changed addresses with the previous sorted snapshot and clones unaffected rows. The move arm takes ownership of a prior frame only when there are no other strong or weak readers, moves untouched rows and builds a replacement vector in source order. The edit arm replaces changed rows or appends in place when the upper bound on interior shifts is small. For an expensive shape change it retains the linear move merge. The last maximum visible epoch is recomputed if it might have decreased. All fallible new row reads occur before taking the previous authoritative snapshot.

The control retains an actual second Rc while updating; exclusive mutation is then unavailable. Independent audit compares every edited frame to original source enumeration, including visible row, key fields, address, order and maximum epoch. The full pass additionally checks exactly the same raw neural tuples, root tickets, winning binding order, physical new Cells and source effects. Complete resident inference includes frame maintenance.

| Program | Vanilla | Original | Move | In-place (ms) | Rows retained without Rc field clones | Updates handled in place / eligible updates |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.75 | 35.45 | 35.23 | 33.95 | 53,936 | 694 / 772 |
| dot-product | 18.32 | 30.92 | 30.78 | 30.67 | 53,365 | 564 / 617 |
| jacobi-1d | 109.65 | 191.99 | 191.74 | 183.50 | 417,647 | 901 / 1,069 |
| conjugate-gradient | 344.79 | 678.45 | 665.44 | 671.33 | 1,351,474 | 1,209 / 1,387 |
| 3mm | 911.73 | 2106.69 | 2065.61 | 2131.51 | 4,722,498 | 1,863 / 2,175 |
| deriche | 1604.28 | 3889.86 | 3891.87 | 3862.85 | 6,445,245 | 2,243 / 2,611 |

These copy counts are operations within the frame update, not changes to the number of physical e-graph Cells. End-to-end differences on the two largest inputs were small or mixed. The six initial/transfer experiments are paired independently at seed 1703.

```sh
python benchmarks/pass3-cell-gpu/unique-source-frame/build.py "$EXP/frame"
python benchmarks/pass3-cell-gpu/unique-source-frame/study.py "$EXP" "$EXP/frame/session" "$EXP/frame-study"
python benchmarks/pass3-cell-gpu/unique-source-frame/study.py "$EXP" "$EXP/frame/session" "$EXP/frame-big" --cases 3mm deriche --arms move edit --repeats 4
python benchmarks/pass3-cell-gpu/unique-source-frame/verify.py
```
