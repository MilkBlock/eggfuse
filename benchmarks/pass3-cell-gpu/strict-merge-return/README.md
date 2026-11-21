# A composed merge constructor with an explicitly named old row

Consider a rule that writes `F(key) = Candidate(args)`, where the function's original merge expression calls `Constructor(old, new)`. The compiler can build a static template variant if the same rule has precisely one LHS atom reading `F` on the identical key expression, its old result is a named slot, the candidate is a constructor result returned immediately before the set, and there is one unambiguous supported Set effect. The extraction reads the compiled query, effect and merge expression; it has no operator names or rule ordinals built in.

For each real neural multi-parent root proposal, the issuer checks its **already issued** physical parent tuple at emission, before source suffix verification. When that tuple names every table atom, including the exact old function row and its version, the issuer sets the candidate's template-variant bit. The immutable page owns the bits, original parent addresses and static variant. A different template choice does not grant another free choice of external parents. Rejected root proposals still count against the denominator. A single-parent proposal, unresolved operand or unsupported plan retains the ordinary separately charged child protocol.

At matched-root binding, the instance saves the proved old result from the checked old atom's slot. At ordered commit the reader verifies the issued serial, rule, Run, old reference and version. The candidate constructor exposes its **actual** returned fact at the original instruction, including an intern hit on an earlier Cell. At the Set boundary two direct physical reads validate current old row and candidate return; a changed old version, key or value, or an unavailable return, leaves the original separately issued child path active. Comparing the canonical old value as well as epoch protects against multiple writes within one Run. These checks do not enumerate other possible old rows. The source's own ordered function update and normal constructor interning remain in force.

With a complete proof the executor suppresses the dependent neural child issue, including its scoring. If the original merge really calls its constructor, the static variant rechecks the actual ordered arguments, then returns the actual reused fact or newly allocated constructor. A tagged root that reached an absorbed write may produce no nested constructor. The new template does not count a successful check, suppressed packet, preallocated Cell or intern hit as a fresh e-node.

The separate trace inspection uses the ordinary filtered explicit-parent leaf with the unchanged learned merge-child issuer. It compares each observed child's old row and version against the corresponding original paid root refs. The retrospective count measures opportunity. Only the native treatment suppressing the external child and delivering its typed result can establish composition.

## Native result

| Pass 3 | Issued tags / source-committed | Stale old, paid fallback | Actual merges, freshly built / existing returned | New internal origins still visible | External child proposals, leaf → composed | Strict FEPT, leaf → composed | Inference ms, leaf → composed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 355 / 102 | 3 | 75 / 24 | 75 | 191 → 92 | 0.21253 → 0.21420 | 37.21 → 35.60 |
| 3mm | 8,384 / 2,480 | 230 | 979 / 1,271 | 979 | 2,508 → 258 | 0.16603 → 0.16670 | 1,870.04 → 1,917.16 |

In both compiled inputs exactly one rule qualifies (507, `terms-helpers`). The complete root packet explicitly names table atoms 0 (old TCPair), 1 (old ExtractedExpr function row, output slot 2), and 3 (source CellSpineView8). Its static RHS computes the candidate TCPair at op 2 and the ExtractedExpr update at op 3. The declared source merge then calls Smaller with the checked old value and the actual result returned by op 2.

For example, sum-bits root serial 4,471 (source RHS ordinal 2,519) names Function(531), version 330. Op 2 returns the pre-existing candidate Cell 2,624, op 6. The ordered merge creates Smaller at Cell 2,687, op 0. Every composed candidate TCPair was returned by reuse in these workloads; assuming the candidate lived at the current Cell's op 2 would have supplied the wrong reference in all 2,349 calls. The final Smaller was genuinely fresh in 75 and 979 cases, and those exact 1,054 original identities remained visible. Each reuse returned the identical physical fact as the independent leaf allocator.

All originally emitted root proposals remain charged (12,471 / 555,566). Valid composition reduces total packets from 12,662 to 12,563 and from 558,074 to 555,824, at equal visible numerators 2,691 and 92,658. Every unaccepted tagged root still incurs its root proposal. The new per-page tag masks total 79 / 1,105 bytes. All successful tags reuse parent references already present in the root. No new independent old-parent proposals, old-row candidate enumeration or separate internal child network scores were used. The verifier did perform 102 / 2,480 direct old reads and 99 / 2,250 direct candidate-return reads, in addition to the source execution's ordered update and interning.

Altering either the old physical reference or its version causes explicit rejection at the first affected Run in both programs. Ordered RHS, writes, Spine, full events including unions, physical allocation identities, root streams and final-visible identities agree. Four interleaved uninstrumented samples after a warmup place the two inference medians close; there is no consistent timing improvement across the two programs. [Native audit and timing samples](results.json) · [Prior exact-reference opportunity count](opportunities.json)

## Evidence and reproduction

Run the study on the same frozen sum-bits and 3mm Pass 3 bundle. The native builder composes the filtered explicit-parent baseline and the additional merge-return support. All timings include the source scheduler and verification in the same warmed native process.

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/strict-merge-build"
python3 measure.py "$exp" "$exp/strict-merge-build/session" "$exp/strict-merge-opportunities"
python3 study.py "$exp" "$exp/strict-merge-build/session" "$exp/strict-merge-test"
python3 verify.py
```

[Explicit-parent accounting contract](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)
