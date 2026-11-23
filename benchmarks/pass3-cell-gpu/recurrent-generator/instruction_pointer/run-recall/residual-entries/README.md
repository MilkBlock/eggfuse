## Bake another generation from the current policy's unclaimed commits

We ran the previous 4,096-layout policy with native CPU assist and captured the actual signed and residual receipts. Their counts partitioned the ordered reference commits on all five programs. We kept each sealed memory delta and checked the source schedule, RHS order, writes, resumes, events and final state. Actual returned port addresses and versions connect the producer and consumer. At a join, the extractor now also tries starting the backward growth with each distinct direct producer. This permits a later producer to serve as the entry while an earlier return is already visible at its boundary.

Only sum-bits and dot-product contributed patterns. A candidate had to include an actual residual commit, start at an externally signed root, have all independently named boundary versions available on entry, retain the required returned versions, and resume at the first eligible schedule for each group. We appended all 915 previously absent qualifying layouts. The catalog now has 5,011 layouts spanning two through ten rules. The GNN, root Actor and boundary pointer are frozen. The same rule wiring, scorer, action space and native verification protocol apply to all sizes. [Append-only layout file](appended.json) · [Parent catalog and trace identities](study.json).

We compared keeping the old policy, extending its catalog with frozen weights, and refitting the shared contextual bandit over the extended catalog. The frozen-weight control checks the original catalog prefix, shared weights and numerical equivalence of its original graph codes. The refit used twelve stochastic native training trajectories, alternating three seeds per program for the critic and three others for the policy. There were 76,202 critic examples and 76,172 policy examples. The complete-layout digest split excluded 654 layouts from exploration and optimization. The same three program holdouts have been used in earlier development. [Training details](training.json) · [Deployable policy](policy.pt).

### Which residuals can the catalog address?

The denominator is the set of commits that the original assist run obtained from residual search. In that fixed execution, we counted distinct residuals appearing inside a recorded ready graph with an already signed external root. Overlapping witnesses count once. The two catalog columns allow multiple competing completions per root and use the observed correct boundary and future path. Each is an opportunity count for this extraction, not a global limit on equivalent proofs or a live neural recall measurement.

| Program | Original residuals | Reachable with old catalog | Reachable with extension | Reachable using only the root's own inputs with extension |
|---|---:|---:|---:|---:|
| fact | 407 | 130 | 195 | 7 |
| loopfact | 361 | 100 | 147 | 5 |
| sum-divisors | 8,583 | 1,929 | 2,900 | 195 |

We reran the original policy and required every receipt, parent and version to match the archived history. An offline observer then evaluated the extended, refitted selector and the ordinary boundary pointer on these same inputs. Giving a layout means trying every qualifying observed layout. Giving a boundary means crediting any recorded versioned boundary that establishes the residual within that layout. With a learned boundary we required an exact match to a recorded certificate. This diagnostic can miss other valid proofs. It measures the originally missed subset. The interventions never supplied a graph or parent to live execution.

| Program | Given layout and boundary | Learned layout, given boundary | Given layout, learned boundary | Both learned |
|---|---:|---:|---:|---:|
| fact | 195 | 1 | 38 | 1 |
| loopfact | 147 | 1 | 25 | 1 |
| sum-divisors | 2,900 | 50 | 594 | 10 |

On sum-divisors, even with the observed boundary, the refitted selector chose graphs reaching only 50 of these 2,900 commitments. Conversely the boundary reader recovered observed proofs for 594 if supplied with target layouts. Both decisions matter and they have quite different error rates. [Fixed-history interventions](interventions.json) · [Readiness, selection and native counts](summary.json).

### Native assist, independent execution and cost

| Program | Signed commits, original / frozen extension / refit | Reference commits | Signed effective operations, original → refit | Paid tokens, original → refit | EPT, original → refit |
|---|---|---:|---|---|---|
| fact | 1,261 / 1,262 / 1,268 | 1,668 | 911 → 917 | 3,787 → 3,789 | 0.24056 → 0.24202 |
| loopfact | 1,058 / 1,058 / 1,053 | 1,419 | 831 → 821 | 3,755 → 3,745 | 0.22130 → 0.21923 |
| sum-divisors | 8,758 / 8,764 / 8,794 | 17,341 | 5,167 → 5,190 | 24,715 → 24,744 | 0.20906 → 0.20975 |

The refit issued newly added graphs 17, 9 and 55 times. Of these, 1, 1 and 4 fully completed. Changes in overall signed coverage can also come from changed choices among the original layouts. All assist runs reproduced native source execution and the exact effective-operation ledger. Search-free trajectories diverged at Runs 7, 8 and 11 respectively; sum-divisors encountered its source panic at Run 85. [Full assist counters](assist.json) · [Exclusive execution](exclusive.json).

Four alternating pairs per program compared CPU inference and native assist against the previous policy, exact-only execution and teacher replay. Median signed operations per second fell from 262.45 to 238.36 on fact and from 254.11 to 229.63 on loopfact. The expanded, refitted policy lost all eight pairs. Median assist times were 3.85 and 3.58 seconds versus 0.14 seconds for exact-only on both. There is no paired clock for sum-divisors. [Timing breakdown and oracle](density.json).

### Reproduction

Use the parent study's BIN, WEIGHTS, BASE catalog and OLD policy. ROOT contains its programs, reference captures and manifest. OUT is a new directory. Every learned layout decision uses the normal port store. Opportunity extraction is offline.

```sh
python residual_layouts.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BASE" "$OLD" "$OUT" --cases sum dot fact loopfact sum-divisors
python extend_layout_bake.py "$ROOT" "$ROOT/sum" "$WEIGHTS" "$BASE" "$OUT" "$OUT/expanded"
python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$OUT/expanded" "$OUT/logs" --explore --omit --attach --cases sum dot --seeds 1703 1709 1721 1733 1741 1753
python train_layout_bandit.py "$OUT/logs" "$OUT/expanded" "$OUT/refit"
for arm in expanded refit; do
  policy=(--policy "$OUT/refit")
  if [[ "$arm" == expanded ]]; then policy=(--policy "$OLD" --training-bake "$BASE"); fi
  for mode in final exclusive; do
    flags=()
    if [[ "$mode" == exclusive ]]; then flags=(--exclusive); fi
    python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$OUT/expanded" "$OUT/$mode/$arm" --omit --attach "${policy[@]}" "${flags[@]}" --cases fact loopfact sum-divisors
  done
done
# ORIGINAL_AUDIT and GOLD are the parent experiment's final/rl and exact ledger reports.
ln -s "$ORIGINAL_AUDIT" "$OUT/final/original"
python residual_bake_report.py "$ROOT" "$ROOT/sum" "$OUT" "$BASE" "$GOLD" "$OUT/summary.json" --cases fact loopfact sum-divisors
python residual_boundary_audit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BASE" "$OUT" "$OLD" "$OUT/interventions.json" --cases fact loopfact sum-divisors
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$OUT/expanded" "$OUT/final" "$OUT/density.json" --policy "$OUT/refit" --base-bake "$BASE" --base-policy "$OLD" --cases fact loopfact
```
