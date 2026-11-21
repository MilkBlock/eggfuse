# Reinforcement learning at RipSat token issuance

The recursive generator can seal either an ordinary root or the checked
143/op1 → 55 → 143 completion in each eligible root token. The parent, its
version, and the compiled program are available before the token is issued.
A Bernoulli policy uses a bias, log page count and log age of the named parent.
The bit is stored in the existing tagged parent word; tokens on the same page
can choose different actions. Rust decodes the same parent and independently
checks the selected program. Only an actual fresh Let/Set port can supply a
later child at its original Run. All other root kinds use their normal path.

## Reward and training

Each training episode replaces the initial graph with randomly generated Get
facts, optional already-known Single facts, and possibly their already-known
reverse Get. It runs four always-run stages with the actual rule code. The
fixture override requires an explicit training environment and is unavailable
in bundle inference. Training uses no held-out executions. The compiled donor
supplies the rule semantics and the existing root generator.

Two native executions start from the same generated graph: force leaf for
every root, then sample an action for each eligible issued root. Count all
external single/multi proposals and independently paid child tokens in both
runs. Compare ordered RHS, effective writes, Spine resumes, source events,
schedule, final state and endpoint origins. Credit a sampled root once per
independent child proposal actually removed, using the signed child commit's
original root serial. For this action family, the sum of root credits must
equal the net difference in paid packets. Reused, stale and rejected attempts
earn zero. A new action with displaced or additional proposals would need a
signed debit in this ledger before it could use this attribution.

PyTorch updates the actor by REINFORCE, minimizing the negative sampled action
log-probability weighted by its realized credit, averaged over issued decisions.
The seed controls generated inputs and sampled actions. Only the actor head is
updated. Offline MPS training requires CPU fallback disabled. GPU job 2904
failed on its first forward in Apple's Metal compiler service (error 141).
The recorded checkpoint is the explicit PyTorch CPU training control. Frozen
deployment runs the policy and verification in the single-threaded Rust Cell
session. The endpoint is the standalone EggFuse Pass 3 runtime.

## Measured controls

Training had 48 generated starting graphs, 633 token decisions, 403 composed
actions and 282 fewer external proposals, including 141 terminal steps. The
initial policy chose leaf everywhere in greedy mode; the trained policy chose
the licensed larger Cell at every eligible held-out issuance. Its performance
therefore equals the forced-full control for this family.

| Full source workload | Leaf packets | Trained packets | Fewer external proposals | From the second hop | Strict FEPT, leaf → trained |
|---|---:|---:|---:|---:|---:|
| sum-bits | 12,662 | 12,601 | 61 | 26 | 0.212526 → 0.213554 |
| 3mm | 558,074 | 555,913 | 2,161 | 932 | 0.166032 → 0.166677 |

The earlier signed completion could already attain these numbers when forced
on. The experiment measures learning the issuance decision and verifies its
credit. It covers one authenticated cross-Run family. The mixed-action
holdout tests score the same frozen weights with sampling instead of greedy
selection. Staling the second port restores precisely the terminal proposals.
The comparison excludes the trace-Bake library to isolate the policy's action.

Native CPU medians in milliseconds, four measured trials after warmup.
RSS columns give median first passage at the same calibrated incremental RSS,
with four fresh sampled and four unsampled trials per arm. Resident request
times including setup and response are in the timing artifact.

| Workload | Exact search | Leaf | Learned | Leaf RSS time | Learned RSS time |
|---|---:|---:|---:|---:|---:|
| sum-bits | 20.34 | 30.45 | 30.62 | 24.72 | 24.67 |
| 3mm | 875.22 | 1692.31 | 1699.80 | 981.67 | 985.60 |

[Trained actor and all episode returns](actor.json) · [Source and packet controls](results.json) · [Canonical source checks, stale port, CPU timing and RSS](performance.json)

## Reproduce

Run with the external worktree launcher and the shared experiment queue. The
GPU training command is the default. Select `--device cpu` explicitly for
the recorded control. Use fresh output directories.

```sh
e=/Volumes/EggFuseWorkspace/experiments
d=benchmarks/pass3-cell-gpu/ripsat-issuance-rl
o="$e/new-issuance-rl"
job() { ~/.local/bin/eggfuse-job run --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse "$@"; }
job env PYTHONPATH=benchmarks/pass3-cell-gpu/joint-witness python "$d/build.py" "$o/native"
job env EGGFUSE_GENERATED_GET_EPISODES=1 PYTORCH_ENABLE_MPS_FALLBACK=0 python "$d/study.py" train "$e" "$o/native/session" "$o/train"
job python "$d/study.py" evaluate "$e" "$o/native/session" "$o/test" --checkpoint "$o/train/actor.json"
job python "$d/measure.py" "$e" "$o/native/session" "$o/timing" "$o/train/actor.json" "$o/test/results.json"
```
