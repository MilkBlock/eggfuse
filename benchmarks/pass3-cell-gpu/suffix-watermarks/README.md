# Reading a freshness certificate before choosing the parents

A sealed multi-parent plan in the standalone Rust Cell CPU engine computed the greatest visible epoch of every remaining table by asking for its typed frame. Each consumer of this number in generation and in the exact suffix compares it, or its maximum with the prefix epoch, to this occurrence's seminaive watermark. Thus an interval containing any row at or above the watermark suffices. A complete unchanged version with all epochs below the watermark proves the opposite. A non-seminaive occurrence does not need these suffix epochs. Zero is a valid watermark.

The off control runs the shared single-parent headers and lazy arithmetic ports from the joint CPU study. The header arm consults the same published address/version bank when a typed frame is unavailable. The scalar arm retains only a table generation and its exact maximum, scanning source metadata on a miss. The optional whole-rule cut bypasses preparations when every source is old. The threshold arm stops reading earlier tables once a later relation meets the watermark. The proof arm stops looking through addresses at the first visible witness. The carry variant also revalidates a witness from another generation against current membership, dependency kind, visibility and epoch. A failed revalidation resumes the scan. Negative certificates are scoped to the exact table generation. The current scanner materializes the membership list, then walks it in reverse. Neither the witness nor the source maximum can supply a matching parent to the verifier.

Four interleaved, resident inference samples per arm follow a warmup at seed 1703. The two smaller programs also exercise reading a header without the whole-rule cut, the independent scalar cache, and disabling cross-generation carry. The raw signed proposal stream, source winners, physical allocations, ordered RHS and writes, Spine, union, source schedule and final graph agree on each program. Every consulted new table certificate that lacked a current typed frame was independently checked against visible decoded source rows in the detailed run. That audit cost is excluded from timing. Full results are in [small.json](small.json) and [large.json](large.json).

| Program | Vanilla | Joint CPU off | Header + cut | Threshold | Carry, ms | Cross-generation witnesses reused | Threshold table reads skipped |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.28 | 33.15 | 33.54 | 32.51 | 32.84 | 87 | 4,455 |
| conjugate-gradient | 352.50 | 648.47 | 658.34 | 652.83 | 653.11 | 168 | 12,340 |
| 3mm | 921.24 | 1,948.06 | 1,903.10 | 1,984.79 | 1,939.59 | 264 | 16,290 |
| Deriche | 1,552.28 | 3,536.42 | 3,557.04 | 3,573.74 | 3,569.16 | 314 | 18,033 |

On 3mm and Deriche the early cut short-circuited 114 and 97 source rule occurrences. The main source frame provider eventually decoded exactly the same number of changed rows as off, 113,418 and 170,925 respectively. Full rebuilds also read the same 29,379 and 39,488 visible rows. Looking only at the avoided freshness reads would overstate the physical benefit. The carry arm materialized 3,776,413 and 4,661,864 address entries to inspect 210,844 and 168,494 epochs. The four programs do not establish a consistent full-pass benefit.

```sh
d=benchmarks/pass3-cell-gpu/suffix-watermarks
python "$d/build.py" "$EXP/frontier-build"
python "$d/study.py" "$EXP" "$EXP/frontier-build/session" "$EXP/frontier-small" --cases sum-bits conjugate-gradient --arms headers headers-cut scalar-cut threshold proof carry
python "$d/study.py" "$EXP" "$EXP/frontier-build/session" "$EXP/frontier-large" --cases 3mm deriche --arms headers-cut threshold carry
python "$d/verify.py"
```
