# Strict partial cross-Run returns and named same-RHS merges

The four same-binary arms are ordinary filtered explicit-parent leaves, partial delivery through at most two certified cross-Run edges, the preissued same-RHS merge-return variant, and both together. Counts use actually transmitted singleton and multi-parent proposals and separately selected child packets.

**Original header.** The low 32 bits retain the source template. Bits 32–62 identify the signed Spine program (rule ID + 1), with a checked 31-bit bound. Bit 63 on a multi-parent page announces a per-lane merge bitmap. All singleton headers keep bit 63 clear. The verifier consumes the little-endian bytes in the original native template field. The independent audit decodes fields and bitmap padding, compares committed lanes against source template/Run, and counts the observed combinations. Root serials reserved for internal partial releases are excluded from the external packet count.

**Physical inputs.** An internal partial consumer receives an actual signed producer return on its original Run. A same-RHS strict merge requires that the root names every independent table parent, the old function row ID, its version and the candidate constructor's actual returned reference. The verifier checks the old value at the ordered Set. On a mismatch the original independently charged child remains available. The audit compares every internal merge result, including interned ones, against the exact same physical return from the corresponding separately paid child in the arm with the same partial setting.

**Distinct origin credit.** Every born constructor fact is classified by immediate RHS source (external proposal or internal cross-Run release) and by birth kind (typed, paid child, internal same-RHS merge or other dynamic). Both births and final-visible original facts reconcile exactly. We compare signed trails, root and child physical identities, source RHS, effective writes, unions, Spine and final graph. Fault controls alter individual header fields or the Old input ID/version. A stale partial-release control measures the return to paid proposals.

## Matched native runs

Every entry is an observed full execution. No combined-arm value was calculated by adding the two independent savings.

| Workload | Arm | Explicit root proposals, single + multi | Selected child packets | Total external | Strict FEPT | Inference / caller wall, ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | leaf | 6,559 + 5,912 | 191 | 12,662 | 0.21253 | 32.46 / 69.39 |
| sum-bits | partial2 | 6,148 + 5,912 | 191 | 12,251 | 0.21966 | 33.50 / 69.90 |
| sum-bits | merge | 6,559 + 5,912 | 92 | 12,563 | 0.21420 | 32.77 / 68.85 |
| sum-bits | both | 6,148 + 5,912 | 92 | 12,152 | 0.22145 | 33.62 / 69.53 |
| 3mm | leaf | 334,594 + 220,972 | 2,508 | 558,074 | 0.16603 | 1,761.21 / 2,017.82 |
| 3mm | partial2 | 324,039 + 220,972 | 2,508 | 547,519 | 0.16923 | 1,897.20 / 2,155.76 |
| 3mm | merge | 334,594 + 220,972 | 258 | 555,824 | 0.16670 | 1,799.34 / 2,063.61 |
| 3mm | both | 324,039 + 220,972 | 258 | 545,269 | 0.16993 | 1,884.50 / 2,143.79 |

| Final-visible origins, joint arm | sum-bits | 3mm |
| --- | ---: | ---: |
| Typed RHS under external root | 2,520 | 87,513 |
| Typed RHS under internally released root | 69 | 3,526 |
| Fresh strict merge return under external root | 75 | 979 |
| Fresh strict merge return under internally released root | 0 | 0 |
| Fresh separately paid child under external root | 3 | 223 |
| Fresh separately paid child under internally released root | 24 | 0 |
| Other dynamic birth under external root | 0 | 9 |
| Other dynamic birth under internally released root | 0 | 408 |
| **Total** | **2,691** | **92,658** |

On 3mm the partial route delivered 9,199 one-edge and 1,356 two-edge internal bindings. The merge route removed 2,250 external child proposals, returning 979 fresh and 1,271 pre-existing Smaller facts, with exactly the same physical identities as the independent leaf allocator. Sum-bits delivered 384 and 27 partial bindings and removed 99 paid merge children (75 fresh, 24 interned). No signed internal partial root performed the strict merge in these two programs: the measured improvement combines two independently admitted capabilities.

In the real joint 3mm stream the original root headers identified 107,921 Spine-tagged lanes and 8,384 merge-tagged lanes, with zero both-tagged and 428,706 ordinary lanes. Sum-bits counts were 3,387, 355, zero and 8,318. For example, the eight original bytes of the merge page for rule 507 were `fb 01 00 00 00 00 00 80`: template 507, no Spine code, a following bitmap with low bit set on its first lane. The checked 3mm and sum-bits bitmap costs were 1,105 and 79 bytes. The native codec fixture tests simultaneous tag bits separately, including the maximum accepted Spine code; it supplies no evidence of a both-tagged real producer.

Three (sum-bits) and 230 (3mm) changed old merge rows returned to the paid child path. Injecting stale partial returns produced zero signed commits, restoring actual external packet totals to 12,563 and 555,824. Full source semantics remained aligned. Corrupting either header field or the old row ID/version rejected the affected run explicitly. The integrated runtime is not faster than the leaf in these four-sample paired medians. The study contains no additional RSS measurement. [Native trials and independent source/physical checks](results.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/strict-joined-build"
python3 study.py "$exp" "$exp/strict-joined-build/session" "$exp/strict-joined-study"
python3 check_header.py "$exp/strict-joined-build"
python3 verify.py
```

[Explicit-parent metric](../../../docs/EXPLICIT_PARENT_FEPT.zh.md) · [Partial two-hop](../strict-partial-named-ports/README.md) · [Merge-return](../strict-merge-return/README.md)
