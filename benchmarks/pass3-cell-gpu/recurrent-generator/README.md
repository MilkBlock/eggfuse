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

The [receipt study](receipts/README.md) follows the generated token across several waves of the same source Run. The [composed-certificate study](receipts/composable-proposals.md) gives a separate coverage denominator for multiple RHS per certificate, with an example tied to the actual producer effect ports, and measures frozen policies over 1–16 waves. The [pending-parent experiment](pending/README.md) now measures that comparison on the same trained actor and checks every resulting child against its actual source publication.

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

### Issuing a three-step Bake Cell

The opt-in action bank adds donor unit 41 (143 → 55 → 143) alongside
its pair prefix. Each consumer here has a single query atom bound by the
previous effect. The existing actor scores both actions. Their wire selectors
differ so a frozen token uniquely identifies the chosen recipe. The train
split contains 161 positive paths for unit 41. At a given root a full path
supersedes its matching prefix target. Other outgoing paths remain eligible.
Training uses the existing supervised set loss on the CPU.

The verifier queues the first consumer on the actual producer return. A winning
middle RHS can enqueue its own return for the terminal consumer. Both claims
check the returned row, publication ticket, scheduled rule and winning binding.
The terminal uses a second claim slot with no additional generator row. This
implementation reserves a second claim and queue bank when chains are enabled.

The six paired runs used the checked-in policy, the ordinary source schedule
and the full exact residual. The serial C++ diagnostic executes the grid kernel
bodies on CPU. It does not measure device timing or GPU concurrency. In each
workload one generated token with a committed terminal was shortened during
frozen replay. All root and middle winners and all other terminal winners
survived. Each shortened token cost exactly one additional exact RHS match.
Both arms matched the reference schedule, ordered RHS inputs, effective writes,
Spine resumes, unions and final visible row contents. The paired artifacts
separate evidence available before the consumer Run from the later target.
The actor has not been trained on these counterfactual stop/continue labels.

[Policy](three-step-policy.json) · [Six workload results](three-step-comparisons.json)

Reproduce with the shared compute queue and external worktree launcher.
Here `e` is the experiment root and `d` is this directory. Use a fresh output
directory. Omit `--serial-cpu` to request Metal execution.

```sh
python "$d/chain_check.py" "$e/repair-bake-families-20261120" \
  "$e/pass3-release-reproduction-20261120" "$e/rotary-axes-20261119/packed-1703/final.pt" \
  "$d/three-step-policy.json" "$e/new-three-step-sum" --case sum-bits --serial-cpu
```

### Recursive Bake actions, named boundaries and measured issuance returns

The default supervised trainer compiles every composed unit observed in its
training split. The previous three-step checkpoint remains loadable. The four
training families have 560 three-step and 106 four-step paths. There are six
three-step recipes and one four-step recipe. The compiler interns their suffixes
and checks effect-to-pivot table compatibility. Claim storage grows with the
maximum number of hops in the catalog. Explicit unit lists still support ablations.

Capture records the matched physical row, epoch and publication ticket for
each relational query atom of the source winner. Target generation records
external inputs, all observed returned ports and individual outside uses.
A ticket can move to a surviving row during repair. The recorded consumer
address preserves that distinction. The source engine still publishes ordinary
effects. The takeover changes the route supplying the input binding.

On an actual producer return a side input with a determined functional key
can be named by one point lookup. The consumer checks that physical row, epoch,
visibility and fields. If the name is missing or expires, exact matching can
still supply the binding. A free relational join without a certified donor
Entry lies outside this action bank. The named-input buffer in the experiment
costs 98,312 bytes per execution. Source-witness capture is optional audit
instrumentation.

In the reference-selected affine-twins receiver check, 82 complete recipes
ran across seven separate interventions. Unit 44 consumed the two expected
external tuple-length witnesses. Staling one signed version removed precisely
one internal winner. Unit 48 completed four steps 15 times. All witness arrays
and public returns matched the source, including outside consumers. The 973
outside uses are counted across instances and interventions. These results
measure verifier capability on known eligible inputs. [Per-recipe controls](recipe-boundary-results.json)

**Return training.** At a prospective decision the recursive actor executes
two trajectories from identical preceding token streams and identical current
root rows. One arm selects the action, the other its pair prefix or silence.
Later tokens are generated afresh in both arms. All 56 pairs preserve the
reference schedule, ordered RHS inputs, writes, Spine, unions and final rows.
The initial 14 pairs explore each composed unit on visible root candidates.
The following 42 pairs use ordinarily generated roots and compare a non-null
child against silence. The trial selector uses no later outcome. The policy
receives the measured difference in active tokens plus residual exact RHS
bindings, charging one unit each. The trainer differentiates the expected
return under the two actions' conditional softmax and reuses measured
decision contexts between episodes. It updates the original child scores,
row biases and null score. Ten actions in the full arms obtained zero child
commits. No future label enters inference.

Across six comparison workloads the frozen return-trained policy emitted 63
fewer tokens and incurred 32 additional exact RHS bindings, improving that
objective by 31 units. Completed three/four-step instances fell from 29 to
24. Earlier exploratory training on long actions alone regressed on this
comparison; these workloads are reused comparisons. These are operation
counts for the standalone serial CPU kernel control. They do not establish
Rust-runtime or GPU speedups. Apple Metal shader compilation failed to reach
MTLCompilerService (error 141). [Frozen policy](baked-returns-policy.json) ·
[Workload and training results](baked-returns-results.json)

Run the following commands using the shared compute queue and worktree launcher,
with fresh output directories. Set `e` to the experiment root, `d` to this
directory, and `ref`, `corpus`, `reader` as in the capture commands above.

```sh
python "$d/compose_capture.py" "$corpus" "$ref" "$reader" "$e/compound-boundary-capture-v1" --splits train development --serial-cpu
python "$d/compose_targets.py" "$corpus" "$ref" "$e/compound-boundary-capture-v1" "$e/compound-boundary-targets-v1"
python "$d/compound_model.py" "$ref/sum-bits/program.json" "$e/recurrent-receipts-20261120" "$e/compound-boundary-targets-v1" "$e/new-supervised" --seeds 1703
python "$d/recipe_check.py" "$e" "$e/new-supervised/train-1703/policy.json" "$e/new-recipe-check"
python "$d/issuance_returns.py" "$e" "$e/new-supervised/train-1703" "$e/new-returns" --updates 56
python "$d/returns_evaluate.py" "$e" "$e/new-supervised/train-1703/policy.json" "$e/new-returns/policy.json" "$e/new-eval" --cases histogram-scatter gated-state sum-bits dot-product gemm-bias-relu stable-argmax
```
