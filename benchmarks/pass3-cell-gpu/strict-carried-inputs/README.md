# One actual returned constructor plus four carried LHS witnesses

This bounded experiment targets one donor-frozen self-composition. Among recurrent templates from both dot-product and jacobi-1d with five table atoms, one typed producer operation and the remaining atom identities carried unchanged, the selected mapping is the same rule after four original Runs. No consumer lookup, candidate bucket or receiver search is used to obtain any of those five inputs. The public fallback remains available whenever the signed branch cannot prove completeness.

Rule 249 reads a loop, two ContextOf atoms, a Const and the input type. It constructs a new Const at operation 2 and publishes a loop-invariant analysis fact. Its compiled variant has input mapping [original atom 0, original atom 1, original atom 2, actual new op 2, original atom 4]. A bit on each original producer page selects that precise variant at issue time, before source validation and RHS application. Only an ordinary source winner bearing all five original physical addresses, their versions and the signed variant may register the operation's actual fresh returned fact. A nested child, an intern hit, or another rule's result cannot provide the new port. An internal child does not acquire an uncharged right for a third activation.

**Disjoint source exclusion.** At the predetermined future Run the receiver independently reads the five named rows, checking their physical types, versions, seminaive eligibility, literals and shared variables. It must prove the last lookup on the source prefix cannot have another independent result. The engine maintains a saturated public count for the last table's bound key column. Births increment it, and actual unions merge its two counts. Retirement never lowers the upper bound. The directory stores no FactRef or candidate list. It cannot supply a missing parent. A bound of exactly one and the visible carried HasArgType establish uniqueness for this four-address prefix. The compiler also checks that the ordinary deduplication key includes all the input key columns of all five tables.

Certified children are constructed **before** residual enumeration. The ordinary general-stack issuer is disabled immediately on entering the exact four-address prefix, before lookup, scoring or generation of its last independent parent. Other complete bindings under the same DoWhile or Const may still be necessary. The ordinary issuer can therefore do genuine residual model/search work on shorter shared prefixes. Verified children are merged at the reference's lexicographic position among disjoint residual source tuples; a child is drained even if residual enumeration reaches no such prefix or emits nothing. An equal external tuple is an error. The independent detailed audit also checks that no external consumer packet has the protected prefix. Original RHS arbitration receives the disjoint union and commits at the designated original Run. Charging every external producer, failed token and selected child is preserved.

The detailed, untimed control compares the scalar upper bound against all currently visible original terminal rows for that same concrete key. Only this separate audit scans them. Timed requests publish the number of such reference-only row visits, which must be zero. Birth/retention counts are classified by the original table and source operation, so an underlying program Expr constructor can be distinguished from a maintained analysis fact. Losing a version or lacking uniqueness returns to the ordinary external path.

## Held-out explicit-parent results

| Workload | Final-visible original constructors | All paid external proposals, ordinary → carried | Strict FEPT | Independent internal children | New / final-visible constructors from internal RHS |
|---|---:|---:|---:|---:|---:|
| sum-bits | 2,691 | 12,662 → 12,662 | 0.212526 → 0.212526 | 0 | 0 / 0 |
| 3mm | 92,658 | 558,074 → 557,744 | 0.166032 → 0.166130 | 330 | 330 / 330 |

The productive child table is **lsr-inv**, the source's loop-invariance analysis constructor. All 330 newly published physical identities remained in the 3mm export. The child RHS produced no new Const/Expr identity: it consumed the already returned Const. Those 330 analysis identities also exist under ordinary execution, so the numerator remains 92,658. The measured gain is exactly 330 genuinely absent external packets. The singleton and independently selected nested-child counts stay 334,594 and 2,508. The multi-parent external stream falls from 220,972 to 220,642.

On 3mm, 12,118 original producer proposals carried the variant, 12,118 committed, and 330 supplied the required strictly new operation-2 return. At the release boundary the normal verifier made 1,650 addressed row reads and 330 O(1) terminal degree checks. It prepared and committed all 330 children with no unnamed-parent lookup and no unresolved internal proof. The residual source checked 10,773 four-address prefixes and preempted 330 before the fifth parent lookup. The public degree ledger charged 5,945 terminal-table activations and 1,183 union updates. The separate source audit exercised 1,145,293 row visits to cross-check actual live cardinalities and found exactly one matching terminal row for every protected prefix. These audit visits were zero in the timed path. Ordinary execution also contained one committed terminal choice per corresponding exact prefix. Neither stale evidence nor the conservative ambiguity bound blocked a valid opportunity on this workload. The injected stale-version and nonunique controls each blocked all 330 and restored the full original external count and original source/physical state. In sum-bits four producer proposals committed and none published a fresh specified Const at op 2, matching the absence of this exact shape in its earlier trace.

For example, 3mm source commit 42,043 at Run 839 produced Const FactRef 181123065839618. At Run 843 the internal source commit at ordinal 49,883 retained the original DoWhile/ContextOf/ContextOf/HasArgType addresses with versions 1, 835, 831 and 57; its fourth LHS atom read this new Const at version 839. The ordered committed binding and resulting constructor identity matched the ordinary child. [Source, origin and negative-control receipts](results.json) · [Donor-frozen mapping](template.json)

| Workload | Inference, ordinary → carried | Common entry-relative RSS rise | First crossing, ordinary → carried | Sampled peak, ordinary → carried |
|---|---:|---:|---:|---:|
| sum-bits | 38.20 → 35.07 ms | +9.28 MiB | 25.24 → 27.36 ms | 270.69 → 274.32 MiB |
| 3mm | 1,949.26 → 1,959.28 ms | +264.09 MiB | 1,318.10 → 1,466.08 ms | 698.12 → 698.40 MiB |

Four rotated resident samples follow warmup. The sum-bits arm admitted no internal children, so its lower median cannot establish a gain from this template. The 3mm source-aligned packet reduction did not improve the overall median or time to the common growth level. RSS uses three independent vanilla calibration processes, followed by four fresh sampled/unsampled pairs per arm. Source/model loading and graph export are outside inference. The aperture comparison uses a macro-off ordinary issuer built from the same source; the retained graph, original ordered RHS, effective writes, unions, Spine, physical and semantic roots, constructor birth origins and final output all align with the independent Cell CPU source execution. [RSS samples, controls and thresholds](rss.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/strict-carried-inputs
python "$d/freeze.py"
python "$d/build.py" "$EXP/strict-carried-build"
python "$d/study.py" "$EXP" "$EXP/strict-carried-build/session" "$EXP/strict-carried-study"
python "$d/rss.py" "$EXP" "$EXP/strict-carried-build/session" "$EXP/strict-carried-rss"
python "$d/verify.py"
```
