# External transport yield for a trained class actor and a compiled arithmetic pair action

> **Metric clarification.** The 3mm values **0.81852** (wide pair) and **0.97328** (compound key) are external transport yields. The receiver finds the individual parents inside the named class or learned-key region. The retained constructor count and timing measurements stand; neither grouped value establishes explicit-parent FEPT. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

Before inspecting individual singleton candidates, the frozen 113-parameter REINFORCE controller decides whether a rule should receive a generative freshness-class descriptor. The ordinary singleton issuer contributes explicit residuals. The independent two-parent actor can describe several learned signatures over a bounded public root span and target slice. A typed compiler proof adds a second key when the public integer ports must satisfy an arithmetic relation. The receiver independently resolves public roots and versions and recomputes both signatures, then the registered source suffix and ordered RHS execute. Wider queries still issue literal multi-parent evidence. No held-out birth labels are used to choose a deployed action.

The primary numerator is the same set of newly born constructor identities visible at final graph export in all arms. The primary denominator charges actual forward singleton, family, explicit residual and selected nested child packets, including unsuccessful actions. It excludes the receiver's feedback and failed internal prototype lookups; both are reported separately. A rise in forward transport yield must not be used to infer a reduction in search or neural FLOPs. The actor's outputs did change before candidate enumeration. The trained gate's marginal advantage over an unconditional class decision is isolated in the [dispatcher training study](../fept-policy/README.md).

| Program | Original emitted-packet yield | RL singleton | + wide two-parent | + compiled compound key | Last arm with replies | Last arm all prototype decisions + replies |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 0.21253 | 0.35483 | 0.62234 | 0.63333 | 0.47402 | 0.03673 |
| 3mm | 0.16603 | 0.40093 | 0.81852 | 0.97328 | 0.90706 | 0.02447 |
| deriche | 0.12286 | 0.37231 | 0.66058 | 0.74586 | 0.70470 | 0.01818 |

On 3mm, 92,658 retained origins are served by 95,202 forward actions: 6,950 singleton class actions, 675 singleton literals, 40,264 wide/compound pair packets, 44,805 residual higher-arity literals and 2,508 selected children. Input injection and mutable function writes add zero. The 64-byte singleton actions produce 6,950 twenty-byte replies. Charging these yields 0.90710, while charging all surveyed prototype choices and replies increases the denominator to 3,787,046 and reduces the ratio to 0.02447. This last number is a conservative decision accounting, not a count of distinct floating-point network evaluations. The source issuer and the family receiver still use many deterministic projections and key checks.

Sending the arithmetic key reduces the actual pair expansions from 4,633,068 to 683,319 on 3mm. The receiver still performs 793,338 arithmetic projections and the sender 833,646. The oracle for a hit is the original complete program, including each Run, parent and actual fresh physical ID. 3mm full inference in this four-arm matrix took 1,815.70 ms for original issuance and 2,675.01 ms for the compound composition. A more compact external interface has not established a speedup or parity with the default CPU. Sum-bits is a donor workload of the gate; 3mm and Deriche are held out.

**Transport budget for two visible origins per packet.** At the same 3mm numerator, forward transport yield of 2 allows at most 46,329 packets. We need to eliminate 48,873 more. Even if all 44,805 residual three-or-more-parent packets cost zero, the rest of the measured design costs 50,397 packets. Even if all 40,264 wide actions cost zero, the remaining 54,938 packets exceed the target. Both action families and the number of unsuccessful decisions matter. Among the higher-arity literals, 23,801 are ternary and 17,472 have five independent parents. This arithmetic is a conditional bound, not an implementation of either hypothetical optimization.

**RSS and reservation interaction.** A separate OS observer samples fresh processes between native inference markers. The primary comparison freezes the same independent default-CPU calibration and charges an increase of +264.11 MiB on 3mm and +9.27 MiB on sum-bits. Three rotated processes per arm, including unreached and already-crossed thresholds in rss.json/reserved-rss.json. Timestamp fields in the raw traces are microseconds from entry.

| Matrix and program | Initial issuer | RL class or compound (specified) | Wide or reserved (specified) | Final compound |
|---|---:|---:|---:|---:|
| 3mm, class and wide ablation | 1,324.30 | 1,593.35 (class) | 1,676.28 (wide) | 1,505.90 |
| sum-bits, class and wide ablation | 24.56 | 25.66 (class) | 29.45 (wide) | 29.17 |
| 3mm, prebuilding ablation | 1,382.25 | 1,590.32 (compound) | 1,622.90 (reserved) | — |
| sum-bits, prebuilding ablation | 25.16 | 30.40 (compound) | 34.32 (reserved) | — |

Each time is the median in ms to the same incremental threshold within that matrix. Adding fraction-predicted, compatible shared private Cell storage kept all historical transport denominators unchanged. It actually supplied 107,698 physical Cells from 130,511 reservations on 3mm. The earlier common-RSS crossing seen for prebuilding on the ordinary issuer does not transfer to this composition. Use the archived native inference samples for the corresponding latency comparison.

```sh
python build.py "$EXP/new-compound-joint"
n="$EXP/new-compound-joint/session"
python study.py "$EXP" "$n" "$EXP/new-cf-ablation"
python rss.py "$EXP" "$n" "$EXP/new-cf-ablation/results.json" "$EXP/new-cf-rss"
python study.py "$EXP" "$n" "$EXP/new-cf-reserved" --pool-study --cases sum-bits 3mm --repeats 3
python rss.py "$EXP" "$n" "$EXP/new-cf-reserved/results.json" "$EXP/new-cf-reserved-rss" --pool-study
python study.py "$EXP" "$n" "$EXP/new-cf-deriche" --cases deriche --repeats 3
python verify.py
```
