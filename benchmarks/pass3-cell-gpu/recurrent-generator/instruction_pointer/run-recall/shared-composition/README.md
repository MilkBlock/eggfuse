# Shared Cell composition on sealed EggCC Runs

**Native shadow, offline neural decoder.** The model trained on Metal using sum-bits and dot-product. The model and frozen prefix baseline ran on CPU for evaluation. The native receiver checked every complete request against the teacher snapshot. Teacher replay supplied every reference commit and determined when saturation occurred. No neural request drove the live graph. The weights, prefix checkpoint and receiver digests are in each workload JSON. This experiment measures proposal quality only. Wall clocks, exclusive saturation, EPT and saved executor work were outside the requested protocol.

## What the network received

The store applies sealed retirement, return and version events incrementally. An owner can expose several typed instructions. The consumer schema partitions its ordered table atoms across one or two distinct owners, with the first atom on the first side to avoid duplicate partitions. The first fresh referenced role owns a proposal if both sides changed. Training renames token IDs. Name fingerprints classify held-out examples only. They never enter the model.

The common 14-feature interface encoder reads arities, wiring counts, origin kind, instruction positions, version and forwarding features. The unary output scores a one-owner projection. For two owners, the score is the inner product between two learned structural projections plus a learned positive scale times the mean bit correlation across schema-aligned fields. Field bits come from native value hashes. This gives the model a strong prior for equality. Success does not establish that a network independently discovered field comparison. The scorer has no rule-specific parameters or early productivity gate. The event's output score is the maximum over actual partner scores. Ambiguous static port mappings are explicitly enumerated and charged. Encodings and LSH buckets are rebuilt for scoring in this prototype.

Fit 900 AdamW steps on 80 positive and 20 empty Runs sampled per training workload. Sampled 613 unary requests (532 positive) and 6,745 binary (937 positive) with native labels. Fit binary cross entropy on alternating unary/binary batches. Evaluate at logit zero, K=8, fixed seeds and fixed caps, without threshold selection on the evaluation programs. These three programs have been used for development in earlier experiments. They are out of training here, not a fresh blind test. The earlier census dictionary includes whole training traces; this experiment defines “seen” by examples actually supplied during fitting, including labeled negatives.

## Results on 120 sampled Runs

For each evaluation program draw 32 reference Runs with commits and eight empty Runs. The draw is uniform within each stratum. The sample contains 1,954 teacher commits, of which 1,505 have canonical proofs with one or two owners. Distinct native teacher IDs are the unit of recall. A different named proof can earn the same ID once. All rows below use the same snapshots and weights.

| Decoder | Requests | Valid receipts | Distinct targets of any arity | Distinct unary/binary targets / 1,505 | Binding / guard rejects |
|---|---:|---:|---:|---:|---:|
| Dense score, threshold zero | 8,383 | 5,873 | 895 | 804 | 1,505 / 1,005 |
| Exact top eight then threshold | 4,971 | 3,508 | 888 | 797 | 1,144 / 319 |
| LSH then top eight and threshold | 2,289 | 1,936 | 517 | 510 | 205 / 148 |

The dense arm produces 4,978 repeated valid proofs after the first credit for each teacher ID. It fully recalls 50 of 96 nonempty Runs. The additional 24 empty Runs are excluded from that denominator. No neural work replaces exact execution in shadow.

| Program | All commits hit / sampled | Complete nonempty Runs | Mean per-nonempty-Run recall, all arities | Unary/binary hit / required | Canonical bindings excluded at layout / rule budget |
|---|---:|---:|---:|---:|---:|
| fact | 320 / 382 | 17 / 32 | 76.96% | 280 / 293 | 4 / 0 |
| loopfact | 233 / 268 | 22 / 32 | 86.49% | 182 / 189 | 4 / 0 |
| sum-divisors | 342 / 1,304 | 11 / 32 | 45.58% | 342 / 1,023 | 689 / 18 |

Limits chosen for the small study were 2,048 projections per side and 65,536 products per layout, skipping the entire layout on overflow. Once accepting a whole event would exceed 16,384 scored candidates per rule and Run, omit that event. All excluded commits remain in the denominator. The two caps excluded 697 and 18 canonical proofs. Alternative proofs brought the ceiling of the scored material from 790 canonical to 816 distinct unary/binary targets. Native exhaustive labeling of those **scored** 411,230 proposals is an offline diagnostic. It never supplies candidates to the deployed scorer. 804 / 816 is conditional coverage.

