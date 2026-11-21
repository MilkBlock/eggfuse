# Learning where a signed Cell should stop

A root issuer chooses a leaf, the signed fresh Let prefix, or the Let and Set
continuation of 143 → 55 → 143. The word of the selected root carries the
choice before verification. A prefix can open the first internal entry with
the existing block verifier. Its permit prevents Set capture on the middle
RHS. The ordinary source still executes the Set; its consumer needs an
independent proposal. The full choice also licenses the second entry if the
actual fresh output survives. No choice predicts a successful mutation or
waives source validation.

## Credit and training

Each issued root gets a sequence of stop/extend decisions. A shared linear
logit uses the named parent's physical operation-index class, the checked
edge kind, the consumer input width, and prefix position. An index match is
only a policy feature: two different producer templates may have the same
operation index. The verifier uses the physical parent and version. The frozen
greedy decision for each of the two observable classes is computed at Rust
session configuration. Issuance reads the resulting prefix length. Sampling
uses the same logits before each extension.

Train with on-policy Bernoulli REINFORCE, an exponentially averaged baseline per
position and undiscounted reward-to-go. The return to the first decision
includes realized work at the terminal. The second decision receives only its
own marginal result. A receipt counts only for its actual committing root.
For each of 144 random episodes the runtime executes the sampled policy and a
leaf-only intervention on identical generated inputs. Their ordered effects and
final state must match. Credit summed over roots must agree exactly with the
difference in external packets and root-verifier header checks, minus named
receipt row reads and actual root registrations. The per-root attribution maps
are populated only in sampled training. An optional price can further penalize
reserved edges. The reported experiment uses zero price.

The reward counts four kinds of work in unit weights. It does not estimate
nanoseconds or include every runtime cost. An actual row decode may cost more
than one header probe. Native timing and fresh-process RSS controls are
independent outcomes. Training uses the original rule code on generated inputs;
both complete EggCC workloads are held out from training. Here the native
authorization supports two ordered edges. Further sizes need real compiled
edges and matching verifier permissions.

## Reproduction

From the external GPU-session worktree, use a fresh experiment directory.

```sh
e=/Volumes/EggFuseWorkspace/experiments
o="$e/new-scale-policy"
d=benchmarks/pass3-cell-gpu/ripsat-scale-policy
job() { ~/.local/bin/eggfuse-job run --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse "$@"; }
job env PYTHONPATH=benchmarks/pass3-cell-gpu/joint-witness python "$d/build.py" "$o"
job env EGGFUSE_GENERATED_GET_EPISODES=1 PYTORCH_ENABLE_MPS_FALLBACK=0 python "$d/study.py" train "$e" "$o/session" "$o/actor.json"
job python "$d/study.py" evaluate "$e" "$o/session" "$o/results.json" --checkpoint "$o/actor.json"
job python "$d/controls.py" "$e" "$o/session" "$o/actor.json" "$o/controls.json"
job python "$d/controls.py" "$e" "$o/session" "$o/actor.json" "$o/clock.json" --verifier-clock
```

Use `--device cpu` explicitly to reproduce the CPU training control. The local
MPS job failed allocating its first training tensor because Metal could not
reach MTLCompilerService. All published inference timings use the native
single-threaded Rust runtime. Each resident arm is warmed, then timed five
times in rotating order. The independent vanilla oracle checks ordered RHS,
writes, union, Spine, schedule, Run count and final graph.

## Results

| Full native Pass 3 | sum-bits previous → learned | 3mm previous → learned |
|---|---:|---:|
| Registered root blocks | 194 → 169 | 5,413 → 4,081 |
| Independent proposals eliminated vs leaf | 61 → 59 | 2,161 → 2,103 |
| Header checks | 50,536 → 50,543 | 2,023,730 → 2,023,933 |
| Receipt rows read | 61 → 59 | 2,161 → 2,103 |
| Net counted work saved vs leaf | 15 → 33 | 2,002 → 3,131 |
| End-to-end native median, ms | 30.88 → 30.90 | 1,647.74 → 1,684.28 |
| Exact search median, ms | 20.64 | 852.82 |

Forcing the one-edge prefix gives negative net work on both workloads
(−115 and −2,658). The second edge makes the full program profitable in the
same units. Training a greedy decision using just immediate first-edge reward
would miss this opportunity. The learned policy selected either zero or two
edges on these targets. Both reach the same source results with zero exact RHS
residuals; the old policy saves more independent proposals. The new policy
improves the unit-weight work objective but fails to demonstrate an end-to-end
speedup. It remains an opt-in experiment.

The credit regression also exercises a 64-edge fabricated trace with a stopped
sibling and duplicate-credit rejection. This checks the reward implementation
only. Native execution and speed measurements here cover up to two licensed
continuations. [Frozen weights and training history](actor.json) ·
[Native audit and per-trial times](results.json) · [Sampled RSS controls](controls.json).

The single-witness verification clock in six separate alternating trials
moved from 2.185 to 2.180 ms on sum-bits and 140.78 to 135.94 ms on 3mm.
This clock excludes other verification and graph execution. Median first
passage to the calibrated incremental RSS moved from 25.28 to 24.86 ms and
1,016.75 to 1,023.52 ms respectively. Staling the second port restores 25
and 903 external proposals under the learned policy and preserves ordered
source execution. [Verification clock trials](clock.json)
