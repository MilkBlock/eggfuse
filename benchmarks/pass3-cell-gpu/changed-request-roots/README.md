# Drive connected requests from changes to their ports

The front end already proves a three-atom route in which a source Cell supplies the complete key of a function. The function result feeds a learned projection that proposes the final independent parent. This experiment activates the same native Rust recipe by its seminaive watermark. If the remaining source suffix is old, a legal new tuple must have a fresh root, function row or target. Fresh roots retain their original issuing path. Fresh function keys select possible old roots through a learned input-signature directory. Fresh target values select possible function rows by their learned output signatures, then activate root subscribers of those keys. The rule's complete-key comparison disambiguates collisions. The source address and version still pass through the ordinary sealed page and source verifier in original order.

The point control uses reverse activation only when the target is old. The target arm includes fresh target buckets. The receipt arm passes the function's current physical address to the issuer after checking the complete key; the detailed native run independently looks up each transferred address. The presence arm additionally reverses from all visible function keys when any suffix can be fresh and the function is smaller than the root. Large or dense cohorts retain the direct learned provider. Each cached directory is bound to source table, column, table generation and union generation. Retained directory size is bounded by row count, and an individual table larger than 32,768 rows uses the original route. The compiler does not assign credit for selecting the deterministic function address to the neural proposer.

Four source Pass 3 workloads used seed 1703, four paired rotated timing samples after warmup, complete generation and the same two learned views. The exact CPU source controls ordered RHS, effective writes, union, Spine, schedule and final graph. All four reverse treatments preserve the connected provider's entire raw stream and all winning parent and physical allocation identities. The ordinary composed issuer has its own raw stream.

| Source | Vanilla | Original joint CPU | Direct request | Reverse fresh target | Plus receipt | Plus presence, ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.06 | 34.45 | 34.82 | 34.87 | 33.49 | 33.20 |
| conjugate-gradient | 342.00 | 632.40 | 652.26 | 641.93 | 647.98 | 647.85 |
| 3mm | 906.45 | 1,962.98 | 1,991.17 | 1,999.52 | 1,939.86 | 2,001.95 |
| Deriche | 1,611.05 | 3,578.91 | 3,683.63 | 3,442.61 | 3,616.80 | 3,555.10 |

| Source | Roots visited, direct → receipt | Native function requests, direct → receipt | Transferred function receipts | Rows processed building subscription indexes |
|---|---:|---:|---:|---:|
| sum-bits | 12,417 → 916 | 12,090 → 478 | 378 | 10,162 |
| conjugate-gradient | 188,090 → 6,978 | 182,687 → 4,056 | 2,922 | 161,348 |
| 3mm | 629,433 → 18,925 | 613,362 → 10,510 | 8,415 | 551,695 |
| Deriche | 1,118,651 → 42,773 | 1,106,732 → 15,100 | 27,673 | 961,779 |

These are counts on eligible request programs. The table-generation cost of constructing the lookup directories explains why the much smaller root domain yields mixed full-pass medians. [Small and medium workload measurements](core.json) · [Larger measurements](large.json)

```sh
d=benchmarks/pass3-cell-gpu/changed-request-roots
python "$d/build.py" "$EXP/wake-build"
python "$d/study.py" "$EXP" "$EXP/wake-build/session" "$EXP/wake-core"
python "$d/study.py" "$EXP" "$EXP/wake-build/session" "$EXP/wake-large" --cases 3mm deriche --arms target receipt presence
python "$d/verify.py"
```
