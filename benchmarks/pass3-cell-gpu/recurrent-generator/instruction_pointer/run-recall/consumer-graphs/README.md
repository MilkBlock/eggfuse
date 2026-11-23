# Training one graph action across observed Cell layouts

Sum-bits and dot-product supply both training tapes. Fact, loopfact and sum-divisors are development holdouts reused in earlier studies. Each template specifies ordered rule occurrences, Run groups, independent boundary slots and actual returned instruction ports. The same message passing weights, completion scorer and boundary pointer handle every size. The frozen root Actor supplies the initial named request. This study keeps the historical one-wave, top-32 root policy for comparison with the first unified graph deployment.

Bake now follows outgoing consumer edges as well as incoming producer edges. Two consumers may use different results of the same producer without either consumer appearing in the other's ancestry. Starting from each root, the additional walk adds connected consumers in source order while their external inputs are already visible at the root and their internal returns and scheduled groups agree with the trace. Intermediate graphs also enter the joint corpus. The extraction limit was ten rule occurrences. The greedy walk samples connected subgraphs and the evidence covers their observed executions. It does not certify local saturation under every applicable rewrite.

| Training evidence | Previous bounded ancestor catalog | All observed ancestors | All observed plus consumer growth |
|---|---:|---:|---:|
| Distinct catalog layouts including iterative joins | 4,096 | 49,382 | 54,156 |
| Layouts observed ready at a training root | 3,044 | 3,044 | 7,828 |
| Layouts with at least one observed positive in the loss | 3,552 | 43,230 | 47,428 |
| Layouts excluded from gradient updates by hash | 534 | 6,142 | 6,719 |

The two new scorers each trained on Metal for one full shuffled epoch. The previous scorer trained for two. Growing consumers produced 164,183 labeled root/layout pairs. Only 2,088 distinct step vectors and 9,539 edge vectors were needed to construct the new catalog's graph batches. On the saved 4,096 templates the new encoder reproduced every frozen CPU graph vector exactly. The held template split allows shared component rules. The corpus includes observations which fail root readiness, and missing observations supply weak negative labels.

## Native execution

One CPU inference thread issued named certificates. Rust verified every independent input without searching inside the certificate. In assist, the separate residual engine filled missing source commits. Across all three programs the source schedule, ordered RHS, writes, resumes, events, final graph and effective operation ledger matched the native reference. Five-program teacher replay verified 7,866 distinct layouts with at least one complete instance. The corrupted final-parent version controls all failed. The saved sum-bits semantic contract passed separately. Comparing both end-to-end configurations includes changes to the learned scorer, pointer and catalog.

| Assist workload | Distinct signed commits, previous → new | Reference commits | Complete graph instances, previous → new |
|---|---:|---:|---:|
| fact | 1,263 → 1,279 | 1,668 | 93 → 137 |
| loopfact | 1,053 → 1,081 | 1,419 | 63 → 116 |
| sum-divisors | 8,702 → 8,904 | 17,341 | 587 → 778 |

Completed instances of at least three steps rose from 10 to 348. The new actor completed 335 three-step, seven four-step and six five-step certificates. It completed zero six- to ten-step certificates on the development programs. Signed operations rose from 6,736 to 6,906, paid requests changed from 32,401 to 32,382, and aggregate EPT rose from 0.20789 to 0.21327. The actor attached a higher layout to 26,229 requests and completed 1,031, compared with 12,405 attachments and 743 completions. Coverage rose by 246 commits. The separate prefix-recovery study uses a different root and layout policy and records higher coverage.

Exclusive had zero independent searches. Its first differing Runs were 7, 8 and 11 in workload order. All three final graphs differed, and sum-divisors encountered a source panic at Run 91. The raw assist counters contain repeats, classified rejects, residual work, waves and timings. These trials overlapped and do not establish a throughput or EPS improvement.

[Training control](ancestor-training.json) · [Joint training](training.json) · [Boundary pointer](boundary.json) · [Teacher replay](replay.json) · [Assist](assist.json) · [Exclusive](exclusive.json) · [Historical comparison](../unified-layouts/README.md)

## Reproduction

Use the ROOT, WEIGHTS and native BIN from the unified layout study. OUT is a fresh directory. Omit the consumer growth flag to reproduce the uncapped ancestor training control.

```sh
python train_ripsat.py "$ROOT" "$ROOT/sum" "$WEIGHTS" "$OUT" --steps 10 --updates 1 --all-observed --grow-consumers --extra-eval sum-divisors
python ripsat_boundary.py "$ROOT" "$ROOT/sum" "$OUT" "$WEIGHTS" "$OUT" --cases fact loopfact sum-divisors
python bake_ripsat.py "$ROOT/sum" "$WEIGHTS" "$OUT"
python ripsat_replay.py "$ROOT" "$ROOT/sum" "$OUT/catalog.json" "$BIN" "$OUT/replay.json" --grow-consumers --cases sum dot fact loopfact sum-divisors
for name in fact loopfact sum-divisors; do
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$OUT" "$OUT/$name-assist.json" --case "$name" --native
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$OUT" "$OUT/$name-exclusive.json" --case "$name" --native --exclusive
done
```
