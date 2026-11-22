# Counterfactual credit at signed Cell issuance

The native CPU issuer chooses between a leaf and its licensed compound completion. For training, the Rust overlay allows one actual issuance decision to be flipped. The two executions start from the same generated input and seed, verify the preceding decision prefix, and check source effects, endpoint identities and semantic roots in both outcomes. Later sampled actions can diverge. Their consequences contribute to the episode return. The learner uses the existing three decision features and differentiates the expected paired reward with respect to the issuer logits.

```sh
D=benchmarks/pass3-cell-gpu/counterfactual-issuance
python "$D/build.py" "$OUT"
python "$D/train.py" "$EXP" "$OUT/session" "$OUT/policy.json" --episodes 128 --device cpu
python "$D/evaluate.py" "$EXP" "$OUT/session" "$OUT/policy.json" "$OUT" --cases sum-bits 3mm
```

Training uses random generated inputs. Evaluation runs native EggCC workloads. Reward uses leaf minus full paid proposals plus one eighth of the difference in root header checks, capture reads and block admissions. The weighting is an experimental operation proxy. `checked_internal` counts the signed verifier's direct internal binds. Greedy evaluation uses CPU inference. Training used CPU for this experiment.

In 128 paired decisions the completion had positive reward 57 times and negative reward 71 times. Sixteen of the nineteen distinct observed feature vectors occurred with both signs. This is evidence of observational ambiguity in this dataset. It does not identify which additional input will resolve it. The trained policy, the earlier policy and always issuing the compound performed identically on both real workloads. Gains over leaf-only execution come from the existing block admission and verification path. This experiment provides no evidence that the new RL policy saved additional work. Results and feature-group counts are in `results.json`.

## Paid proposals as the sole training return

catalog_credit.py refits the three-feature issuance head on the saved paired, randomly generated decisions using only leaf paid packets minus full paid packets. Prefix checks and equality of both native outcomes were enforced when the pairs were captured. Among 128 forks, 57 saved two packets, 71 saved zero, and none lost a packet. Thus a fixed-full policy already maximizes the observed paired return, regardless of network width. Later sampled actions may differ after a forced action, so these are paired episode outcomes.

The frozen actor runs on complete sum-bits and 3mm. At load time, the compiler supplies the applicable Let paths and the separately checked Set route. The widest catalog enumerates one- and two-edge paths through seminaive, sole constructor atoms with distinct variable slots; the native loader rechecks eligibility. Eligibility and static wiring are compiled. The trained actor decides whether to sign the typed continuation on eligible roots; it does not dynamically choose one among thousands of distinct paths. All external singleton and multi-parent proposals and selected independent children are paid. Only actually committed internal source ordinals count as savings. Each arm checks against the independent native reference and preserves the leaf arm's physical identities, source commit and ordinal accounting, and constructor birth and endpoint digests.

Reproduce with the native counterfactual session and the paired training artifact from train.py:

```sh
python catalog_credit.py EXP NATIVE_SESSION PAIRED_POLICY_JSON OUTPUT
```

The frozen combined catalog saves 419 and 10,758 external proposals relative to leaf issuance. Compared with the full two-edge Let catalog alone, the net reductions are much smaller. The Set path can compete for a source occurrence already covered by another template, so terminal Set commits cannot simply be added to Let savings. The fixed-full control matches the learned head. This experiment exercises the existing filtered CPU issuer and direct internal verification. It neither times the alternatives nor establishes a general autonomous neural search rate.
