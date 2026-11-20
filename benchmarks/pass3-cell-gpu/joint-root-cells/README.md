# Physical root Cells from the sealed neural recipe

The CPU policy chooses the source rule and stable witness addresses. The compiler supplies the Cell template and a typed projection program for the rule's RHS inputs. This experiment puts those fields into an actual binary payload at the time the single candidate or independent multi-parent tuple is issued, before the suffix checker is invoked. A winning root is credited only if the allocator receives the decoded template **and the slot buffer constructed from that payload**, and actually stores a new physical Cell id.

The wire uses little-endian words. A packet records its ABI, raw serial, provider, source occurrence, rule, Cell template, number of selected references and number of input projections. Each selected reference records the LHS atom, address kind, stable Cell/operation or function row id, and generation. Each input projection records its destination slot, source atom and column, and table or checked-primitive role. These deterministic field descriptions do not need to be learned. They are serialized here to make the transport and its cost explicit.

The verifier decodes that payload, checks the exact source version, validity of each reference and the immutable rule layout, and builds a newly owned typed slot buffer. Table projections read the actual verified witness rows. Primitive-produced fields use the result of the exact typed operation already performed by the source verifier. The winner retains the completed recipe through the single-witness Mark or multi-witness Ticket carried by the native binding. No reference result or externally supplied binding enters this path.

At the original ordered RHS, the checked packet supplies its template and passes a clone of its owned operand buffer into source execution. The ordinary frame path, writer path and first-miss completion/prefix paths receive that chosen template; the completion engine no longer independently selects the root template when creating a frame. Fresh-id credit occurs only immediately before a real root store. Avoided/temporary frames and later promotions earn no fresh-root credit. The nested merge child retains its separate checked allocator. Every credited root is compared against the independent physical event and its winning binding ordinal. Parent and nested id sets must be disjoint.

| Program / seed | High roots + nested / all fresh | Certified roots + nested / all fresh | Certified neural / source RHS |
| --- | ---: | ---: | ---: |
| sum-bits/1703 | 5,754 + 103 / 5,868 (99.81%) | 5,764 + 103 / 5,868 (99.98%) | 7,265 / 7,265 |
| sum-bits/1709 | 5,757 + 103 / 5,868 (99.86%) | 5,764 + 103 / 5,868 (99.98%) | 7,265 / 7,265 |
| dot-product/1703 | 5,536 + 128 / 5,682 (99.68%) | 5,538 + 128 / 5,682 (99.72%) | 6,704 / 6,704 |
| dot-product/1709 | 5,536 + 128 / 5,682 (99.68%) | 5,538 + 128 / 5,682 (99.72%) | 6,704 / 6,704 |
| gemm-bias-relu/1703 | 12,679 + 176 / 12,869 (99.89%) | 12,690 + 176 / 12,869 (99.98%) | 15,462 / 15,462 |
| gemm-bias-relu/1709 | 12,681 + 176 / 12,869 (99.91%) | 12,690 + 176 / 12,869 (99.98%) | 15,462 / 15,462 |
| stable-argmax/1703 | 6,731 + 101 / 6,841 (99.87%) | 6,740 + 101 / 6,841 (100.00%) | 8,190 / 8,190 |
| stable-argmax/1709 | 6,733 + 101 / 6,841 (99.90%) | 6,740 + 101 / 6,841 (100.00%) | 8,190 / 8,190 |

For dot-product seed 1703 in the high arm, 55,821 single raw offers and 21,210 multi tuples generated 22,393,600 recipe bytes. The winning 6,702 recipes supplied real source RHS inputs. 5,536 caused a fresh primary store and 128 additional, disjoint fresh ids came from explicit merge-child packets. The remaining 18 fresh ids have no direct learned construction credit. In the certified arm the two additional RHS bindings also supply their physical root descriptors.

## Counterfactuals and limitations

* Withhold the root packet, corrupt its template or reference version, or verify the packet while withholding it from allocation. In every such assisted control the ordinary source path restores the same state and physical allocation stream, and the number of physical roots allocated by the packet path is zero. The merge-child intervention remains separately controlled.
* Forbid the ordinary fallback at the point where an actual primary source Cell must be stored. A correctly issued certified root descriptor completes the entire schedule in all eight workload/seed pairs. The high arm requires root fallback at Runs 102 / 135 / 171 / 114 on sum-bits, dot-product, GEMM and stable-argmax respectively. Withholding all recipes or corrupting the first one under a no-fallback policy fails at Run 1.
* Forbid both the default root store and default nested construction. With certified roots the first missing nested template occurs at Runs 816 / 875 / 1213 on the first three programs; stable-argmax completes with all 6,841 fresh ids credited. Exact checking and ordinary graph maintenance still run throughout these experiments.

The binary proof format is not optimized for size or speed. Source inputs are projected and checked on the native CPU and all raw offers may pay serialization cost. For certified seed 1703, adding this root protocol to the previous joint system changes inference medians from 81.24 to 94.74 ms (sum-bits), 78.37 to 90.47 (dot-product), 248.30 to 283.06 (GEMM), and 78.21 to 91.15 (stable-argmax). The experiment establishes causal construction and coverage with a measured cost. The baseline and root-wire timings each have eight paired interleaved samples, including checking and fallback work. [Per-arm coverage and controls](results.json) · [Per-id ledger hashes, actual recipe examples and byte counts](physical-proof.json) · [Both fallback policies disabled](combined-forbid.json) · [Timings](timings.json)

## Reproduction

    dir=benchmarks/pass3-cell-gpu/joint-root-cells
    python benchmarks/pass3-cell-gpu/joint-witness/build.py "$OUT/build" --shortlist --merge-child --root-recipe
    python "$dir/study.py" "$OUT/build/session" "$REF" "$FAMILIES" "$CAPTURE" "$POLICIES" "$MULTI" "$MERGE_CONFIGS" "$CERTIFIED_PATTERN" "$OUT/paired"
    python "$dir/forbid.py" "$OUT/build/session" "$REF" "$FAMILIES" "$CAPTURE" "$POLICIES" "$MULTI" "$MERGE_CONFIGS" "$OUT/paired" "$OUT/forbid"
    python "$dir/timing.py" "$OUT/build/session" "$REF" "$FAMILIES" "$POLICIES" "$MULTI" "$MERGE_CONFIGS" "$OUT/paired" "$OUT/timed"
    python "$dir/package.py" "$OUT/paired" "$OUT/physical-proof.json"

POLICIES contains frozen per-workload typed plans and high-recall checkpoints from the joint study. CERTIFIED_PATTERN supplies the source-checked per-seed single weights. Graphs, ordered bindings, write/Spine histories and physical allocation streams are validated after execution.
