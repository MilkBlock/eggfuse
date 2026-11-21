# Use a compiler-proved arithmetic port in the family packet

> **Metric clarification.** The compiled arithmetic port reduces the combinations inspected by the receiver. The receiver still supplies individual parent addresses. Counts per emitted family describe external transport yield; they cannot establish an explicit-parent FEPT improvement. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

The primary-only family study generated millions of possible combinations for one frequent shape. Its producer knew the relation between the two scalar columns, but its packet described only the learned signature of the common Expr. This experiment tests whether exposing both learned port codes before expansion lets the receiver avoid those combinations. It uses the same frozen model, original source program and 32-left / 8-key / 256-pair bounds as the [primary-key wide study](../generative-pair-families/README.md).

A compiler Equation is admitted if a two-parent plan computes the output of a recognized checked integer operation from one parent's columns or literals, and that output occupies a known column on the other parent. In rule 144 the second SubTuple must begin at the first SubTuple's start plus its length. No rule ID or workload name appears in the extraction or packetizer. The typed compiler still governs the arithmetic, including undefined results. The frozen neural projection maps the resulting integer to its query or key code. The compound packet stores the original primary code and the scalar code as a full pair of 32-bit words. Distinct pairs of codes cannot alias in the encoding. Unequal source values can still share a learned signature; the original verifier checks the source rule. An unknown projected value on either side keeps the whole original one-key route for that occurrence.

The sender materializes an additional projected column for each proved side, cached by original rule, side, exact table generation and union generation. It uses the full pair for the right marginal histogram and the left-span prototype set. These operations finish before any individual partner pair is formed. Primary-only packets still carry four bytes per prototype. The compound-format tag uses one reserved header bit. The receiver independently computes the scalar port from visible public graph rows, authenticates the scope and extent, and retains its ordinary argument, source, and arithmetic checks. The diagnostic fault changes only the high word of a transmitted full key. This exercises the new proof component without changing the source graph.

## Held-out 3mm results

| Native configuration | Family actions | Pairs expanded by receiver | Total external root / family / selected-child packets | External transport yield (visible origins per emitted packet) | Including failed prototypes | Complete inference median |
|---|---:|---:|---:|---:|---:|---:|
| Original directional issuer | 0 | — | 558,074 | 0.166032 | 0.166032 | 1,843.05 ms |
| Primary-key wide families | 58,264 | 4,633,068 | 440,171 | 0.210505 | 0.024703 | 2,691.90 ms |
| Compound-port wide families | 40,264 | 683,319 | 422,171 | 0.219480 | 0.023905 | 2,661.91 ms |

The compiler admitted the arithmetic port on all 70 applicable occurrences. For the SubTuple rule, packets fell from 28,010 to 10,010 and combinations visited fell from 4,084,017 to 134,268. Both paths delivered 10,285 identical original proposals for that rule. Across all two-parent rules the receiver produced 176,167 original candidates and their directly attributable 37,286 final-visible constructor identities. All arms reached the same final-visible total of 92,658. The complete issued family wire fell from 5,249,704 to 3,973,660 bytes, including the widened scalar prototypes.

The compound key reduced available combinations by 85.25% across all families. It also produced more distinct marginal prototypes: 3,570,905 to 3,655,283. When every absent or fully stale prototype is charged, the denominator grows from 3,750,910 to 3,876,108. The senders computed 833,646 scalar row projections and the independent receivers computed 793,338, in addition to the source's exact validation. A separate diagnostic run measured primary-only issue/receiver intervals of 326.08 / 687.89 ms, compared with 347.45 / 768.16 ms for the compound form. The complete compound arm was faster in three of four rotated pairs than primary-only but remained slower than the ordinary issuer. The 29.99 ms difference between family medians does not establish a durable throughput gain.

The complete raw expanded multi-parent digest, ordered RHS, writes, union, Spine, graph, winning source and physical parents and constructor origin ledgers all align. The scalar corruption control failed the packet scope/bounds checks under both programs. The independent sum-bits smoke reduced this rule from 16,085 combinations to 1,282 while delivering the same 232 candidates. [Complete 3mm measurements](results.json) · [Sum-bits controls](smoke.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/compound-family-ports
python "$d/build.py" "$EXP/compound-build"
python "$d/study.py" "$EXP" "$EXP/compound-build/session" "$EXP/compound-smoke" --smoke --cases sum-bits
python "$d/study.py" "$EXP" "$EXP/compound-build/session" "$EXP/compound-heldout" --cases 3mm
python "$d/verify.py"
```
