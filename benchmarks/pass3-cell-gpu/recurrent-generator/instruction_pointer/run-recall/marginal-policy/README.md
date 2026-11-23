# Program-held calibration of higher Cell issuance

Each graph action specifies rule occurrences, Run groups, independent boundary inputs and references to returned instruction ports. The frozen Bake catalog contains 54,156 layouts with up to ten rule occurrences. A shared graph scorer and boundary pointer already handle different graph sizes. This experiment fits four shared coefficients from the existing three predicted receipt counts. The root Actor, graph encoder and boundary pointer are frozen. [Catalog and extraction limits](../consumer-graphs/README.md)

## Native intervention and model selection

Repeat a full native assist rollout from the same sealed history, issuing the standalone root in place of one chosen higher Cell. Subsequent decisions read their own receipts. Compare the distinct signed source RHS ordinals gained and lost and the change in paid external requests. The supervised target is net signed commits plus 0.25 per external request saved. Both sides must reproduce the reference execution and identical effective operations per source ordinal.

Three randomly selected decisions per observed stratum per training program give 18 forks. Weight by inverse inclusion probability and give each training program equal total weight. This sample covers graph choices the original policy made. Six interventions on graphs without child attempts changed neither signed work nor payments. A seven-step dot-product Cell gained five signed commits and lost one, added two signed effective operations and saved seven packets. A ten-step sum-bits Cell gained 20 and lost 15, signed three fewer effective operations and cost 26 extra packets. Size alone would reward both. [Sum-bits forks](data/sum.json) · [Dot-product forks](data/dot.json)

The protocol predates validation. Sum-bits and dot-product supplied the training forks. The original receipt head had selected its training epoch on a separate seed of these same programs. For the new adjustment, affine-twins and gated-state select the strength. Clamped-ramp was evaluated only after locking the winner. These are distinct inputs to the same EggCC rules drawn from earlier repair experiments. This holdout applies to this calibration. Fact, loopfact and sum-divisors remain historical development programs. [Program hashes and selection rule](protocol.json) · [Validation lock](lock.json)

| Native assist candidate | Affine-twins signed / 4,215 | Gated-state signed / 6,118 | Worst recall | Pooled EPT |
|---|---:|---:|---:|---:|
| Original policy | 3,337 | 4,448 | 72.70% | 0.21040 |
| Strength 0.25 | 3,313 | 4,391 | 71.77% | 0.20870 |
| Strength 1 | 3,284 | 4,347 | 71.05% | 0.20176 |

Both adjustments lost signed submissions on both validation programs. The selection rule retained the original policy.

## Locked test

Native assist signed 5,981 of 9,471 reference commits. Residual execution supplied the remaining 3,490. The ordered effects, final state and effective-operation ledger matched reference. The issuing policy signed 3,925 effective operations for 16,888 paid external requests. Of 530 nonempty Runs, 255 signed all teacher commits. Completed graphs ranged from two through eight steps. Among 602 instances issued with held layout identities, two completed. The training menus excluded all 6,719 held identities. The raw reports include program, model and receiver identities, decision counts, rejection reasons, residual work, per-Run recall and timings. Single audited episodes provide no paired speed estimate. [Assist audit](test/assist/clamped-ramp.json)

Exclusive made zero independent search calls. Its first 12 Runs matched the reference. It diverged at Run 13 and hit a source panic at Run 98. The reference has 1,544 Runs. This single test program cannot establish broad transfer. [Exclusive trajectory](test/exclusive/clamped-ramp.json)

## Reproduction

Run from instruction_pointer using MPS-enabled Python. Set STUDY to actor-eggcctraining-20261123, OUT to a fresh experiment directory, LIB to unified-consumers, POLICY to consumer-receipt-credit/commit-policy, REC to native-prefix-recovery/model, WEIGHTS to the frozen root Actor, and BIN to the cell_token_replay release example built with feature cell-token-ept. Use the training captures and full reference operation ledgers from STUDY. Place each validation and test program with its pinned hash at OUT/corpus/PROGRAM/program.json. Copy the archived corpus/manifest.json to OUT/corpus/manifest.json.

~~~sh
PROTO=run-recall/marginal-policy/protocol.json
for name in sum dot; do
  python marginal_forks.py "$STUDY" "$STUDY/sum" "$BIN" "$WEIGHTS" "$LIB" "$POLICY" "$REC" "$STUDY/layout-ownership/gold" "$OUT/data" --case "$name" --draws 3
done
python marginal_policy.py fit "$OUT/data" "$POLICY" "$LIB" "$PROTO" "$OUT/policies"
for name in affine-twins gated-state; do
  dir="$OUT/corpus/$name"
  "$BIN" capture "$dir/program.json" "$dir/tape.json" audit > "$dir/capture.json"
  "$BIN" reference "$dir/program.json" - audit --ept > "$dir/exact.json"
done
for arm in base cal-0.25 cal-1; do
  model="$OUT/policies/$arm"
  if [ "$arm" = base ]; then model="$POLICY"; fi
  python layout_credit.py "$OUT/corpus" "$STUDY/sum" "$BIN" "$WEIGHTS" "$LIB" "$OUT/validation/$arm" --cases affine-twins gated-state --omit --attach --run-recall --recovery "$REC" --policy "$model"
done
python marginal_policy.py lock "$PROTO" "$OUT/corpus" "$OUT/validation" "$POLICY" "$OUT/policies" "$OUT/lock.json"
python marginal_policy.py test "$PROTO" "$OUT/lock.json" "$OUT/corpus" "$STUDY/sum" "$BIN" "$WEIGHTS" "$LIB" "$POLICY" "$OUT/policies" "$REC" "$OUT/test"
~~~
