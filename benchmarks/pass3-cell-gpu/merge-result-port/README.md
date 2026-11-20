# A neural child can cite a merge program's actual constructor result

This native CPU Pass 3 ablation uses the figure 42 leaf policy as the parent generator. A second learned gate can issue a child continuation attached to that parent's set effect. Compilation recognizes a declared constructor merge C(old,new), an explicit constructor F whose result is the proposed new value, and a two-atom consumer joining C's second argument to F's result. The names Smaller, ExtractedExpr and TCPair are not special cases in the implementation.

The gate runs after its parent binding has won the ordered RHS, immediately before its set instruction executes. Its features include the preexisting key/value presence and equality, a numeric candidate-field scale, epoch and rule metadata. It receives the physical witness of the parent's earlier candidate construction. The future merge result and consumer match are not input features. The head is a logistic model fitted offline on four training source families. An all-source collector supplies post-execution training labels. Testing permits issuance only from an actual winning neural parent. The high-recall threshold uses the first percentile of the training positives. The all-neural control issues for every eligible winning neural parent.

The checker observes the *actual* dynamic constructor call of the declared merge, compares its two operands against the pre-set old and native candidate, and requires its returned class to equal the committed function result. It retains the exact constructor and candidate physical references. At the original consumer Run it checks visibility, seminaive ownership, current canonical operands and the consumer's whole LHS against these two references. A repeatable certificate may supply a further distinct RHS only after a checked row-version or canonical tuple change; an identical certified state cannot be reissued. A moved row needs a full canonical-key lookup and a checked result. Each credited ordinal is unique.

For typechecked source set 506 in sum-bits, the hook can name the actual output of its set effect 2. The merge produces a real Smaller(old,new) fact, and its second field is joined to the precise TCPair value constructed by the parent. Seed 1703 has a concrete transition from source RHS #2703 in Run 390 to RHS #2705 in a later consumer Run. Reversing the old and new ports refuses the packet. Repair-only births and ordinary exact parents receive no neural credit in this experiment.

## Source results

| Workload / seed | Eligible neural parents | High-recall issued | Child RHS | Second or later, after a version change | Withholding replacements first diverges at Run |
| --- | ---:| ---:| ---:| ---:| ---:|
| sum-bits/1703 | 27 | 9 | 6 | 3 | 391 |
| dot-product/1703 | 29 | 14 | 20 | 10 | 437 |
| gemm-bias-relu/1703 | 23 | 9 | 6 | 3 | 601 |
| stable-argmax/1703 | 20 | 11 | 6 | 3 | 421 |
| sum-bits/1709 | 27 | 9 | 6 | 3 | 391 |
| dot-product/1709 | 30 | 15 | 21 | 10 | 437 |
| gemm-bias-relu/1709 | 23 | 9 | 6 | 3 | 601 |
| stable-argmax/1709 | 20 | 11 | 6 | 3 | 421 |

The final implementation performs ordinary residual search and removes duplicates belonging to the validated children before constructing the source patch. The withholding arm removes those duplicates and also withholds the neural replacements. The resulting divergence shows the replacements supply real source work. The earlier one-shot control paid ordinary search even for the covered keys; its instrumentation reported overlapping bindings. This design still pays for the original matcher traversal, and these counts measure eliminated duplicate *commit inputs*, not eliminated residual traversal. Restricting the entire consumer rule to neural evidence also diverges; the current parent policy reaches only a fraction of its inputs.

All assisted controls check the complete ordered RHS, effective writes, Spine and graph. Timing includes the parent CPU policy, the extra gate, merge/union validation, ordinary residual and publication. Eight runs rotate and reverse the four relevant arms. Inference medians vary in both directions across the four programs. The observed extra coverage does not establish a consistent speedup or 98% autonomous inference. [One-shot study](one-shot-results.json) · [Versioned study and interventions](versioned-results.json) · [Paired wall times](timing-results.json)

## Reproduction

    dir=benchmarks/pass3-cell-gpu/merge-result-port
    cargo build --locked --release -p eggfuse-cell-runtime --features late-merge-ports,slot-transfer-audit
    runtime="$CARGO_TARGET_DIR/release/eggfuse-cell-runtime"
    python "$dir/study.py" "$runtime" "$FAMILIES" "$REF" "$UNIT_POLICY" "$PARENT_OBSERVATIONS" "$OUT/gates" "$OUT/gates" --fit
    python "$dir/study.py" "$runtime" "$FAMILIES" "$REF" "$UNIT_POLICY" "$PARENT_OBSERVATIONS" "$OUT/gates" "$OUT/paired"
    python "$dir/version_study.py" "$runtime" "$FAMILIES" "$REF" "$UNIT_POLICY" "$PARENT_OBSERVATIONS" "$OUT/gates" "$OUT/versions"
    python "$dir/timing.py" "$runtime" "$FAMILIES" "$REF" "$OUT/versions" "$OUT/timing"
