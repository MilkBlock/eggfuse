# Owner retrieval through Cell fields on frozen EggCC Runs

Native **shadow** quality experiment. Uses the exact 120 Runs of the preceding [shared composition study](../shared-composition/README.md), with 1,954 teacher commits and 1,505 canonical one/two-owner targets. All 76 unseen producer pairs and all 689 previously layout-excluded sum-divisors targets remain in scope. The model, prefix checkpoint and receiver digests accompany each ledger. Teacher commits drive the graph for all 634, 618 and 1,644 reference Runs, including every unsampled Run. The verifier audits fully named proposals; trajectory, writes, resumes, events and state digest are checked. No runtime takeover or timing measurement. No recursion or high-owner audit in this study.

## Quality funnel

Each stage through verification counts **the recorded canonical proof**. The last column credits any verified proof of the same distinct reference commit. Alias hits can exceed the canonical funnel. All arms have the same semantic domain of 1,505 targets.

| Arm | Canonical scored | Canonical top 8 | Issued | Verified | Any proof | Complete-tuple scores | Paid requests |
|---|---:|---:|---:|---:|---:|---:|---:|
| All blocks | 1,505 | 1,252 | 1,240 | 1,240 | 1,451 | 2,232,175 | 9,658 |
| Fixed workload score budget | 492 | 481 | 473 | 473 | 896 | 411,230 | 3,672 |
| Previous joint-projection LSH on full domain | 604 | 576 | 564 | 564 | 683 | 130,498 | 3,518 |
| Single pooled owner key | 1,126 | 1,065 | 1,053 | 1,053 | 1,270 | 343,946 | 7,710 |
| Exact neural multi-key ranking | 1,465 | 1,248 | 1,236 | 1,236 | 1,436 | 398,481 | 9,638 |
| Neural multi-key ANN | 1,463 | 1,245 | 1,233 | 1,233 | 1,433 | 200,759 | 9,499 |
| Exact field-hash diagnostic, uncapped owners | 1,505 | 1,252 | 1,240 | 1,240 | 1,451 | 25,806 | 9,658 |

The dense arm reaches 1,555 distinct teacher commits including higher-arity teacher proofs with low-owner aliases. The learned ANN arm reaches 1,537. Its 9,499 requests yield 7,983 valid receipts, including 6,446 repeats, with 1,185 binding rejections and 331 guard rejections. It completes 54 of 96 nonempty sampled Runs. The 24 empty Runs are excluded from that denominator. The archive includes per-Run numerators and denominators, and separate funnel and retrieval counts for each program. Counts for matched-paid end-to-end arms (names containing “vs”) carry only final hits; their intermediate zero fields are unmeasured.

For the **689** previously excluded sum-divisors targets, full blocks score all 689, verify 491 canonical proofs and recover **654** by any proof. Keeping the old total score budget and spreading draws uniformly over each program's whole domain yields **347**. Field ANN scores 648 canonical proofs, verifies 484, and reaches **636** by any proof. Uniform allocation is one reproducible policy; these counts do not bound other allocators.

For the **76** evaluation targets with known individual producers never paired during training, dense reaches **70** by any proof (58 canonical); true single-owner keys **60**; exact multi-key and ANN both **71** (59 canonical); previous LSH **12**. The prior restricted-domain LSH reached two. Different shortlists can break score-boundary ties or remove competing proposals, so restricted top-eight decoding need not be nested within dense top-eight decoding.

## What was retrieved and trained

The previous LSH indexed a role-conditioned **complete projection**, including aligned fields and the learned Compose vector. An actual pooled single-key owner ablation is new here. Its key averages all exposed field vectors. The structured interface uses shared slots from the consumer schema to select a source port/column and a destination port/column. Persistent entries hold a 24-dimensional key and query for each field. An index is partitioned by table and column. Eight random hyperplanes define the bucket. Probe the query bucket and its eight one-bit neighbors for each role. Union the resulting **owner addresses**. Score their type-visible op mappings through the field keys. Exact field ranking reads all type-visible projections. Owner rank is the best eligible projection score; select up to 32 owners and expose their mapped projections to the unchanged Compose scorer. A missing cross-field link falls back to pooled owner similarity on the typed domain. Unary events need no partner retrieval.

