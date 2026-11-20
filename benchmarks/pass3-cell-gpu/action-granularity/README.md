# Figure 42 — how much source work can one emitted certificate authorize?

This comparison uses single-threaded native Rust policy inference and the authoritative Rust Cell runtime on actual eggcc Pass 3. PyTorch trains offline and independently checks the native recurrence after execution. Each source Run permits one emission per row, with two rows. A two-member unit can earn two actual source RHS ordinals from one emission. The roots, learned choices, private latent history, weights and issuance budgets agree within each three-arm comparison.

| Emission | Packet | Verification |
| --- | --- | --- |
| Raw binding | Source rule and pivot, physical anchor, proposed physical suffix witness when present, explicit RHS input tuple | Check the proposed rows, column positions, equality constraints, visibility, delta eligibility and every bound value. Failed references leave the binding for ordinary source search. |
| Certified leaf | Leaf template ID and anchor | Instantiate the typed key plan. A required suffix may be found by exact key even when its row lies beyond the pointer head's candidate bank. |
| Executable macro | One library unit ID and anchor | Decode its first entrance, producer effect and second entrance. If the root wins an actual source RHS, keep that exact published effect as the named parent for the second member. Check visibility and remaining boundary conditions when the original consumer Run executes. |

No separate child token is issued by the macro arm. The winning native cursor carries the issuance identity through deduplication into the source commit. Republishing a row under another producer does not authorize the old child. A credit requires a distinct actual winning RHS ordinal.

For sum-bits seed 1703, Run 98 row 0 issued unit 32 at native anchor address 80. The library decodes it as leaf 3, effect 2, then leaf 5. Its first member won RHS #413. Its actual effect published native fact (Cell 541, operation 2). The second member won RHS #536 at Run 102. Both have the same certificate issuance identity.

## Actual source measurements

The 32-leaf sum-bits library has 15 frozen two-leaf units. Each root selects among up to eight typed native anchor positions. The raw pointer head selects from up to eight rows of the appropriate suffix table. All root queries in this frozen library have one or two table atoms. The model trains on four source program families, and uses only their witnessed successes as binding or continuation labels. Its pointer head receives true witness-rank labels only after a training route completes. The four training families provided 51, 47, 46 and 37 in-window suffix-rank observations. Sum-bits is the library donor and GEMM-bias-ReLU and stable-argmax are held-out program families.

Native forward reads current typed rows, epochs and published cursor features and its own preceding eight-float per-row latent. It selects the root, a compatible complete unit id, and an explicit-witness preference internally before emitting any certificate. The raw and leaf arms retain identical latent updates when their packet formats cannot express a proposed continuation. The independent PyTorch rollout starts from zero and consumes its own last token throughout the source schedule.

| Program / seed | Active certificates | Raw RHS | Leaf RHS | Macro RHS | Certificates winning two RHS | Source exact / macro inference ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 136 | 58 | 59 | 80 | 21 | 28.4 / 32.4 |
| sum-bits/1709 | 132 | 54 | 56 | 76 | 20 | 29.6 / 33.8 |
| dot-product/1703 | 96 | 50 | 50 | 64 | 14 | 26.1 / 33.0 |
| dot-product/1709 | 98 | 46 | 46 | 55 | 9 | 26.0 / 30.7 |
| gemm-bias-relu/1703 | 94 | 43 | 44 | 59 | 15 | 55.7 / 60.7 |
| gemm-bias-relu/1709 | 96 | 42 | 43 | 57 | 14 | 54.3 / 62.3 |
| stable-argmax/1703 | 80 | 41 | 42 | 58 | 16 | 29.8 / 34.0 |
| stable-argmax/1709 | 80 | 35 | 36 | 47 | 11 | 29.3 / 34.4 |

The larger action increases committed work in every pair, but inference is slower than source exact search. Ordinary search supplies most bindings. Each assisted arm checks ordered RHS, effective writes, Spine digests, birth/union events and final native state. Without residual search all three grammars miss the initial empty-LHS rule and diverge on the first Run. Separately corrupting the second witness can invalidate a raw binding while assisted source execution stays aligned.

Eight native CLI repetitions per timed arm rotate and reverse order. Per-pass inference includes candidate construction, native recurrent forward, checks, residual matching, source effects and rebuild. CLI samples also include startup, loading and export. Logical size estimates assume an int32 action/slot address and int64 per explicit RHS input. These exclude the shared private latent and do not measure native heap bytes. An independent Metal control checks the same weights/library on both anchor programs for one seed. Each backend uses its actual physical table ordering. [Native results](results.json) · [Device control](metal-control.json) · [Final unit-id decoder](confirmed.json)

## Reproduction

Run in the external workspace environment with MPS fallback disabled for the offline capture and independent Metal control.

    dir=benchmarks/pass3-cell-gpu/action-granularity
    families="$EGGFUSE_ARTIFACT_ROOT/repair-bake-families-20261120"
    ref="$EGGFUSE_ARTIFACT_ROOT/pass3-atlas-integration-20261120"
    reader="$EGGFUSE_ARTIFACT_ROOT/rotary-axes-20261119/packed-1703/final.pt"
    original="$EGGFUSE_ARTIFACT_ROOT/recurrent-receipts-20261120"
    targets="$EGGFUSE_ARTIFACT_ROOT/recurrent-composition-targets-20261120"
    out="$EGGFUSE_ARTIFACT_ROOT/NEW-action-units"
    mkdir -p "$out"
    python "$dir/capture.py" "$families" "$ref" "$reader" "$original" "$out/capture"
    python "$dir/model.py" "$ref/sum-bits/program.json" "$original" "$targets" "$out/capture" "$out/model"
    cargo build --release --locked -p eggfuse-cell-runtime --features action-units,slot-transfer-audit
    cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" "$out/runtime"
    python "$dir/native_study.py" "$families" "$ref" "$out/model" "$out/runtime" "$out/paired"
    python "$dir/confirm.py" "$out/runtime" "$families" "$ref" "$out/paired" "$out/confirmed"
    python "$dir/metal_control.py" "$families" "$ref" "$reader" "$out/model" "$out/metal"
