# Learned child-template allocation in the joint native Pass 3 executor

The single- and multi-witness providers execute together on one CPU Cell Graph. This experiment asks a stricter question than whether an allocation happens during a neural RHS. Does a sealed proposal **name its actual physical template and directly allocate that Cell id**?

The compiler recognizes a function merge of the form C(old,new), where the proposed new value was returned by an earlier constructor in the same source RHS. At a matching set effect, a second neural gate receives the identity of its already committed neural parent, the available candidate port, and a feature vector derived from pre-mutation state. Its learned decision is to issue or abstain for the statically typed child template. It runs before the merge and emits concrete parent-effect, old-function and candidate-constructor port references, both generations, operand keys, and the model-selected template. The template's semantics and port wiring come from the compiler. This is the frozen gate trained in the merge-result-port study on four other program families, with its threshold calibrated on training positives.

At the native dynamic constructor call the checker requires:

1. The original winning neural binding with the same source ordinal, rule and actual provider ticket.
2. The original live old function row and candidate constructor row, table, argument keys, values and generations.
3. The correct compiled template and the ordered old/new arguments of the actual requested constructor.

A valid token first probes the constructor key. A hit is reuse and receives **zero new physical Cell credit**. On a miss, the packet itself supplies the template and bound operands to the native Cell allocator and performs the insertion. The returned fresh id is logged at this branch. Missing, corrupted and stale proposals use the ordinary source implementation when fallback is enabled. Shadow checks the same token but never enters the packet allocator.

Every recorded child id is joined to a distinct native physical allocation event. The audit independently verifies its actual template, its actual parent after source deduplication, and that this id was not already counted in the parent's direct RHS-template set. Every assisted arm also has identical source schedule, ordered RHS/writes/Spine and final typed graph. The negative controls retain the same raw neural scores and positive decisions where applicable. The final ABI rechecks both port keys and confirms the exact local ticket index against the native multi-witness parent record.

| Program / seed | Neural / all RHS | Correct parent templates | Additional learned child templates | Directly named / all distinct fresh ids |
| --- | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 7,253 / 7,265 | 5,754 | 103 | 5,857 / 5,868 (99.81%) |
| sum-bits/1709 | 7,257 / 7,265 | 5,757 | 103 | 5,860 / 5,868 (99.86%) |
| dot-product/1703 | 6,702 / 6,704 | 5,536 | 128 | 5,664 / 5,682 (99.68%) |
| dot-product/1709 | 6,702 / 6,704 | 5,536 | 128 | 5,664 / 5,682 (99.68%) |
| gemm-bias-relu/1703 | 15,451 / 15,462 | 12,679 | 176 | 12,855 / 12,869 (99.89%) |
| gemm-bias-relu/1709 | 15,453 / 15,462 | 12,681 | 176 | 12,857 / 12,869 (99.91%) |
| stable-argmax/1703 | 8,181 / 8,190 | 6,731 | 101 | 6,832 / 6,841 (99.87%) |
| stable-argmax/1709 | 8,183 / 8,190 | 6,733 | 101 | 6,834 / 6,841 (99.90%) |

Dot-product seed 1703 has 416 possible neural-parent set sites. The gate issues 210 child packets, 82 return an interned result and 128 allocate a new id: 38 have a single-witness parent and 90 have a multi-witness parent. The latter include actual source ordinal 3465 at Run 327, multi ticket 1723, source rule 507's set effect 3, old row generation 323 and candidate generation 321. Its issued template 906 directly allocates Cell 3594. The permissive all-candidate control supplies 136 child allocations on dot-product. These figures do not establish that learned gating is required to instantiate the typed template.

Null, wrong-template, wrong-old/new, stale and shadow produce zero child allocations via the learned branch. Original RHS results and the physical allocation stream remain identical when fallback is enabled. Disallowing an unverified default fresh allocation for the nested constructor is a different intervention from disabling residual source matching. Under the learned gate it first fails at Runs 816, 875 and 1213 on sum-bits, dot-product and GEMM; stable-argmax completes. Null fails on all four. These experiments attain the specified coverage threshold, not autonomous completion of every source step. Some dynamic allocations during repair still have no winning neural source RHS.

CPU timings include the entire source inference with the parent heads, host verifier, residual matching, merge work and actual Cell allocation. Eight resident repetitions interleave ordinary joint execution, null, shadow and allocator-enabled learned arms. The learned path did not show a consistent end-to-end speedup. [Physical evidence by parent and fresh id](physical-ids.json) · [Controls and coverage](results.json) · [Native timings](timings.json)

## Reproduction

The plan and weights below are frozen outputs of the joint-witness and merge-result-port studies. The joint builder accepts --merge-child to install this overlay into its isolated source checkout. POLICIES contains the per-program plans and previously frozen single configs, and MULTI contains the per-seed multi model.json files. Numeric input weights, source images and truth are never reconstructed on behalf of the running policy.

    dir=benchmarks/pass3-cell-gpu/joint-merge
    python benchmarks/pass3-cell-gpu/joint-witness/build.py "$OUT/build" --merge-child
    python "$dir/evaluate.py" "$OUT/build/session" "$REF" "$FAMILIES" "$CAPTURE" "$POLICIES" "$MULTI" "$OUT/paired"
    python "$dir/timing.py" "$OUT/build/session" "$REF" "$FAMILIES" "$POLICIES" "$MULTI" "$OUT/paired" "$OUT/timed"
    python "$dir/check_results.py"

The default target arm uses the learned high-recall single head with explicit source residual and the frozen 3x learned multi head with sealed independent references and no multi residual.
