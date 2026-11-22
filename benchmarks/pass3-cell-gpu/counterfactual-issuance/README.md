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
