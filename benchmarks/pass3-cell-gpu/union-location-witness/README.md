# Predict physical union locations before enumerating reverse readers

At a real pre-union site, the ordinary Rust CPU executor knows the displaced and kept representatives. This experiment asks a trained shared port head to name physical facts and fields before looking at the displaced reverse bucket. Its bounded address vocabulary includes the Cell encoded by the displaced Eq id when it identifies an existing Cell, and up to four fact-parent addresses in the currently consumed neural root token. Constructor-induced repair events can occur outside a live token. The network sees current template wiring and early instance metadata, including source slots and Copy aliases, role, physical field position, parent-token membership and birth epoch. It never sees the reverse-reader identities, decoded field equality, ground-truth mask or later RHS outcome. All 12 weights and the bias are shared across templates.

The emitted certificate identifies the losing/kept pair, Run epoch, union sequence, Cell and operation, proposed field mask and expected table. The native validator stamps the physical version and immutable payload being checked. Each selected field must actually contain the losing scalar Eq value. When the forward subscription has as many distinct current representatives as the relation's scalar Eq columns, a single confirmed match covers that occurrence exactly once. Otherwise the validator checks unlisted possible Eq columns. Sets, functions as proposed target objects, missing payloads, hidden or specialized facts and unsupported shapes retain ordinary handling. The old payload identity, Run, union number and version are checked again at the point of applying the patch. Successful repair substitutes only the certified fields while retaining the original dirty publication and later ordered repair. Detailed execution independently decodes the linked instruction and checks all resulting values.

For a complete-list fast path, every proposed member is certified against the existing forward membership. Unique certified addresses must also equal the exact original reverse cardinality. The model never reads the bucket members to discover its proposals. An independent audit compares the entire sorted list before it is used. Incomplete lists retain ordinary notification and can still patch individually verified facts. This specific experiment retains the reverse index for cardinality, physical merging and incomplete notifications; local field prediction is not credited with removing that index. The [independent self-owner storage ablation](../implicit-owner-subscribers/README.md) measures actual memory release.

Three separate real source programs provide 6,621 positive and 110,666 negative field observations after proposals' features have been fixed. A PyTorch shared affine head trains with balanced positive/negative mass. Two donor-only thresholds maximize F0.5 or F2. The static control names direct source slots and Copy aliases; the all-local control proposes every possible mask bit. The combined control adds strict learned selections to static ones. A bounded shared-program control reuses the same combined returning masks across identical template/slot/context keys. Its stored plan has operator indices and masks but no graph rows or reverse subscribers.

| Held-out / policy | Confirmed scalar positions / proposed | All affected scalar positions | Complete / nonempty unions | Notified directly / all reader notifications | Full inference ms |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient, static | 11,912 / 18,794 | 34,401 | 3,721 / 9,151 | 4,053 / 31,916 | 646.42 |
| conjugate-gradient, strict | 10,020 / 13,197 | 34,401 | 3,279 / 9,151 | 3,603 / 31,916 | 632.16 |
| conjugate-gradient, broad | 12,417 / 19,301 | 34,401 | 3,721 / 9,151 | 4,053 / 31,916 | 662.49 |
| conjugate-gradient, baked | 11,912 / 18,794 | 34,401 | 3,721 / 9,151 | 4,053 / 31,916 | 642.63 |
| 3mm, static | 24,447 / 38,258 | 70,336 | 8,350 / 19,182 | 9,375 / 65,816 | 1,901.41 |
| 3mm, strict | 21,153 / 27,320 | 70,336 | 7,176 / 19,182 | 8,164 / 65,816 | 1,961.52 |
| 3mm, broad | 25,535 / 39,346 | 70,336 | 8,350 / 19,182 | 9,375 / 65,816 | 1,960.85 |
| 3mm, baked | 24,447 / 38,258 | 70,336 | 8,350 / 19,182 | 9,375 / 65,816 | 1,933.57 |

Each timing uses four rotated, resident whole-program measurements at seed 1703. The original neural Pass 3 roots, winning physical parents, all source RHS, effective writes, Spine, union order, fresh IDs and final graph match the independent default source execution. The normal path without location proposals took 607.42 ms on CG and 1,981.74 ms on 3mm. All local candidate cells together supplied 25,812 of the 70,336 actual scalar positions on 3mm. Broad predicts 25,535 of those reachable fields (98.93%) but only 36.30% of the global scalar positions, with precision 64.90%. It adds 1,088 verified fields beyond the static wiring. On these workloads the extra active-token parent cells add zero correct positions beyond those reachable through the losing owner. Many unions occur in rebuild or have other readers beyond the proposal vocabulary.

Example from the actual CG trace: at epoch 24, union 0, template-local position (Cell 843, operation 1) names bit 2 in TypeList-ith (mask 4). The independent exact mask is 4 and the reverse set has two members. A correct physical position alone does not certify the second member. At union 15 of the same epoch the predicted Base mask is 2 but this fact has no actual affected field; that proposal receives no patch credit. A deliberately stale union serial activated no patch and all ordinary notifications remained correct. [Weights](model.json) · [Source and counters](results.json) · [Donor counts](donors.json) · [Instrumented issue, check and patch intervals](phases.json)

```sh
d=benchmarks/pass3-cell-gpu/union-location-witness
python "$d/build.py" "$EXP/locator"
python "$d/capture.py" "$EXP" "$EXP/locator/session" "$EXP/locator-training"
python "$d/train.py" "$EXP/locator-training/donors.json" "$EXP/locator-training/model.json"
python "$d/study.py" "$EXP" "$EXP/locator/session" "$EXP/locator-training/model.json" "$EXP/locator-test"
python "$d/phases.py" "$EXP" "$EXP/locator/session" "$EXP/locator-training/model.json" "$EXP/locator-clocks"
python "$d/verify.py"
```
