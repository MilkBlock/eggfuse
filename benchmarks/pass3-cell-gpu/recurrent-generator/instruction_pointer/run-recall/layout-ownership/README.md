## Training a single policy on native RipSat Cell ownership

The policy takes the current root's named port fields and a frozen Bake graph encoding. The graph has one source rule occurrence per step, a source Run group, external boundary slots and edges to actual returned instruction positions. A shared key projection adds step count, boundary arity, group count and edge count. The standalone action competes with all statically compatible layouts. No action-specific weights are learned. The frozen catalog has 4,096 layouts of two through ten rule occurrences, including joins and same-Run siblings. The shared boundary pointer signs independent inputs once. Root discovery, boundary-pointer weights and catalog extraction were frozen in this experiment. [Catalog and extraction](../unified-layouts/README.md).

### Credit and training

The native receiver exposes already signed internal requests at the sealed Run boundary. After independent proposal decoding, an identical ordered rule and versioned premise tuple can suppress a standalone request. When the new proposal carries additional independently chosen successors, it remains a paid graph certificate. Its root can adopt the signed step and consume that step's actual return. Rust still verifies signed steps and checks source visibility and scheduling. Generating the root and reading its inputs still cost time even if sending it is suppressed.

We collected twelve stochastic native assist trajectories from sum-bits and dot-product. Exploration allocated 40% probability to the previous greedy choice, 15% to standalone, and 45% uniformly across eligible graph sizes then uniformly across layouts of that size. 534 full layouts were excluded from every exploration menu and the resulting loss. The assignment was fixed by graph digest before training. The three evaluation programs have been used as development holdouts in earlier iterations.

A root earns one point for each verified internal step replacing an omitted external proposal. Otherwise an accepted internal step earns its attributed effective operations if no external alternative was observed. An unsuccessful internal verification costs 1/16 point. The two positive terms are mutually exclusive for a step. Awaiting a future Run earns no future credit at the end of a source program. This reward measures observed local ownership and effects. Interference among independently sampled graph choices can change global attribution, so an individual reward does not establish a paired causal estimate. The reward also omits pointer calculation time.

A shared critic fit 75,214 choices from three seeds per program. A separate shared policy fit 75,161 choices from the other three seeds per program. Of these respective samples, 700 and 681 had positive realized return. The policy uses a propensity-corrected contextual bandit objective with a learned value baseline, capped importance ratio of eight and KL weight 0.03. Both networks used backpropagation on Metal. Deployment takes the greedy action on CPU. Held-out layouts become eligible during deployment. [Training hashes and sample splits](training.json) · [Policy weights](policy.pt).

### Native assist and exclusive execution

The baseline and trained policy below both have ownership feedback, omission and successor attachment enabled. EPT counts four kinds of effective operation attributed to signed external or internal tokens and charges every issued external packet. The residual search gets no signed credit.

| Program | Signed commits / reference, baseline → trained | Signed operations | Paid packets | EPT | Trained residual commits |
|---|---|---|---|---|---:|
| fact | 1,264 → 1,261 / 1,668 | 908 → 911 | 3,803 → 3,787 | 0.2388 → 0.2406 | 407 |
| loopfact | 1,050 → 1,058 / 1,419 | 813 → 831 | 3,732 → 3,755 | 0.2178 → 0.2213 | 361 |
| sum-divisors | 8,721 → 8,758 / 17,341 | 5,013 → 5,167 | 24,812 → 24,715 | 0.2020 → 0.2091 | 8,583 |

Under the previous selector, completed instances comprised 904 two-step, eight three-step and one nine-step Cell. The new policy completed 907 two-step, 66 three-step, three four-step, two six-step and one nine-step Cell. Across programs it completed 57 distinct layouts, including six held out of training. A total of 32 completed instances used these six held-out layouts. The trained policy issued 91 distinct layouts. These are live model selections. They have a different denominator from the number of baked layouts or the training examples. [Native graph and credit breakdown](summary.json).

With the old selector, suppressing only plain proposals saved 5, 2 and 25 packets with the same signed operation totals as retaining all proposals. Successor attachment changed which subsequent packets could commit. Audited assist execution reproduced every program's source schedule, ordered RHS, writes, resumes, event stream, final state hash and effective-operation ledger. Under the trained policy the exact fallback still examined 1,845, 1,626 and 22,677 candidates respectively. [All four assist arms and rejection reasons](assist.json).

In search-free deployment both selectors first diverged from the reference at Runs 7, 8 and 11. Neither recovered the final graphs. Sum-divisors reached the same source panic at Run 85. [Exclusive outcomes](exclusive.json).

### Throughput

Four alternated end-to-end CPU pairs per program included exact-only, baseline graph policy, trained graph policy and teacher replay. Median signed operations/second rose from 247.6 to 262.1 on fact and from 240.6 to 256.4 on loopfact. The trained policy won each of the eight comparisons with the baseline graph policy. Median trained assist time was 3.48 and 3.24 seconds respectively, versus 0.145 and 0.144 seconds for exact-only, and 0.147 and 0.136 seconds for the teacher oracle. No paired throughput result was collected for sum-divisors. [Paired timings and component costs](density.json).

### Reproduction

Use the programs, training weights and frozen catalog from the linked catalog study. Build the cell_token_replay release example with feature cell-token-ept. The binary for the archived measurements preceded the source-compatible public API wrapper for enabling layout feedback. All experimental arms used the same receiver build. ROOT is the instruction-pointer study's program export, BAKE its frozen catalog and OUT a fresh output directory.

```sh
for c in sum dot; do
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/ept-logs" --cases "$c" --explore --omit --attach --seeds 1703 1709 1721 1733 1741 1753
done
python train_layout_bandit.py "$OUT/ept-logs" "$BAKE" "$OUT/learned"
for arm in retain plain attach rl; do
  flags=()
  case "$arm" in plain) flags=(--omit);; attach) flags=(--omit --attach);; rl) flags=(--omit --attach --policy "$OUT/learned");; esac
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/final/$arm" --cases fact loopfact sum-divisors "${flags[@]}"
  if [[ "$arm" == attach || "$arm" == rl ]]; then
    python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/exclusive/$arm" --exclusive --cases fact loopfact sum-divisors "${flags[@]}"
  fi
done
mkdir -p "$OUT/gold"
for c in fact loopfact sum-divisors; do
  "$BIN" reference "$ROOT/$c/program.json" - audit --ept > "$OUT/gold/$c.json"
done
python layout_credit_report.py "$ROOT" "$ROOT/sum" "$BAKE" "$OUT" "$OUT/summary.json"
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/final" "$OUT/density.json" --cases fact loopfact --policy "$OUT/learned"
```
