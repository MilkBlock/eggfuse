# One issued root and independently verified consumer activations at later Run releases

The existing CPU path first verifies the model's individual candidate. Spine then takes the already verified bindings, joins their original fact addresses to scheduled entries with a published cursor, chooses its ordinary owner and continues at the recorded ordering point. A Spine resume alone cannot establish that an external consumer token was unnecessary.

The experiment implements a second, causal certificate verifier inside the live Rust EggFuse Cell CPU engine. Each newly accepted Spine root contributes one genuine original model root serial, producer rule, source Run and unique Spine owner ID. All such roots are charged, including roots that never lead to an accepted consumer. A page, batch or future observed chain introduces no token.

Before the ordinary model emits any proposals for a scheduled rule in its source wave, the independent verifier enumerates that rule's current Entry deltas. A candidate must refer to a previously admitted external root through an actual live native Spine publication at a particular producer output. The producer must have committed in an earlier Run; the original watermark and visibility must also admit its output now. This bounded grammar handles immediate children of roots only. Its compiler admits pivots with an existing Spine entry proof and an ordered, complete-key table suffix, allowing typechecked checked-integer arithmetic. All query aliases and literal bindings, exact suffix reads and result predicates must succeed. Neither the model's offers nor the source winners are inputs to this verifier.

The verifier reconstructs a complete RHS slot vector and its exact source fact witnesses. At the ordinary commit, it checks that the current Run, expected binding, winning Spine root, original pivot address/version/output and producer rule agree. Every retained source witness must agree. When a compact source binding omits a witness, the same authenticated original pivot and complete deterministic key program certify the reconstructed suffix. The two witness categories are counted separately. Only then does the apply arm move the independently computed slots into the actual RHS. Other activations retain the original path. The verify-only arm performs the same checks and consumes its independent proposal without replacing the slot vector. Corrupting the owner of an otherwise accepted activation must abort. All original accepted root metadata, raw wire hashes, model choices, physical allocations, ordered RHS inputs, effective writes, unions, Spine and final graph must match the default CPU source and no-integral learned control.

**Two distinct token counts matter.** The supplemental certificate stream has one externally supplied seed per admitted real root. Its consumers need no additional model-parent input for their own reconstruction. The integrated full engine still requires the original consumer proposal for winner arbitration and ownership comparison. Its actual external model traffic remains measurable in the original raw ledger. Subtracting certified children from whole-pass accepted RHS token counts is therefore an attainable-work hypothesis conditional on replacing that arbitration. Raw rejected offers and auxiliary nested merge tickets cannot be subtracted with this calculation.

The four other source output counters and the constructor-only metric are measured around the actual accepted RHS. Their stored order is new logical fact registrations (including relation facts), newly allocated physical Cell records, effective native function updates, successful unions and first visible constructor fact registrations. Counts cover each RHS commit and exclude preloaded input graph construction, but include the program’s separate source initialization rule when it runs. Distinct constructor fact registrations are the logical e-graph node measure used for the per-token ratios. Function values and physical frame allocations are shown separately.

## Measured real Pass 3

| Metric | sum-bits | 3mm |
|---|---:|---:|
| Source Runs / accepted RHS | 1,428 / 7,265 | 4,260 / 294,917 |
| Actual original single + multi root packets | 7,889 + 5,912 | 845,168 + 220,972 |
| Additional issued merge-child records | 305 | 7,120 |
| Supplemental external seeds / seeds with credited children | 3,492 / 804 | 181,235 / 28,576 |
| Already-proven native Spine resumes / first-hop ceiling | 2,098 / 1,330 | 62,506 / 40,128 |
| Independently derived bindings / actual consumer RHS supplied | 1,243 / 1,223 | 36,873 / 36,855 |
| Complete original receipt set / anchored reconstruction | 175 / 1,048 | 4,036 / 32,819 |
| Independent anchor reads / suffix point lookups / primitive evaluations | 3,187 / 2,635 / 23 | 115,928 / 106,245 / 488 |
| New constructors at all seeds / internal children / whole pass | 2,262 / 474 / 3,610 | 72,948 / 11,345 / 119,503 |
| Physical Cell allocations / effective function updates at internal children | 959 / 207 | 31,186 / 16,209 |
| Full inference, standard learned / secondary verify / secondary verify and apply, ms | 34.53 / 36.20 / 38.74 | 1,960.00 / 2,128.14 / 2,117.52 |
| Independent default CPU inference, ms | 22.03 | 912.52 |

All supplemental seeds paid, seeds and children together produce **0.784 / 0.465 constructor births per supplemental seed token**. Restricting the denominator retrospectively to seeds that had a credited child yields 2.076 / 1.294, so excluding unused seeds materially changes the result. Actual original external traffic is unchanged across all three learned arms. On the original accepted RHS denominator, whole-pass births per accepted ticket are 0.497 / 0.405. Eliminating precisely the now-certified child tickets would give 0.597 / 0.463 **if source arbitration could also be replaced**. This experiment directly verifies slots supplied to the original RHS; it establishes no reduction in external packets.

In sum-bits, accepted external serial 368 (root 83, rule 573, Run 24) provides its actual output port 1 to rule 572, at LHS pivot 1, in both Runs 25 and 26. In the compiled recipe rule 573 reads TCons and TLConcat; rule 572 reads TNil and TLConcat. One retained root verifies two legitimate scheduled uses of its publication. The source initialization rule 375 is itself a large producer with a single external seed; its outputs account for 96 / 3,412 credited activations on sum-bits / 3mm. The remaining 1,127 / 33,443 certified activations belong to other producers.

On 3mm the checker traversed 1,284,218 scheduled delta ports. 1,072,636 had no published cursor, 78,063 contained a deeper cursor outside the tested grammar, and 79,055 checked first-hop possibilities failed exact binding. Another 22,378 actual source resumes had depth above one hop, and 3,273 first-hop source winners had no offer from the bounded verifier. A corrupt winning owner aborted in both programs. The independent verification overhead is charged in full and dominates the additional evidence. [Paired source, route, fanout, timing and corruption receipts](results.json) · [Frozen build and program identities](manifest.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/integral-root-certificates
python "$d/build.py" "$EXP/integral-cert-build"
python "$d/study.py" "$EXP" "$EXP/integral-cert-build/session" "$EXP/integral-cert-results"
python "$d/verify.py"
```
