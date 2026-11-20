# Compile the complete deterministic suffix of a multi-parent Cell block

The independent neural parents are fixed before any exact check. The Rust compiler lowers the remaining plan to reads from a parent role/column, a preceding operation result, or a source literal. Each step either performs a complete-key table read or invokes the source primitive. It checks any required result equality and advances the original seminaive watermark. A table result must have the original visible physical row, declared table, arity and bound key fields. The executable projects the full source slot map and all witness coordinates only for completed bindings. It uses the ordinary ticket, root recipe and original ordered RHS.

A further static condition permits direct result-port reuse: every dynamic key field of a point lookup must come from a single previously chosen independent parent. In that case the source atom, the physical parent and its visible version determine the entire key within the immutable page. Repeated recipients can reuse the function result or certified absence without rebuilding the key. They still check their own output predicates. Earlier derived results and keys mixing different parents cannot use the parent-only shortcut. The independent full-key cache is tested separately with the same 4,096-entry limit.

The same binary compares the stock issuer, prepared parent projections with the recursive source suffix, compiled registers, registers with key sharing, and registers with parent result-port sharing. The original recursive path also computes signed latent ports on intermediate suffix results under the sealed stack mode. The register executor ends generation before running its suffix, and does not need that unused computation. Thus any time difference between the two complete paths includes both changed binding assembly and omitted latent calculations. Ordered winners, each raw signed stream, actual physical root/child IDs, union, effective writes, Spine, schedule and final graph agree across arms. These are four rotated resident measurements at seed 1703 and a separate default EggFuse CPU control.

| Program | Vanilla | Stock | Prepared parents | Registers | Registers + key | Registers + parent port, ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.88 | 33.90 | 33.47 | 33.97 | 33.40 | 34.75 |
| conjugate-gradient | 360.90 | 648.35 | 640.01 | 636.04 | 661.06 | 677.06 |
| 3mm | 923.99 | 1,974.88 | 1,987.72 | 1,952.33 | 2,016.62 | 1,962.73 |

| Program | Verified parent sets | Bindings completed | Missing keys | Scalar/result guard failures | Stale | Skipped point requests via one parent |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 5,912 | 4,588 | 501 | 766 | 57 | 139 |
| conjugate-gradient | 83,117 | 57,695 | 14,802 | 6,828 | 3,792 | 4,600 |
| 3mm | 220,268 | 146,965 | 41,853 | 17,806 | 13,644 | 7,300 |

On 3mm, 220,268 checked parent sets yielded 146,965 source bindings. The returned key/guard and watermark partitions account for every other parent set. The parent-only cache saved 7,300 of 104,197 source point requests. Index construction and lookup are still paid online. The measurements do not show a uniform advantage from enabling this cache. [Per-source activity and timings](results.json)

```sh
d=benchmarks/pass3-cell-gpu/batched-cell-verifier
python "$d/build.py" "$EXP/verifier-blocks"
python "$d/study.py" "$EXP" "$EXP/verifier-blocks/session" "$EXP/verifier-block-results"
python "$d/verify.py"
```
