# Selecting higher Cells by their realized native work

One offline contextual bandit estimates three outcome counts for a named graph at a proposed root. A directly suppressed independent proposal earns ownership credit only when its internal replacement actually commits. An accepted child with no observed competing external proposal receives the effective operations attributed to its native token. Failed internal checks are charged separately. A root that cannot bind its proposed graph receives zero child credit. Graph size alone earns zero. Pricing these predicted counts at 1 per uncontested effective operation, 0.25 per valid takeover and −0.0625 per failed internal check gives a score relative to issuing the standalone root. These are experimental utility prices. EPT uses the unweighted effective-operation ledger.

The sampler chose one action per decision in stochastic assist runs of sum-bits and dot-product, including standalone, the frozen readiness policy, and uniformly sampled sizes and layouts. All 6,719 held graph hashes were excluded from the sampling menus. Three seeds supplied 75,143 chosen graph actions for regression. Another seed on the same programs supplied 24,757 actions for selecting an epoch. The regressions share graph weights across the 54,156 layouts. They use the root port context, learned graph encoding, and static boundary, fanout and Run-group counts. The regressions estimate observed returns on sampled actions. Unchosen layouts receive no synthetic zero label. Native credit can depend on surrounding issuance decisions as well as the selected action. [Training records and hashes](training.json).

## Native assist with the frozen learned root-recovery head

Both policies use the same root recovery, compiled graph library and boundary pointer. They suppress verified internal claims through the existing ownership path and can attach independent successors. Each checked run reproduced the source schedule, ordered RHS, effective writes, resumes, events, state hash and four-component effective operation ledger. The ordinary residual search completed outstanding bindings separately. Each named certificate was checked without a search for missing parents.

| Development workload | Distinct signed commits, readiness → receipt | Required | Signed effective operations | Paid external tokens | Fully signed nonempty Runs |
|---|---:|---:|---:|---:|---:|
| fact | 1,422 → 1,417 | 1,668 | 1,047 → 1,058 | 4,539 → 4,550 | 106 → 107 |
| loopfact | 1,204 → 1,165 | 1,419 | 974 → 939 | 4,473 → 4,252 | 109 → 100 |
| sum-divisors | 9,663 → 9,720 | 17,341 | 5,826 → 6,273 | 27,943 → 27,851 | 233 → 252 |

Pooled EPT rose from 0.21234 to 0.22563 and signed commit coverage from 60.16% to 60.22%. Complete instances of six to eight steps rose from zero to 34. No nine- or ten-step instance finished. Confirmed owned children rose from 89 to 188, uncontested internal effective operations from 253 to 774, and failed internal step checks fell from 15,628 to 7,956. Completed instances of layouts held from training fell from 163 to 28. The bulk of the pooled effective-operation gain came from sum-divisors. Two of three programs lost distinct signed bindings. [Assist counters](assist.json) · [Summary](summary.json) · [Per-Run recall](run-recall.csv).

Exclusive had no independent search calls. Both policies first diverged at Runs 9, 10 and 11 respectively. The receipt policy encountered source panics on its incomplete states at Runs 72, 58 and 97. None reproduced the complete reference. [Exclusive reports](exclusive.json).

Four alternating single-CPU pairs per program include model preparation, native verification and residual execution. Median signed effective operations/second on fact changed from 118.96 to 117.45 (two wins in four), and on loopfact from 111.11 to 116.95 (three wins in four). Median total time on fact was 8.80 versus 9.01 seconds (exact 0.164, oracle 0.169). On loopfact it was 8.80 versus 8.03 seconds (exact 0.168, oracle 0.171). On sum-divisors the boundary reader scored 16,568,050 ports in the readiness arm and 24,694,291 in the receipt arm. These reads are outside EPT. Sum-divisors has one audited execution per arm and no paired timing. The earlier 5,011-layout margin-only arm used a different root policy and achieved higher aggregate coverage. [Paired timings](density.json).

## Credit for commits versus effective operations

A separate fit replaced the first regression target with the number of uncontested signed child commits. The same logging data, split, prices, graph features, pointer, verifier and deployment budget were used. This control reached 1,407, 1,176 and 9,762 distinct signed commits on the three programs (12,345 / 20,428 overall). It produced 8,233 attributed effective operations for 36,742 paid packets, EPT 0.22408. It completed 462 nonempty Runs, including 250 on sum-divisors, and 30 graph instances at sizes six or above. It had 289 confirmed owned children and 10,502 failed internal probes. This arm has no paired timing. [Commit-target training](commit-training.json) · [Three-arm results](summary.json).

## Single-decision controls

Two illustrative decisions were selected on the training workload sum-bits after observing their local receipts. For each we reran the policy, changing only that decision to a standalone root. The digest of all preceding sealed frames, named requests and proposed layout choices through the decision had to match. Both branches completed the entire program with the exact source schedule and effective ledger. These selected successes do not estimate a population-average causal effect.

At Run 118 a seven-step Cell committed all six children and suppressed proposals for four of them. Compared with the standalone fork, the complete rollout had two fewer paid packets, equal signed commit count, and two fewer signed effective operations. At Run 668 a six-step Cell was credited with four uncontested effective operations. The standalone fork had exactly the same total signed commits, paid packets and signed effective operations. Alternate owners can replace locally credited work. The policy trained here predicts the local receipts. A marginal reward for the full workload needs the difference between branches. [Matched forks](fork.json).

## Reproduction

ROOT, WEIGHTS and BAKE are the training corpus, frozen root Actor and full consumer-graph catalog. BIN is the native receipt-enabled EPT receiver. RECOVERY is the frozen learned prefix-recovery checkpoint. GOLD holds native reference ledger exports. OUT is a fresh experiment directory.

```sh
python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/logs" --explore --omit --attach --recovery "$RECOVERY" --cases sum dot --seeds 1703 1709 1721 1733
python receipt_value.py "$OUT/logs" "$BAKE" "$OUT/compiled"
python receipt_value.py "$OUT/logs" "$BAKE" "$OUT/commit-policy" --target commits
for arm in baseline learned commits; do
  flags=()
  if [[ "$arm" == learned ]]; then flags=(--policy "$OUT/compiled"); fi
  if [[ "$arm" == commits ]]; then flags=(--policy "$OUT/commit-policy"); fi
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/$arm" --omit --attach --recovery "$RECOVERY" --run-recall "${flags[@]}" --cases fact loopfact sum-divisors
  python layout_credit.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/exclusive/$arm" --omit --attach --recovery "$RECOVERY" --exclusive "${flags[@]}" --cases fact loopfact sum-divisors
done
python receipt_report.py "$OUT" "$GOLD" "$OUT/report" --cases fact loopfact sum-divisors
mkdir "$OUT/timing"
ln -s "$OUT/baseline" "$OUT/timing/attach"
ln -s "$OUT/learned" "$OUT/timing/rl"
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/timing" "$OUT/density.json" --policy "$OUT/compiled" --recovery-dir "$RECOVERY" --cases fact loopfact
python receipt_fork.py "$ROOT" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/compiled" "$RECOVERY" "$GOLD" "$OUT/fork.json" --case sum
```
