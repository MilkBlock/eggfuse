# Learn when an issued action should stand for a class of parents

FEPT counts distinct newly published constructor facts whose original source identities remain visible at final export, divided by external model-issued actions including failures and separately selected nested children. An ordinary action can propose one parent. A freshness-class action emits a 64-byte descriptor before enumerating the public pivot table. The native receiver resolves the descriptor and tests its members; it returns twenty bytes of counts. A four- or eight-row shard of independent decisions would still pay for each independent binding.

This study changes the decision itself in the current native EggFuse runtime. One frozen gate jointly selects the literal or class form at each eligible singleton rule invocation, before the table snapshot. Both use the same source, issuer checkpoint, exact verifier and graph. All programs in the training set are real native Pass 3 traces. The 5,924 eligible examples come from sum-bits, dot-product and jacobi-1d. The holdouts CG, 3mm and Deriche were kept out of training. Twelve causal features give public table cardinality, previous invocation counts, watermark age and compiler rule/port dimensions. The current eventual number of survivors and final graph only enter training labels or independent checks. No current candidate list is given to the gate.

If an invocation would issue n individual proposals, one class action costs one external packet independently of its eventual success. Source semantics are invariant to this choice, so its measured advantage in the numerator-preserving forward budget is n−1. For a contract that charges its receiver feedback too, the advantage is n−2. train.py uses offline PyTorch and exports a small native linear or tanh head. A sampled REINFORCE update centers binary returns on their conditional expectation. The other policy-gradient treatment differentiates the exact expected binary return. These are contextual one-step decisions; the experiment does not infer long-horizon reinforcement learning. The BCE baseline predicts whether n>1. A second supervised control is trained on *actual final visible births* attributed to each invocation and predicts whether the invocation will produce any. Program inputs, final surviving origin count, all Run effects and the underlying recurrent trajectory are independently checked in every treatment.

| Gate, before enumeration | CG FEPT | 3mm FEPT | Deriche FEPT |
|---|---:|---:|---:|
| Original independent proposals | 0.15872 | 0.16603 | 0.12286 |
| Always choose the class | 0.38236 | 0.39839 | 0.37032 |
| Previous occurrence sent multiple survivors | 0.34482 | 0.36020 | 0.33251 |
| Public table contains multiple rows | 0.38236 | 0.39839 | 0.37032 |
| Predict at least one final-visible origin (113 params) | 0.18206 | 0.20403 | 0.14077 |
| Predict n > 1 (13 params) | 0.37191 | 0.39065 | 0.36415 |
| Exact expected return (13 params) | 0.38530 | 0.40085 | 0.37269 |
| Exact expected return (113 params) | 0.38589 | 0.40093 | 0.37255 |
| Sampled REINFORCE (113 params) | 0.38578 | 0.40093 | 0.37231 |
| Expected return with reply cost (113 params) | 0.38629 | 0.39902 | 0.37081 |
| Perfect choice at each observed invocation (diagnostic) | 0.39186 | 0.40375 | 0.37484 |

3mm holds 92,658 final-visible original facts in every arm. Compared with original singleton proposals, the REINFORCE policy reduces the full forward budget from 558,074 to 231,105. Most of this change came from the class-action vocabulary: always choosing the class costs 232,580. REINFORCE saves a further 1,475 packets and chooses the class on 6,950 of 9,097 eligible invocations. A 13-parameter expected-return head uses 231,156. The full oracle in this fixed action space and with all multi-parent traffic unchanged reaches only 0.40375 on 3mm. Direct supervision on the positive-node label reaches just 0.20403 there; a low-yield rule can still be a good place to avoid sending many unsuccessful individual proposals. On the donor traces and every test program the actual terminal identity numerator is immutable across policies.

**Work and alternative denominators.** Charging the 6,950 receiver replies reduces REINFORCE on 3mm to 0.38923. Charging a gate abstention as a separate model output instead gives 0.39724. The two charges answer different questions. Wider-family composition additionally records all modeled prototypes and original residual-row scores, a still more demanding denominator. The measured native inference medians in this single-actor matrix are 1,788.61 ms (original), 1,886.52 (always class), and 1,885.96 (REINFORCE) on 3mm. These are secondary metrics, three rotated resident samples per arm after warmup. The gate increases transport yield while the receiver still scans public rows and validates every matching suffix. It leaves all multi-parent packets explicit. The donor labels do not include receiver execution time.

The files under donors contain occurrence, rule, the twelve observable coordinates, n and the final-visible label. models.json pins their digests. verify.py independently scores all donor choices from serialized coefficients and recomputes oracle and effective yields against the native holdouts. The simpler terminal-only holdout audit has its own receipts. The original five frozen models used the same features and training labels before the final-origin label was attached; a second fit on the archived superset reproduced their coefficients exactly. Timing comparisons with other binaries require new measurements.

```sh
python build.py "$EXP/new-fept-build"
n="$EXP/new-fept-build/session"
python experiment.py "$EXP" "$n" "$EXP/new-fept-donors" --capture --cases sum-bits dot-product jacobi-1d
python train.py "$EXP/new-fept-donors" /tmp/fept-models.json
python experiment.py "$EXP" "$n" "$EXP/new-fept-test" --models /tmp/fept-models.json --cases conjugate-gradient 3mm deriche
python verify.py
```
