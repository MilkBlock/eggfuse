# Effective constructor nodes per issued packet

> **Metric clarification.** The filtered 3mm baseline names its independent parents: **92,658 / 558,074 = 0.16603** under the explicit-parent contract. The denominator includes 334,594 singleton, 220,972 multi-parent and 2,508 independently selected child proposals. The classifier and receiver-expanded group experiments use a different accounting convention. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

This is a native Pass 3 audit of two resource decisions using the verified packed wave issuer, an eight-parameter per-rule allocation head in the separate physical pool comparison, and two existing frozen RL checkpoints for row width. The quality numerator is the count of constructor facts first activated in an actual committed root's execution whose original fact identity remains visible at final export. The denominator charges **every sealed single + multi-root proposal plus every separately selected nested child packet**. Rejected root proposals cost one. Children that reuse an existing node also cost one. The initial graph, non-constructor relations, function writes, repeated intern requests and physical spare headers contribute zero nodes. The audit separately records all successful original constructor births before retirement.

The independent source executor verifies the exact (fact identity, table) birth sequence, final visibility, duplicate-repair forwarding and ordered Run semantics. The two programs share their complete original winners and real source physical IDs across these settings. This origin-based endpoint numerator is deliberately strict. An intermediate that was read before its identity was coalesced may have contributed to a later result.

| Configuration | sum-bits multi-root packets | Effective nodes per all packets | 3mm multi-root packets | Effective nodes per all packets |
|---|---:|---:|---:|---:|
| Before scalar omission | 5,912 | 0.1923 | 220,972 | 0.0867 |
| Two-view deployed baseline | 5,912 | 0.2125 | 220,972 | 0.1660 |
| Single learned port view | 6,896 | 0.1972 | 7,047,798 | 0.0125 |
| Two learned port views | 5,912 | 0.2125 | 220,972 | 0.1660 |
| Three learned port views | 5,912 | 0.2125 | 220,268 | 0.1662 |
| Fixed four rows | 5,912 | 0.2125 | 220,972 | 0.1660 |
| 36-parameter row policy | 5,912 | 0.2125 | 220,972 | 0.1660 |
| 456-parameter row policy | 5,912 | 0.2125 | 220,972 | 0.1660 |

The direct view comparison disables the two-view-specific tier specialization in all three arms. Additional salted views reuse the **same tied projection weights**. Their matching buckets progressively require agreement on more than one signature; the full source validator still checks every survivor. The deployed baseline also uses two views with tier specialization enabled. On 3mm, the second view cuts multi-parent traffic from 7,047,798 to 220,972, while the third saves another 704 packets. Final visible attributed nodes stay at 92,658. Thus the increase is from fewer incorrect/irrelevant proposals, with the same number of original successful RHS occurrences. One CPU worker executes all row-policy arms. At four fixed rows the 3mm singleton pages rise from 6,015 to 18,654. Page count does not change proposal count or node yield. Both policy-gradient heads (width cap 8; two or 32 hidden units) selected one cached-scoring row on every eligible call on both programs. Their original reward optimized row computation cost on four donor programs. This is a frozen deployment test, not retraining RL to optimize final node yield.

The matched scorecard joins the production OS RSS measurements and the independent node audit by program, configuration, source/physical commit digests, actual issued roots and child ledger. Each measurement used a separate process appropriate to that quantity. A heavily instrumented semantic audit would distort RSS. Time is measured from inference start to 90% of the fixed **vanilla calibration's increase from baseline**, in four new processes per arm. The maximum RSS attained by a method is also recorded. No RSS result is inferred for the unprofiled signature-view or RL arms.

| Case | OS RSS increment | Raw issuer | Filter + packed | + positive ports | + fraction pool | Effective nodes per packet, raw → filtered |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | +9.27 MiB | 28.52 ms | 27.90 ms | 27.29 ms | 35.41 ms | 0.1923 → 0.2125 |
| 3mm | +264.11 MiB | 1,499.25 ms | 1,371.58 ms | 1,497.22 ms | 1,314.86 ms | 0.0867 → 0.1660 |

For all other measured programs the per-token baseline and full histogram (including exclusion of the initialization rule) are in the [constructor birth ledger](../token-constructor-births/README.md). The [native RSS study](../verified-wave-rss/README.md) reports absolute thresholds, left-censored crossings, actual slot redemption and expired capacity. Neither crossing RSS nor preserving an ancestor identifier earns extra nodes.

Run study.py EXP NATIVE OUT using the native session built by token-constructor-births/build.py. verify.py independently recomputes scorecard.json and checks results.json against the source and RSS receipts.
