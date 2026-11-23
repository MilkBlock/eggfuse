## Recovering missing root proofs with bounded additional named reads

At the previous selector's first incomplete source Runs, the issued root proofs covered 3/4 commits on fact (Run 7), 4/5 on loopfact (Run 8), and 28/36 on sum-divisors (Run 11). Earlier threshold interventions found that opening the parent gate recovered the fact and loopfact misses; sum-divisors had both anchor and parent losses. We kept the 5,011-layout readable selector, boundary reader, source schedule, and native named verifier fixed.

A shared 24-unit head scores reads that the frozen root Actor ranked below threshold. It reads the structural template and atom vectors, the previous selected ports, the current port key, the model's old score margin, and continuous similarities between fields connected by the template. This applies at every nonempty arity and read depth. Up to four additional prefixes can occupy unused positions per rule, anchor and layer of the 32-wide beam. If original candidates already fill the beam, additional candidates receive no capacity. Exact ties spanning the cutoff are dropped. No additional verifier query is made during decoding. No change is made to zero-parent issuance. Extra partial reads can generate further proposals at later depths. Four is a local read budget, not a per-Run issuance budget.

Training used 231,493 sampled below-cut examples from sum-bits and dot-product. Positive partial reads follow observed teacher prefixes. Negatives include high-scoring and random competitors, so a legal alternative partial prefix can be missing from the labels. For complete tuples, a separate offline replay checked 148,059 named requests and added 9,629 positive examples whose proof differed from the sampled teacher path. The native labels were joined by their request identities because verdict order can differ from input order. This supervision used no evaluation program. A hash of each rule template withheld about one eighth of identities from recovery fitting and calibration. About one fifth of sampled training-program Runs were reserved to select thresholds. F1 on the sampled calibration examples was 0.845 for the learned head and 0.437 for a margin-only cutoff; these figures do not measure whole-Run coverage. Training used 32 epochs on Metal. [Training inputs, hashes and thresholds](training.json).

The margin-only control uses the old Actor score directly, with the threshold chosen on the same reserved examples. Both arms have the same maximum beam and recovery budget. Their actual proposal counts differ. This comparison does not isolate quality at an equal number of paid tokens.

| Development workload | Signed commits, baseline / learned / margin | Reference | Paid tokens, baseline / learned / margin | Nonempty Runs fully signed, baseline / learned / margin |
|---|---:|---:|---:|---:|
| fact | 1,257 / 1,374 / 1,396 | 1,668 | 3,759 / 4,462 / 4,942 | 66 / 96 / 105 |
| loopfact | 1,060 / 1,166 / 1,197 | 1,419 | 3,677 / 4,301 / 4,806 | 85 / 97 / 114 |
| sum-divisors | 8,928 / 9,654 / 9,843 | 17,341 | 24,545 / 27,720 / 30,850 | 218 / 247 / 279 |

On the first three previously incomplete Runs, the learned arm reached 4/4, 5/5 and 29/36; margin reached 4/4, 5/5 and 36/36. Micro signed coverage was 55.05%, 59.69% and 60.88% respectively. Aggregate signed operations per paid token were 0.22723, 0.22345 and 0.20528. Learned recovery delivered 885 additional signed effective operations for 4,502 additional external tokens. Sum-divisors alone incurred 2,033 more duplicate verdicts and 515 more rejections in that arm. Residual search completed the graph in assist. All arms reproduced the reference schedules, RHS, writes, resumes, events, final state and effective-operation ledger. The learned arm completed 4, 8 and 36 instances of higher layouts held out of layout training. [Full native counters](assist.json) · [Per-Run signed recall](run-recall.csv) · [Work and graph checks](summary.json).

In exclusive mode with zero independent search calls, the number of consecutive correct Runs changed from 6/7/10 to 8/9/10 with the learned head, and to 11/12/11 with the margin control (fact, loopfact, sum-divisors). All final graphs still diverged. The learned trajectories hit source panics at Runs 72, 58 and 101 respectively; margin finished all three source executions with different final states. [Exclusive outcomes](exclusive.json).

Four alternating paired clocks on each small workload included end-to-end CPU inference, verifier, exact fallback and setup. On fact the baseline, learned and margin arms achieved medians of 254.0, 255.5 and 284.0 signed operations per second. On loopfact these were 243.0, 231.5 and 256.1. The learned head won 3/4 and 1/4 pairs against baseline; margin won 4/4 on each. Total assist time increased in both treatments. The median times on fact were 3.62, 3.98 and 3.69 seconds, versus 0.150 seconds exact-only and 0.143 seconds teacher replay. On loopfact these were 3.47, 4.04 and 3.76 seconds, versus 0.145 and 0.148. No paired timing was run on sum-divisors. The timing keys original, refit and additional mean baseline, learned and margin. [Timing breakdown](density.json).

### Reproduction

Use ROOT, BIN, WEIGHTS and the expanded BAKE from the preceding study. OLD is the set-layout training experiment and SELECTOR its readable checkpoint. GOLD contains the separate exact operation ledgers.

```sh
python train_prefix_recovery.py "$ROOT" "$WEIGHTS" "$BIN" "$OUT/data" "$OUT/model" --collect sum dot
python train_prefix_recovery.py "$ROOT" "$WEIGHTS" "$BIN" "$OUT/data" "$OUT/model"
for arm in learned margin; do
  flags=()
  if [[ "$arm" == margin ]]; then flags=(--margin-only); fi
  for mode in assist exclusive; do
    extra=(--run-recall)
    if [[ "$mode" == exclusive ]]; then extra=(--exclusive); fi
    python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/$mode/$arm" --policy "$SELECTOR" --omit --attach --recovery "$OUT/model" "${flags[@]}" "${extra[@]}" --cases fact loopfact sum-divisors
  done
done
python prefix_recovery_report.py "$OLD" "$OUT" "$GOLD" "$OUT/report"
mkdir "$OUT/timing"
ln -s "$OLD/recall/readable" "$OUT/timing/original"
ln -s "$OUT/assist/learned" "$OUT/timing/refit"
ln -s "$OUT/assist/margin" "$OUT/timing/additional"
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/timing" "$OUT/density.json" --policy "$SELECTOR" --base-bake "$BAKE" --base-policy "$SELECTOR" --additional-policy "$SELECTOR" --recovery-dir "$OUT/model" --cases fact loopfact
```
