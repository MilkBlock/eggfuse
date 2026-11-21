# Store pending singleton proposals in a shared page

The original whole-Run issuer queues a full token, the rule's feature array and a send flag for every surviving singleton. Each token already owns a handle to its sealed recipe page before the suffix checker knows whether the binding exists. This native path preserves the full neural decision stream and changes what the executor keeps while other rules finish issuing their pages.

The compact row holds the original source address, its version, the pre-pruning neural serial (also used by merge children), score and initial-source bit. It occupies 40 bytes on this build. The expanded tuple occupies 112 bytes. Both arms construct the actual typed receipt pages at the original issuance point. The compact queue retains one page handle per shard. On successful suffix verification the actual page and lane are attached to the root binding, preserving the raw wire stream and the original physical parent. The validator reads the same candidates with the same semantics even when a staged claim is denied. All extra per-row data is kept long enough for the original winner and Run audit.

Four interleaved complete inference samples after warmup. Fields headed MB measure decimal megabytes of vector capacity, summed over issuance or at maximum simultaneously pending capacity. They exclude the page payload shared with the checker, staging slabs, the temporary insertion batch, allocator metadata and graph state. Separate RSS measurements charge the entire native process.

| Real program | Peak pending B, expanded → compact | Cumulative pending MB, expanded → compact | Inference ms, expanded → compact |
|---|---:|---:|---:|
| sum-bits | 60,480 → 25,952 | 1.40 → 0.70 | 32.90 → 33.64 |
| dot-product | 75,264 → 30,336 | 1.43 → 0.67 | 30.89 → 31.26 |
| conjugate-gradient | 883,456 → 319,232 | 39.03 → 14.62 | 592.56 → 595.90 |
| 3mm | 1,877,568 → 674,272 | 135.92 → 49.61 | 1,802.32 → 1,822.89 |
| Deriche | 1,880,256 → 675,488 | 372.19 → 134.31 | 3,525.62 → 3,413.53 |

The issuer emitted 243,383 pending singleton lanes on CG and 845,168 on 3mm; 73,676 and 147,952, respectively, actually reached successful binding and required individual page references. Deriche is the only program with a lower four-sample inference median in this no-staging comparison, with four paired wins. On CG/3mm, additionally prebuilding group-authorized Cell headers yielded 658.39/1,870.37 ms expanded and 651.30/1,872.85 compact. The two queues use identical grants, actual redemptions and payloads when prebuilding is enabled. No per-Run byte or timing comparison uses the sum of independent gains.

Whole-process peak RSS (three fresh measured processes per layout) went from 463.02 to 464.86 MiB on CG and 745.03 to 745.95 MiB on 3mm with staging off. With staging on these pairs were 462.22 to 461.95 and 749.39 to 749.84 MiB. Queue capacity savings were visible inside the executor; these process measurements do not establish a peak RSS reduction.

Offline verification includes original/foreign/withheld/stale/duplicate reservation controls, individual stable parents, child IDs, every raw neural decision, full ordered source RHS, writes, unions, Spine and final graph. A smaller pending vector measures a change in the executor's representation of speculative work. It does not establish compression of the final e-graph.

```sh
python build.py "$EXP/new-packed-build"
native="$EXP/new-packed-build/session"
python study.py "$EXP" "$native" "$EXP/new-packed-heldout" --staged
python study.py "$EXP" "$native" "$EXP/new-packed-transfer" --cases sum-bits dot-product deriche
python peak.py "$EXP" "$native" "$EXP/new-packed-heldout/results.json" "$EXP/new-packed-rss"
python controls.py "$EXP" "$native" "$EXP/new-packed-controls"
python verify.py
```