The role routing is static, the projector is shared across roles. Process changed values and retirements incrementally; a version-only advancement retains the previous embedding. Across the three full input traces, the index writes 154,321 field keys and removes 17,042. The prototype still materializes per-layout arrays and typed projection lists for each measured Run. Blocks of at most 256 bound dense score operations; this does not bound the memory of the whole diagnostic. Retrieval exact-vs-ANN is evaluated side by side. The ANN arm recomputes its neural similarities on its bucket candidates. Shared dense diagnostic work is not an implementation cost or wall-clock estimate for either arm.

The new field query and key projections train on Metal using sum-bits and dot-product only. Multi-positive contrastive loss uses 774 events, 1,082 native-labeled positive requests and 11,682 memory negatives, with randomized owner names. Configuration: width 24, 400 steps, seed 871, logit multiplier 8. The Compose weights remain frozen. The same starting field weights without training are a separate ablation on the same Runs. **Exact multi-key retrieval yields 1,436 distinct eligible targets both before and after training. ANN yields 1,436 before and 1,433 after training.** The model starts with a common bit projection and an identity query transform, so identical fields already have identical keys and queries. This study supports schema-directed addressing on these snapshots; it gives no positive marginal result for contrastive training. The evaluation programs are held out of fitting but have been used in prior development.

The field ANN recovers **18,667 / 67,098 (27.82%)** exact neural top-eight owner addresses. After Compose, it preserves **17,396 / 62,871 (27.67%)** dense top-eight binary proposal positions, versus 53,133 / 62,871 for exact multi-key retrieval. The first metric counts owners, the second counts projections; both include events without valid results. Their denominators differ from semantic recall. The hash arm intersects equal recorded 64-bit hashes on schema-linked columns offline. This simulates exact-key filtering; no native label or equality-filtered shortlist enters a model arm. The receiver still compares actual values. No claim about hash-index latency.

## Budget controls

The unrestricted diagnostic scores the entire domain. For the fixed arm a reference-independent prepass counts typed delta projections. Allocate the preceding study's workload-specific score totals uniformly without replacement over that domain, including layouts assigned zero work previously. This offline budget scheduler knows the sample's total domain size. Dense scores serve only the diagnostic; shortlist arms perform their own Compose scores.

| Control | Common complete-tuple scores | Common paid | Distinct eligible commits |
|---|---:|---:|---|
| Same typed domain, matched shortlist counts per event | 165,971 | 44,087 | pooled 1,229; exact multi-key 1,488; multi-key ANN 1,485 |
| Same exact sampled tuples for both frozen scoring functions | 411,230 | 58,390 | old prefix 918; Compose 919 |

In these rank-only controls each arm pays up to eight requests per event without a threshold. Matched retrieval truncates each shortlist to the smallest available count before scoring. Prefix ranking sums conditional log-sigmoid scores along the existing source-order decoder, evaluated on given complete tuples; it does not run the prefix beam in this control. Ranking ties are broken by a common label-blind random draw. In ordinary thresholded arms, all Compose scores tied across the top-eight boundary are dropped to preserve the prior decoder convention. Complete-tuple score counts do not equalize the number of neural operations inside a score or the retrieval work.

As a separate end-to-end control, run the actual frozen width-32 prefix decoder, retain its one/two-owner requests, and compare confidence-ranked requests at the shared available payment per rule and Run. At 2,810 requests per arm, prefix reaches **1,154**, dense Compose **1,144**. At 2,801 per arm, prefix reaches **1,152**, field-ANN Compose **1,135**. Prefix and uniformly budgeted Compose reach 817 and 818 at 1,722 payments. These comparisons do not discard large layouts; they restrict comparison to shared payment opportunity. The measurements support the retrieval interface change, without establishing a replacement for the deployed prefix decoder.

## Reproduction

Run from the instruction_pointer directory using the saved workspace and CPU inference environment with MPS available for fitting.

```sh
root=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123
py=/Volumes/EggFuseWorkspace/envs/eggfuse-ml/bin/python
out="$root/structured-retrieval"
"$py" train_field_retrieval.py "$root" "$out"
for program in fact loopfact sum-divisors
do
  "$py" evaluate_field_retrieval.py "$root" "$program" "$out"
  "$py" evaluate_field_retrieval.py "$root" "$program" "$out" --initial
done
"$py" -m unittest discover
```

The field and Compose checkpoints, receiver and old pointer checkpoint are identified by the program ledgers. Reuse the same tape, capture, program and memory export as the preceding study. The reviewed sum-bits semantic contract passed separately using saved exports.
