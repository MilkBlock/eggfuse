# Can a merge reward teach a small Cell to become an executable composite?

This ablation trains the admission head at an actual parent publication. The source CPU proposer, the four compiled producer/effect interfaces, the recursive SubTuple template, and the checked cross-Run evaluator are frozen. The head emits a binary decision for one candidate instance. When selected, the continuation can avoid a consumer entrance, a repeated root check and the standalone child recipe. Each true source RHS, intermediate value still visible to external readers, union and scheduled boundary remains observable. This measures execution composition. The physical owner-retirement experiment charges a different operation.

## Native labels and the counterfactual

The donor library and the four training programs are separate from the evaluation programs. Training uses source executions from four diversity fixtures, including a paired ordinary-leaf and all-composed pass through the Rust engine. A generation identifies one published owner and its producer rule, effect, immutable integer, source generation and stable root. The source-matched child ledger supplies both positive and unconsumed outcomes. Only fields observable on publication are model inputs. Future winners, numbers of probes, physical addresses, ordinals and test traces are absent from the input vector.

The 689 observed publications contain 295 distinct won child occurrences and 52 distinct input vectors. In 21 groups, the same vector has both a positive and a negative outcome. These groups contain 525 offers. Even a deterministic classifier memorizing every feature vector makes at least 181 mistakes on these labels. The label asks whether the selected parent later won the consumer, which also depends on future scheduling and competing support. [Training publications](training-events.json) · [Feature support](feature-support.json)

A later child win and a useful composition can be different labels. Under forced composition, 7,632 of the 9,157 suppressed entrance visits in these four native programs belong to published parents that never won a child. A proved-inapplicable branch can save many repeated visits. Conversely the four frontiers performed 13,029 header scans, including scans of owners outside the selected family. Paying only for child wins misses the first effect; charging only owned header rebuilds misses the second.

## Warm start and reward matrix

Each seed trains a nine-scalar linear gate in PyTorch. Both curricula spend 80 updates on supervised initialization, then 120 updates on the same sampled native rows, with batch size 96 and Adam at 0.025. All reward arms share the seed-specific minibatch schedule and the same source budget. The real warm start samples training publications. The synthetic warm start constructs small scheduled Cell episodes using the same static port interfaces. A CPU interpreter applies publications, changes of generation, optional external reads and later consumer Runs. Only a prior winning greater-than branch may supply the synthetic recursive depth increment and decremented integer. Changed generations, unconsumed ports and competing parents can yield zero credit. The simulator gives local structural labels. Native execution supplies all performance claims.

Each full-data checkpoint has the same BCE supervision on whether this generation later wins. The four added rewards are compared to that supervision alone. A Bernoulli gate has exact expected bonus `p(compose) * advantage`; the optimizer differentiates this expectation directly.

| Arm | Additional benefit of selecting a parent |
|---|---|
| prior | zero |
| offer | one unit per selected parent |
| settled | one unit per distinct, verified child win |
| work | suppressed entrance visits, plus the repeated seals and separate child packets saved, less covered-source header rebuilds |
| charged | same work, with **all** frontier rebuild headers allocated to training offers proportionally to their observed rebuild counts |

The work bonuses share one training-only scale and clip at eight normalized units. Equal weights for a header, an entrance, a check and a packet are an explicit accounting choice. The gate has no clock target. The allocated cost is additive when every opportunity is accepted. A mixed gate can induce different shared maintenance, so each deployment directly counts the complete rebuild and reports its own net work and wall time. The source can execute the same child using ordinary leaf verification; a credited merge win represents how that work was carried out.

At evaluation time the native head uses the frozen weights and threshold zero, with no gold feedback. Python independently checks every native decision against the published feature vectors. Also included are always-leaf and always-composed controls. For each arm the test compares ordered RHS, effective writes, Spine, union events, schedule, final graph, physical Cell IDs and higher-order winner provenance. Runtime admission uses the actual possibly mixed frontier. The timing includes all policy, verifier, index repair, notifications and ordered source work, with the program resident. There is a separate scarcity control using only the 96 publications of affine-twins for native gate supervision; the common pre-existing actor and template library were already compiled.

## Reproduction

Use the versioned composed-port Rust experiment with the source version used for capture and evaluation. Set EXP to the local artifact root and BIN to its compiled session executable. Use fresh output directories.

```sh
python benchmarks/pass3-cell-gpu/merge-reward/native.py "$EXP" "$BIN" "$EXP/merge-labels"
python benchmarks/pass3-cell-gpu/merge-reward/train.py "$EXP/merge-labels/corpus.json" "$EXP/merge-gates"
python benchmarks/pass3-cell-gpu/merge-reward/evaluate.py "$EXP" "$BIN" "$EXP/merge-gates/policies.json" "$EXP/merge-runs"
python benchmarks/pass3-cell-gpu/merge-reward/large.py "$EXP" "$BIN" "$EXP/merge-gates/policies.json" "$EXP/merge-jacobi"
```

## Frozen-policy results on the four evaluation workloads

The eight evaluations comprise four programs at seeds 1703 and 1709. Across both seeds there were 1,944 gate opportunities and up to 846 source-confirmed child completions. Totals below count executions from both seeds. The same source child can still execute on the ordinary leaf path. [Per-arm samples and native endpoint digests](results.json) · [Paired aggregation](comparison.json)

| Reward after the real warm start | Selected instances | Selected instances owning a committed child | Net counted operations including all frontier headers |
|---|---:|---:|---:|
| Common supervision only | 721 | 427 | −34,527 |
| Offer a merge | 1,764 | 844 | −15,622 |
| Verified child win | 1,740 | 834 | −16,012 |
| Local work savings | 1,944 | 846 | −9,824 |
| Fully allocated header cost | 0 | 0 | −46,562 |
| Original leaf path, frontier disabled | 0 | 0 | 0 |

Switching from real to synthetic initialization produced identical per-instance decisions on all eight evaluations for the verified-win, local-work and fully-charged rewards. The two initializations differ on the supervision-only control in all eight. Its synthetic warm start selected 568 instances owning 305 later children, compared with 721 / 427 after real initialization. These results do not establish synthetic pretraining as a prerequisite for this familiar family.

The original composed frontier eagerly rebuilds its index even when the gate selects zero instances. That explains why the zero-selection row still incurs 46,562 additional header visits; this is visible runtime work. On this compiled family the fully charged **synthetic-warm** checkpoints are provably always off: all four producer/effect interfaces, all 65 clipped integers, and all 16 depth classes give a strictly negative gate score. The real-warm checkpoints also select zero on the measured programs, but they select some unobserved inputs in the finite domain. An implementation can dispatch a certified constant-off gate to the original leaf path. [Finite-domain check](gate-domain.json)

Measured work and timings have different units. Across the eight paired groups the median ratio of the verified-child arm to the leaf wall time was 0.983. Similar timing fluctuations occur for separately evaluated weights that produce identical decisions. The experiment provides no 2× speedup from changing the reward.

With only affine-twins supervising the gate (96 native offers, 41 later wins), the two initializations still selected identical instances on all four sum-bits/dot-product seed pairs for the verified-win and fully charged rewards. The common-supervision-only gates differed in three of four pairs. The static template library remained the same in both cohorts. This does not evaluate finding an unseen producer interface. [Scarce-data native control](scarce-results.json)
