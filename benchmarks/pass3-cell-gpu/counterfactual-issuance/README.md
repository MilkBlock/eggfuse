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

## Interchangeable owners of the same successor

owner_forks.py replays four interventions with the same program, generated initial rows and native issuance page. Both named roots are offered before any result feedback. The trace must agree through the last address on that page. None, only A, only B, or both may sign the existing 143 → 55 → 143 template; every other root in the episode takes the leaf action. All four must agree on source execution, endpoints and semantic root bindings. The script separately runs exact matching on the same generated program and checks the leaf trajectory against it. Saved proposals must equal distinct internally committed source ordinals. Source ordinals, rather than serials allocated by the proposer, identify common successors across interventions.

The shared-result generator makes two distinct Get keys return the same Expr e-class. Both source RHSs therefore request Single on the same operand. Half of the episodes also start with an existing Single for that operand. The native scope is four always-run iterations with the real EggCC rules. It is separate from execution of a full EggCC input. A/B assignment is shuffled; the earlier source execution owns the fresh result in the original implementation. Distinct address choices and asymmetric returns alone do not establish that two owners compete for the same successor.

The optional reuse_returns capability licenses the existing typed first edge on a signed block when the constructor actually returns a visible fact. It records the executing producer cell and instruction separately from the returned fact and version. At the original Run, release checks the current member, physical witness, version and returned address. A previously registered witness is retained. Only the first licensed registration can supply a given successor; the option grants no additional constructor birth. Corrupting the recorded release address must fail even when the physical operation index differs from the signed instruction.

Build this directory's native overlay. Run owner_forks.py EXP SESSION OUT with EGGFUSE_GENERATED_GET_EPISODES=1, passing --shared-result in both arms and --reuse-returns in the treatment. Use distinct output directories. Run catalog_credit.py with --reuse-returns for the complete sum-bits and 3mm comparison. paired-owner-results.json contains the aggregated same-page interventions and the full-workload paired arms.

## Can the generator observe when a signed completion pays off?

Build the counterfactual session, then run `EGGFUSE_GENERATED_GET_EPISODES=1 python context_credit.py EXP SESSION OUTPUT`. Training uses 32 randomly generated pairs with the dot-product program; evaluation uses 32 fresh pairs with the sum-bits program. Each episode substitutes the generated inputs and executes four iterations of the EggCC always-run rules. The experiment controls the first issuance of the 143 → 55 → 143 family; other roots take the leaf action. The pair changes one Single input between an unrelated value and the Get output. The generator shuffles token order, adds unrelated rows and sometimes places the subject value in a distractor's output port.

Native leaf and signed executions supply the regression target in paid external proposals. Both agree on the strict source trace and semantic roots, and savings reconcile to uniquely committed signed children. The old count/age inputs, a manually joined context bit and a learned pooling read over all initial token rows use the same paired data. The learned read receives row type and exact port comparisons to the subject, trains with backpropagation on CPU, and pools without position encodings. The live test computes the frozen score in Python from the source input before invoking Rust. Rust applies it to the first eligible issuance without an oracle serial. Every resulting trajectory is checked against exact execution and the corresponding paired token count.

In the held-out episodes the 73-parameter reader selected 32 of 64 possible signings and retained all 64 saved external proposals. Always signing the first root attained the same paid count. The read distinguishes productive signings; this experiment changes neither the available library nor the best attainable FEPT. The generated single-root setting and supplied address comparisons limit what can be inferred about autonomous parent selection and full workload execution.