| Binary teacher signature stratum | Required | Reachable in scored domain | Dense hit | LSH hit |
|---|---:|---:|---:|---:|
| Exact signature seen | 769 | 201 | 201 | 54 |
| Known producers never paired in training; consumer known | 76 | 22 | 22 | 2 |
| Pair previously seen elsewhere; new to this consumer | 16 | 9 | 9 | 2 |
| Same producer multiset and consumer; new mapping | 21 | 9 | 9 | 0 |
| Previously unseen producer | 146 | 116 | 116 | 23 |
| Previously unseen consumer, producers known | 13 | 13 | 13 | 1 |

Fingerprints include the concrete program template. “Pair” ignores role order and instruction positions, retaining multiplicity for distinct owners of the same type. These strata classify the canonical target proof. Separate issued-signature precision, event precision/recall and pessimistic positive-rank histograms are in each JSON. Across scored unary/binary events the maximum-score decision fires on 2,890 events, of which 2,273 have a valid request; 2,384 events had any valid request. For the new-combination stratum (including singletons) it fires on 124, with 65 productive, and detects all 65 productive events. A true-positive event need not select the correct partner.

The fixed LSH configuration uses five random hyperplanes, equal key norms via one extra dimension, the query bucket plus its five one-bit neighbors and exact reranking. It retains only 2,179 / 41,900 binary exact top-eight positions; 19,412 candidate scores remain in the retrieval arm including unary. Dense scores were computed as the comparison oracle. These counts are not timings or an implemented speedup.

| Budget matched within each rule and Run | Paid per arm | Frozen prefix hits | Relation hits |
|---|---:|---:|---:|
| Dense | 1,389 | 579 | 554 |
| Exact top eight | 1,336 | 578 | 553 |
| LSH + top eight | 813 | 393 | 343 |

Restrict both sides to proposals naming one or two owners. Rank the prefix proposals by the sum of frozen conditional log-sigmoid scores and relation proposals by their frozen logits. Use the common available count in each rule and Run. Drop the entire tie at a cut, reducing the common budget until the paid counts agree. This comparison only measures shared opportunity; the unrestricted counts above include opportunities offered by just one decoder.

## High-owner counterproofs on all three complete captures

Of all 20,428 teacher commits, six have no parent, 16,231 have one or two, and 4,191 have at least three (3,475 exactly three, 297 exactly four, 419 five or more). Test alternatives against the same native winner ID, rule, Run and sealed versions. Try same-table and same-hash alternatives offline to find positives. Separately enumerate the complete type-compatible one/two-owner domain up to 128 tuples per rule and Run, with one extra tuple detecting non-exhaustion. Only exhaustion of the type domain can certify a negative. These native probes do not enter the model or its credit.

| Program | High-owner commits | Low-owner alternative confirmed | Type domain exhausted with none | Unresolved |
|---|---:|---:|---:|---:|
| fact | 315 | 129 | 84 | 102 |
| loopfact | 290 | 130 | 79 | 81 |
| sum-divisors | 3,586 | 1,058 | 911 | 1,617 |

With the current port ABI and these exact snapshots, the share of all commits admitting a one/two-owner proof lies between 17,548 and 19,348 out of 20,428. The upper bound excludes the six empty proofs and 1,074 exhausted negatives. A different Higher Cell catalog or a different upstream token history can change these bounds.

For a separate static diagnostic, seed the first fresh owner and next distinct source-order owner of each high proof. Propagate known slots through keyed table calls and primitive signatures. On the successful recorded proofs the rows for 3,618 of 5,501 remaining owners have determined keys, covering every remaining owner in 2,701 commits. Obtaining the value still requires a runtime computation or point read, and knowing the row does not identify its named owner and instruction. No such lookup or completion receives model credit.

## Reproduce

Run in the instruction_pointer directory using the captured workspace and its MPS PyTorch environment. The native replay checks schedule, writes, RHS, resumes, events, unused requests and final state hash against each saved capture. The archived sum-bits semantic acceptance check separately passed on the saved reviewed exports.

```sh
root=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123
python=/Volumes/EggFuseWorkspace/envs/eggfuse-ml/bin/python
receiver="$root/whole-fork-credit/receiver"
prefix="$root/alternate-proofs/root-calibration/opaque-parent/calibrated/model.pt"
out="$root/relation-experiment"
"$python" fit_relation.py "$root" "$receiver" "$out/train"
for workload in fact loopfact sum-divisors
do
  "$python" lower_owner_audit.py "$root/$workload" "$receiver" "$out/$workload-higher.json"
  "$python" evaluate_relation.py "$root/$workload" "$prefix" "$out/train" "$receiver" "$out/$workload.json"
done
"$python" -m unittest discover
```
