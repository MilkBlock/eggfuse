# Version-local validation of named RipSat receipts

A release refers to a previously recorded physical FactRef **and** its version. For these consumer plans the row must still have exactly that version and be at least as recent as the consumer watermark. If the recorded version precedes the watermark, no possible current row can satisfy both checks. The native receiver can therefore safely skip a graph read independent of subsequent union/repair. A changed version or stale identity never supplies a new independent parent. Watermark equality is inclusive.

This study tests the actual Rust receiver on sum-bits and 3mm with the authenticated RipSat Let/Set chain. All source selection and future visibility follow the original schedule. It compares a full scan, an early version guard while scanning the original directory, and a per-consumer ordered map from published versions to named addresses. The index is populated at actual Let and Set publication. Gaps or changes on unselected addresses leave the ordinary actor responsible. The active range restores original address order before opening live facts. Partial mode is required, since discarding stale addresses can also discard a witness for completeness of the whole table. No new proof of whole-table closure is inferred. Counts of directory entries, row reads, postings and sorted items are in results.json; the secondary index adds storage.

| 3mm, direct Set matrix | Ordinary scan | Early guard | Version index |
|---|---:|---:|---:|
| Named addresses visited | 62,168 | 62,168 | 2,471 |
| Physical row reads | 14,817 | 2,161 | 2,161 |
| Receipt-opening + index maintenance ms | 6.391 | 2.067 | 1.426 |
| Whole inference ms | 1,640.68 | 1,632.08 | 1,619.44 |

Dedicated phase profiles charge the entire receipt-opening region plus index insertion. We sum both clocks in each replicate before taking its median. Separate unprofiled inference samples include the rest of the engine, with five interleaved samples per method after warmup. The sum-bits scoped medians are 0.101 / 0.073 / 0.077 ms.

## Factorial with a real higher Cell owner

A second binary includes the actual higher-order state/queue and the direct path. On a fresh reply the index registers the authorized version stored by the new specialized owner. The index never dereferences a retired owner's former cell. Active-range validation still checks live source fields/versions on every eligible terminal. This is an optional locality study; immutable FEPT numerators, denominators and the set of emitted/restored ordinals must match. Source checks include individual parent identity, root and nested physical IDs, original Run RHS, effective writes, Spine, union and final graph.

| 3mm method | Receipt row reads | Receipt-opening + index ms | Complete inference ms | Time to +264.11 MiB (ms) |
|---|---:|---:|---:|---:|
| Direct | 14,817 | 4.972 | 1,838.25 | 948.96 |
| Direct + index | 2,161 | 1.424 | 1,957.32 | 989.34 |
| Higher owner | 14,817 | 6.777 | 1,886.61 | 1,007.72 |
| Higher owner + index | 2,161 | 1.593 | 1,912.37 | 1,032.50 |

Four unprofiled inference samples and three dedicated timing samples per arm after warmup, on one machine. Fresh-process RSS uses the same independent CPU-calibrated increment from the other RipSat studies, three processes per arm. The analogous sum-bits +9.27 MiB crossing medians are 25.77 / 27.18 / 26.66 / 28.13 ms. In 3mm all arms preserve 932 actual terminal commits, 92,658 final-visible constructor origins and 555,913 forward packets. Both higher arms transfer 932 stable logical owners; sum-bits transfers 26. No new external parent is selected by the index. The work reduction is robust, but the scoped saving is small relative to the whole engine, and these timings do not establish a repeatable improvement in either whole inference or RSS rise time.

These receiver-opening times include some terminal owner validation. The independently measured request/response/owner component clocks are reported in the [higher Cell study](../ripsat-higher-cell/README.md); phase totals from separate builds must not be added.

```sh
python build.py "$EXP/new-receipt-index"
python study.py "$EXP" "$EXP/new-receipt-index/session" "$EXP/new-receipt-study"
python build_joint.py "$EXP/new-higher-index"
python combined.py "$EXP" "$EXP/new-higher-index/session" "$EXP/new-higher-index-study"
python rss.py "$EXP" "$EXP/new-higher-index/session" "$EXP/new-higher-index-study/joint.json" "$EXP/new-higher-index-rss"
python verify.py
```
