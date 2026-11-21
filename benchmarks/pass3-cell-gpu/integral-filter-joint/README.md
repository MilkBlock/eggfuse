# Combine scalar negative proofs with whole and partial integral packet suppression

A single native Rust Cell CPU binary runs the original model, the compiler’s exact scalar negative proof, a previously accepted root’s independently released consumer proof, and the source verifier. The controls cross scalar filtering on/off with whole-bank suppression on/off. A fifth arm allows partial suppression with scalar filtering enabled. All modes use the same first-hop integral verifier and frozen model. The independent default CPU reference and unchanged Run schedule remain the acceptance oracle.

The actor computes every original score and advances the same recurrent state. Certified missing function keys or seminaive-stale ports first remove impossible singleton wire requests. For a surviving source address to be generated internally, the earlier root must already have supplied an independent candidate for the compiler’s determinate singleton pivot at this exact Run, watermark and source version. The function-key suffix and its result slots were checked at release. Unrepresented survivors retain their external packets. Ambiguous or unexpected extra releases, conflicting versions, a noncanonical source order or inconsistent certified scores decline that attempt. Whole mode also declines if any surviving source needs an external packet.

For a mixed bank, the issuer traverses the original surviving source order and alternates spans of external packets and locally instantiated, independently proven bindings. External spans allocate ordinary wire pages. Internal spans reserve the same logical serials, write zero external bytes and carry no external child certificate. The verifier uses the two locally known old/fresh scores and earlier root proof for these rows and restores original model serial order before source arbitration. Omitted scalar negatives still advance the model serial but consume no root serial. A duplicate virtual ordinal, stale release or corrupted lane order fails closed. The tested route uses one scoring row, batched source verification, checked root slots and no speculative record reservation. Other source configurations use ordinary issuance.

## Held-out real Pass 3 results

| Program and mode | Singleton packets | Total packets¹ | Root wire B | New nodes/packet | Retained nodes/packet | Inference ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits, raw external | 7,889 | 13,992 | 287,128 | 0.25800 | 0.19232 | 34.64 |
| sum-bits, raw whole | 7,175 | 13,278 | 261,032 | 0.27188 | 0.20267 | 35.33 |
| sum-bits, filtered external | 6,559 | 12,662 | 238,952 | 0.28511 | 0.21253 | 34.46 |
| sum-bits, filtered whole | 5,842 | 11,945 | 212,656 | 0.30222 | 0.22528 | 37.43 |
| sum-bits, filtered mixed | **5,444** | **11,547** | **208,736** | **0.31264** | **0.23305** | 39.40 |
| 3mm, raw external | 845,168 | 1,068,648 | 20,817,600 | 0.11183 | 0.08671 | 2,154.58 |
| 3mm, raw whole | 836,221 | 1,059,701 | 20,586,680 | 0.11277 | 0.08744 | 2,016.94 |
| 3mm, filtered external | 334,594 | 558,074 | 8,415,216 | 0.21413 | 0.16603 | 1,971.04 |
| 3mm, filtered whole | 325,603 | 549,083 | 8,182,344 | 0.21764 | 0.16875 | 1,995.00 |
| 3mm, filtered mixed | **311,648** | **535,128** | **8,006,144** | **0.22332** | **0.17315** | 2,001.50 |

¹ Actual external singleton and multi-parent roots plus all selected nested child packets, including zero-birth packets. The multi-parent count is 5,912 / 220,972 on every corresponding workload; selected children are 191 / 2,508 out of 305 / 7,120 total child decisions. No per-span or per-parent external summary packet is added for an internal release. The original-identity constructor counts are 3,610 / 119,503 new and 2,691 / 92,658 retained in all five arms. Timing reports four rotated, post-warmup complete inference samples; prepared process wall samples are in the receipts. [Individual samples, denominators, source and physical digests](results.json)

Conditional on the certified scalar filter, whole-bank suppression removed 717 / 8,991 more packets. Mixed mode additionally removed **398 / 13,955** packets from **119 / 327** partially covered rule occurrences. These are genuinely mixed: the same occurrences retained 847 / 55,524 external singleton lanes, split into 207 / 2,807 ordinary contiguous external spans. All 1,115 / 22,946 internally delivered lanes reached their original ordered RHS. External and internal winners retained the same global logical root serial, source witness and per-rule serial as the matching filtered external control. The complete virtual scoring decisions and graph are equal across all five arms. The original native checker also independently rematched every omitted internal lane and rejected all 1,330 / 510,574 certified negative candidates. Both corrupted order and stale release controls fail in execution.

The additional integral check still traverses the actual scheduled ports, looks up determinate suffix rows, constructs internal bindings and merges them back into source order. The saved wire does not remove model scoring or external proof/release bookkeeping. Against filtered external, mixed mode increased complete inference by 4.94 ms on sum-bits and 30.46 ms on 3mm in this sample. The deployment choice depends on whether wire traffic or current CPU time is the bottleneck. [Normal-runtime work counters](cost.json)

```sh
d=benchmarks/pass3-cell-gpu/integral-filter-joint
python "$d/build.py" "$EXP/integral-joint-build"
python "$d/study.py" "$EXP" "$EXP/integral-joint-build/session" "$EXP/integral-joint-results"
python "$d/cost.py" "$EXP" "$EXP/integral-joint-build/session" "$EXP/integral-joint-cost"
python "$d/verify.py"
```
