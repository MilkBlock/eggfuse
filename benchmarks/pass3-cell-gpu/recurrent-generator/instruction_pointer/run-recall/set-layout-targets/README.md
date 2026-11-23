## Training a layout selector on the full set of observed continuations

The catalog, graph encoder, root Actor, boundary pointer and native receiver are frozen at the 5,011-layout study. For each external decision on the original assist history, collect every observed layout that is ready at this root's versions and first eligible schedule. A tail step contributes a unit of supervision if the original native execution credited it to residual search or to a previously signed internal step. The latter rewards preservation of useful behavior. Repeated occurrences of a layout use the maximum observed gain from a single certificate. Teacher information is confined to training labels and offline interventions. Neither deployment nor the native verifier gets the alternatives.

Two selectors received the same contexts and compatible action menus. The **observed** target credits a ready continuation with an observed boundary. The **readable** target credits it only when the frozen deployment pointer, reading the ordinary sealed typed port store, independently reproduces one of those complete versioned boundaries. Per root, gains normalize to a distribution on layouts. A root without observed credit targets the standalone action. A missing recorded boundary can have a valid equivalent proof. The target is a conservative observation of opportunity.

The previous bandit used stochastic realized native returns. These two arms use supervised cross-entropy, with the same shared Utility network, fresh initialization, and direct logits. They also dispense with the earlier logging prior during decoding. The comparison between observed and readable isolates the training label. The comparison against the bandit changes both training and decoding. No new RL was used here. Each epoch includes all positive roots and the same number of sampled standalone decisions. The 48 epochs run on Metal, and live inference and verification run on CPU.

Training data came from sum-bits and dot-product only. Sealed receipts reproduced both archived traces. Of 25,199 eligible actual proposal decisions, 1,898 had observed gain and 893 had gain with a reproduced boundary. All 654 held-out complete graph identities were removed from every training menu. The three evaluation programs are established development holdouts. [Observed model and provenance](observed/training.json) · [Readable model and provenance](readable/training.json).

### Actual signed execution

| Program | Signed commits, bandit / observed / readable | Reference | Paid tokens, bandit → readable | EPT, bandit → readable | Complete nonempty Runs, bandit → readable |
|---|---|---:|---:|---:|---:|
| fact | 1,268 / 1,256 / 1,257 | 1,668 | 3,789 → 3,759 | 0.2420 → 0.2442 | 65 → 66 of 163 |
| loopfact | 1,053 / 1,053 / 1,060 | 1,419 | 3,745 → 3,677 | 0.2192 → 0.2293 | 83 → 85 of 166 |
| sum-divisors | 8,794 / 8,785 / 8,928 | 17,341 | 24,744 → 24,545 | 0.2097 → 0.2243 | 203 → 218 of 627 |

On sum-divisors the readable selector earned 5,506 signed effective operations and left 8,413 commits to exact fallback. Mean recall over nonempty Runs rose from 54.14% to 55.99%. Across the three programs its pooled signed coverage was 11,245/20,428 (55.05%) and pooled EPT was 0.22723. Every assist arm matched ordered source execution, final graph and the exact effective-operation ledger. Per-Run attribution cross-checks the number of sealed signed plus residual receipts against that Run's teacher commit count. The final graph in search-free deployment still diverged in all three cases, first differing at Runs 7, 8 and 11. Sum-divisors still panicked at Run 85. [Summary](summary.json) · [Per-Run receipt counts](run-recall.csv) · [Assist counters and rejection reasons](assist.json) · [Exclusive trajectories](exclusive.json).

On the fixed sum-divisors trace, the intervention set contained 2,900 original residual commits. With a correct boundary, selectors chose layouts covering 50 (bandit), 162 (observed) and 121 (readable). Requiring the actual pointer's boundary recovered 10, 50 and 111 respectively. These are exact matches to recorded proofs on the previous policy's history. They do not identify the net change in a free live run. [Interventions](interventions.json).

### How much of the layout choice can Bake do?

In an offline ablation we circularly reassigned the selector's root context between opportunity roots with the same eligible menu and arity. The boundary reader continued to see the true fields. On sum-divisors 1,696 inputs changed, 362 decisions changed and 119 known residuals had both layout and boundary recovered, compared with 111 with the real fields. This single permutation motivated testing an entirely static layout score.

A separate model trains on the readable labels with zero root context for every example. Bake evaluates its trained logits on all templates once. The signed root still comes from the dynamic root Actor. At runtime the stored logits rank the eligible layouts once per active rule per Run, preserving template order for ties and the standalone option. Each selected graph still names dynamic boundary inputs and passes the same native checks. The static selector made 299, 307 and 1,308 menu choices for 3,333, 3,183 and 21,036 eligible root decisions respectively. Its signed commits were 1,246, 1,053 and 8,851. Aggregate EPT was 0.22708. It completed 68, 86 and 224 nonempty Runs. Its sum-divisors coverage was lower than that of the context-conditioned readable model even though it completed more Runs. [Static checkpoint and hashes](static/training.json).

Four alternating CPU trials per program compare exact-only, bandit, readable, static and teacher replay. Median signed operations/second on fact were 240.3, 278.7 and 310.5 for bandit, readable and static. On loopfact these were 206.9, 240.7 and 278.5. Both new arms won each of their eight comparisons against the previous selector. Median static total times were 2.96 and 3.03 seconds, versus 0.138 and 0.148 seconds exact-only and 0.139 and 0.144 seconds for the oracle. There is no paired timing result for sum-divisors. The raw timing keys original, refit and additional denote bandit, readable and static respectively. [Paired clocks](density.json).

### Reproduction

Use ROOT, BIN, WEIGHTS, BASE and OLD from the residual-entries study. EXP contains that study's expanded Bake catalog, the refitted bandit, and the five original assist traces. OUT is a fresh result directory.

```sh
python layout_targets.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BASE" "$EXP" "$OLD" "$OUT/data" --cases sum dot
for arm in observed readable static; do
  flags=(--labels "$arm")
  if [[ "$arm" == static ]]; then flags=(--labels readable --static); fi
  python train_layout_targets.py "$OUT/data" "$EXP/expanded" "$OUT/$arm" "${flags[@]}"
done
for arm in bandit observed readable static; do
  checkpoint="$OUT/$arm"
  if [[ "$arm" == bandit ]]; then checkpoint="$EXP/refit"; fi
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$EXP/expanded" "$OUT/recall/$arm" --policy "$checkpoint" --omit --attach --run-recall --cases fact loopfact sum-divisors
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$EXP/expanded" "$OUT/exclusive/$arm" --policy "$checkpoint" --omit --attach --exclusive --cases fact loopfact sum-divisors
done
for arm in observed readable; do
  python residual_boundary_audit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BASE" "$EXP" "$OLD" "$OUT/$arm-intervention.json" --policy "$OUT/$arm" --cases fact loopfact sum-divisors
done
python layout_target_report.py "$OUT" "$GOLD" "$OUT/report"
mkdir "$OUT/timing"
ln -s "$OUT/recall/bandit" "$OUT/timing/original"
ln -s "$OUT/recall/readable" "$OUT/timing/refit"
ln -s "$OUT/recall/static" "$OUT/timing/additional"
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$EXP/expanded" "$OUT/timing" "$OUT/density.json" --policy "$OUT/readable" --base-bake "$EXP/expanded" --base-policy "$EXP/refit" --additional-policy "$OUT/static" --cases fact loopfact
```
