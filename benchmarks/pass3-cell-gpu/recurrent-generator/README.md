# Recurrent neural Cell proposals and verification on the full Pass 3 schedule

A two-row neural actor now runs before **each** scheduled GPU search. Each row outputs a latent vector of width 8, a Bake leaf, a physical anchor row, a candidate position and an activation bit. The exact next neural call reads the preceding generated token from alternating device buffers. Ordered effects update the real graph. The following Run sees that graph and the actor's own token, including proposals that were rejected. The actor gets the source ruleset and a bounded bank of possible typed addresses, including stale, hidden and unmatched candidates. It selects the template and anchor together. It receives no completed bindings, observed RHS, verification truth or CPU-generated history. [Readable PyTorch actor](model.py) · [Metal forward and verifier](actor.metal)

The study reuses the 32-leaf sum-bits Bake catalog, admitting only compatible typed rules with a checked device entry in each program. The policy scores up to eight physical rows per template; another 2-row forward occurs at the next source Run. This is a **restricted neural proposal domain**. Residual exact search normally completes outstanding obligations and supplies most bindings. The online process needs only the device image, address/port weights, the static certified catalog and the frozen actor. The two checkpoints each have 783 parameters and train only on windows from four source families, for 480 updates. Labels are source winners observed after the Run. Each training unroll feeds its own generated frontier back into the next step. Source rows in the unrolled observation stream come from an exact reference trajectory. Sum-bits is the original library donor, not an unseen-library test. [Training](train.py) · [Reachable obligations](opportunities.json)

## What the generator actually contributed

| Real workload | Source Runs | All committed RHS bindings | Neural winners, seeds 1703 / 1709 | Remaining exact, seed 1703 | Resident exact / joint ms, seed 1703 |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 1,428 | 7,265 | 58 / 59 | 7,207 | 863.0 / 975.5 |
| dot-product | 1,535 | 6,704 | 48 / 47 | 6,656 | 886.3 / 1,017.1 |
| gemm-bias-relu (held out) | 1,652 | 15,462 | 44 / 43 | 15,418 | 2,789.4 / 2,925.4 |
| stable-argmax (held out) | 1,149 | 8,190 | 35 / 34 | 8,155 | 925.5 / 1,059.7 |

On sum-bits seed 1703 the actor emitted 136 non-null proposals. The verifier rejected 26, discarded 52 duplicates and accepted 58. Each accepted token in this arm won a real RHS ordinal. The verifier checks source scheduling, visibility, epoch, original cursor, literals, repeated slots and any certified point reads before projecting the binding. The accepted record goes to the normal token bank. With coverage enabled, the exact routed search skips that specific validated (rule, pivot, witness). Every other entry continues normally. The source ordinal, rule and original anchor of **each** neural winner are independently checked. Full schedule, ordered RHS inputs, effective writes, actual Spine resumes, union sequence, class roots and final graph match the previously CPU-aligned engine. [Ordinal proof](provenance.json) · [Two-seed raw counts and ten paired samples per timed arm](results.json)

## What the interventions say about cooperation

* **Change the actor, hold verification fixed.** Zeroing only the previous generated latent, keeping discrete source fields, changes 20 / 34 sum-bits row decisions across the two seeds. The resulting neural winner counts are still 58 / 59. Both seeds on all four programs were also run with swapped row latents. An independent PyTorch rollout starts at zero and consumes its own token throughout; its discrete outputs agree with Metal across the intact, masked and swapped conditions. This shows a causal effect on decisions. Useful coverage did not reliably improve. [Independent rollout parity](parity.json)
* **Change the verifier, hold the proposals fixed.** A positive-only verifier admits the same valid proposals and leaves exact enumeration open. The coverage verifier also closes each admitted leaf entrance. Raw neural tensors match between these arms. On sum-bits seed 1703 it skips 58 entrances and 59 duplicate suffix steps; the verifier itself executes 99 steps, including failed proposals. This saves too little to repay the actor and verifier. A shadow control validates proposals and withholds their bindings, and the normal engine again supplies every RHS. An all-null actor is a separate fallback control.
* **Turn off exact completion.** On all four programs, the isolated seed-1703 neural-only run produces zero RHS bindings, diverges on Run 1 and stops after 208 source control occurrences. The empty-LHS initialization obligation lies outside the action library. Even on the exact assisted trajectory, only 742 of the 7,265 sum-bits winners have a source witness in the available candidate positions. Their concentration in 105 Runs limits two slots to 181 such reference winners at most. This is a candidate/throughput ceiling on that trajectory, not an autonomous accuracy estimate. [Isolation and failed autonomous rollout](isolated.json)

The clearest next comparison is to expand executable proposal coverage, including initialization/ordinary entries, and expose validated task closures to the next neural wave. Measure accepted novel work, duplicated work, exact completion and whole-pass time separately. These results do not establish the diagram 42 composed-action or diagram 43 variable-port comparison.

## Full Pass 3 follow-ups

The [receipt study](receipts/README.md) follows the generated token across several waves of the same source Run. The [composed-certificate study](receipts/composable-proposals.md) gives a separate coverage denominator for multiple RHS per certificate, with an example tied to the actual producer effect ports, and measures frozen policies over 1–16 waves. It also registers the pending-parent versus wave-verified comparison; that online comparison remains open.

## Reproduction

Use the external workspace environment with MPS fallback disabled. Each output directory below must be new.

```sh
ws=/Volumes/EggFuseWorkspace
corpus="$ws/experiments/repair-bake-families-20261120"
ref="$ws/experiments/pass3-atlas-integration-20261120"
reader="$ws/experiments/rotary-axes-20261119/packed-1703/final.pt"
dir=benchmarks/pass3-cell-gpu/recurrent-generator
out="$ws/experiments/NEW-recurrent-leaf"
python "$dir/capture.py" "$corpus" "$ref" "$reader" "$out"
for seed in 1703 1709; do python "$dir/train.py" "$out" "$out/train-$seed" --seed "$seed"; done
python "$dir/study.py" "$corpus" "$ref" "$reader" "$out" "$out/paired"
python "$dir/rollout_check.py" "$out" "$out/paired" "$out/rollout-check.json"
python "$dir/provenance.py" "$corpus" "$ref" "$reader" "$out" "$out/paired" "$out/provenance"
python "$dir/isolate.py" "$corpus" "$ref" "$reader" "$out" "$out/isolated"
```

Timing includes proposal, verification and exact completion over the same static GPU budget; state reset and oracle comparison are outside the timed interval. Ten resident repetitions per timed arm rotate order. The isolation worker copies six input files and denies access to the experiment directory. CPU verification is post-run. Frozen native weight arrays are in [seed 1703](actor-1703.json) and [seed 1709](actor-1709.json).
