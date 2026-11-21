# A two-parent learned bucket is one bounded native action

> **Metric clarification.** A bucket packet names a left anchor and a key. The receiver opens the right posting to identify the matching parents. Ratios charging that bucket once measure external transport yield; the grouped lanes do not qualify for explicit-parent FEPT. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

The frozen donor model projects a specific, actual left anchor's port into a packed signature. The new actor can issue a **nine-word packet** containing the original epoch and rule, typed physical anchor, anchor version, both table generations, learned right-bucket signature and declared cardinality. The sender reads that bucket's cardinality before walking any individual partner. It does not send right-row identities or a hidden list of candidates. A separate three-parameter logistic head decides whether to use this representation. Its inputs are a bias, log bucket size and scaled log right table size. LBFGS on sum-bits and dot-product used the 103 donor groups with a later original commit and 38 with none, with equal total class weights. Only the frozen coefficients run on the two held-out programs. The all-groups control uses the same learned query/key projection and group ABI with a deterministic admission rule.

The compiler-derived gate admits a two-parent plan with one shared learned column, no unresolved local right-row tests or deferred arithmetic/other pair filters, a sufficient fresh anchor and a bucket of 2–64 entries. It declines a previously enumerated reverse join. The public source schema supplies the right table, column and original parent roles. One frequent case is rule 87, propagating `BodyContainsExpr` through `Top`: CG actually sent 120 donor-selected group packets for this rule. The same implementation handled 13 rule IDs on CG and 19 on 3mm.

The receiver decodes the actual public left row, authenticates its epoch and type, re-encodes its learned query, validates both source table versions, and builds its **own** keyed posting index by reading visible right-table rows from the graph. The index is reused only for the same table, column, table generation and union generation. It checks the exact declared extent. The receiver page holds one anchor and a reference to its own posting; it synthesizes the two original parents on each downstream read. The group packet itself has no per-member parent array. Every resulting potential binding still receives its original native source check, suffix and ordered RHS. A corrupted extent fails in each held-out program. This is local CPU execution, with no network transport timing. The fixed nine words are 72 bytes of action payload. The native queue also stores placement and diagnostic feature metadata.

## Held-out actual Pass 3

| Workload | Policy | Group actions | Literal pair packets replaced | No committed lane | No direct final-visible birth | Final-visible births credited to grouped lanes | Final-visible nodes / emitted packet | Final-visible nodes / explicit opportunity | Inference, ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CG | ordinary | 0 | 0 | — | — | 0 | 0.158717 | 0.158717 | 592.57 |
| CG | donor gate | 271 | 1,020 | 76 | 253 | 63 | 0.159265 | 0.151860 | 613.05 |
| CG | all eligible | 376 | 2,469 | 114 | 321 | 419 | 0.160256 | 0.152832 | 613.29 |
| 3mm | ordinary | 0 | 0 | — | — | 0 | 0.166032 | 0.166032 | 1,689.71 |
| 3mm | donor gate | 801 | 3,142 | 213 | 737 | 200 | 0.166731 | 0.160599 | 1,742.49 |
| 3mm | all eligible | 941 | 5,573 | 257 | 820 | 971 | 0.167421 | 0.161279 | 1,731.54 |

The numerators remain 34,595 / 92,658 final-visible original constructor identities on CG / 3mm. Emitted packets count every remaining external singleton and explicit multi-parent root, every action including actions with no winner, and every selected nested child. The stricter opportunity column additionally charges every size-ineligible or declined anchor action. The donor head saw 376 / 941 eligible buckets and declined 105 / 140. There were 10,863 / 22,020 tested anchor opportunities including ineligible bucket counts. A further 77,255 / 215,411 anchors failed structural or freshness admission before the optional group choice.

The donor-gated receiver had to decode 32,912 / 102,702 public table rows while building its own indexes, then supply 1,020 / 3,142 private candidates. Ultimately 775 / 2,290 of these candidates committed. The transfer head learned which collections contained any winner. That objective did not maximize surviving nodes per packet: admitting every structurally eligible group recovered many more directly attributed births. Four rotated resident inference samples follow warmup. All arms reproduce the original expanded learned stream, ordered Run RHS, effective writes, unions, Spine, final graph, physical winners, ordered constructor birth origins and visible fact identities. [Results and fault controls](results.json) · [Donor labels](donors.json) · [Frozen PyTorch weights](policy.json) · [Scoring and verification work](work.json)

```sh
d=benchmarks/pass3-cell-gpu/generative-pair-buckets
python "$d/build.py" "$EXP/generative-pair-build"
python "$d/study.py" "$EXP" "$EXP/generative-pair-build/session" "$EXP/generative-pair-donors" --train --cases sum-bits dot-product
python "$d/train.py" "$EXP/generative-pair-donors/results.json" "$EXP/generative-pair-donors/policy.json"
python "$d/study.py" "$EXP" "$EXP/generative-pair-build/session" "$EXP/generative-pair-holdouts" --cases conjugate-gradient 3mm --policy "$EXP/generative-pair-donors/policy.json"
python "$d/work.py" "$EXP" "$EXP/generative-pair-build/session" "$EXP/generative-pair-holdouts/results.json" "$EXP/generative-pair-work"
python "$d/verify.py"
```
