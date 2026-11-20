# Verifier placement for the same sealed forest

The policy runs exactly once per whole Pass 3 input after receiving static features and the initial graph summary. It emits the same six-word certificate envelope per typed candidate slot as the whole-pass experiment. The two empty-LHS roots are static compiler projections. The network chooses child activations. A child cites the root, its specific effect port, the consumer rule and its certified entrance. Both backends independently check parent identity, publication visibility, freshness and compiler-certified port roles. A universal one-atom certificate can instantiate the RHS inputs directly. Other accepted tokens can require exact suffix-table reads. Uncovered source obligations remain with the exact engine unless explicitly disabled.

### Allowed placements

* CPU PyTorch policy, one CPU thread, followed by the Rust verifier.
* GPU PyTorch policy followed by readback of the sealed certificate, then the same Rust verifier.
* GPU PyTorch policy followed by a Metal verifier consuming the device tensor.

The default-layout Rust Cell CPU runtime is compiled with the optional `precomputed-forest` feature. A native root commits through the usual source rule in the ordered RHS path. Each actual root output supplies a `Dependency` and publication generation. The verifier uses a currently visible native row and its typed parent address to construct an actual binding and query-fact receipts. The winning Spine cursor carries its unique token id through native deduplication into `begin_step` at commit. Exact residual and neural tokens use the same Rust Graph and source effects. The negative control `--forest-only` visits the named published roots/ports directly and has no residual native search. A wrong-parent control corrupts the input envelopes before static validation.

Gold traces and graphs are used after execution. On the native side the separate audited run checks each source Run, ordered binding digest, effective-write digest, actual Spine digest and final graph against the baseline runtime. Each execution separately reports active submissions, actual credited RHS ordinals, static roots and residual counts. Source ordinals for the same certificate slot are compared across backends. The independent event auditor aligns source identities by actual constructor births and checks the entire Metal/Rust trajectory against each other, including their own no-residual graphs after diverging from the original workload. A slot gains credit only if its verified cursor supplies the committed RHS.

## Full Pass 3 results

| Real source / seed | Static roots + learned child RHS | Remaining exact | CPU policy + Rust ms | GPU policy + Rust ms | GPU policy + Metal ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 2 + 91 | 7172 | 25.36 | 26.57 | 887.83 |
| sum-bits/1709 | 2 + 92 | 7171 | 25.63 | 26.45 | 883.71 |
| dot-product/1703 | 2 + 195 | 6507 | 20.68 | 22.14 | 940.77 |
| dot-product/1709 | 2 + 195 | 6507 | 21.45 | 22.58 | 944.32 |

Every neural RHS ordinal matched across all three placements, including which token supplied it. With ordinary source search disabled, both verifiers diverged from the source at Run 3; nevertheless each pair of autonomous executions agreed with one another on the entire truncated source schedule, all ordered RHS inputs, effective writes, Spine, class roots and final typed graph. Both sum-bits seeds stopped after 275 Runs, and both dot-product seeds stopped after 276.

The runtime placement dominates these measurements: the entire exact residual, rebuild, scheduling and ordered effects are executed by the selected backend. The timing difference between Rust and Metal cannot be assigned solely to the cost of validating the positive certificates. With Rust held fixed the synchronized GPU policy and readback did not pay for their overhead in this bounded forest. [Full timing, identities and audit data](results.json)

## Timing

Model weights, immutable program and candidate layout are resident. Rust creates a pristine graph before signaling readiness. The measured host interval covers the forward, transfer when required, binary certificate transport, validation, full inference and the reply. Only the dynamic little-endian int32 envelope tensor is sent to the resident Rust process. It uses the cached static catalog and validates every dynamic batch before source execution. Metal resets its initial graph outside the timer and synchronizes after full inference. The native graph digest and Metal per-Run arrays are checked after each timed pass. Six repetitions rotate and reverse all three placements. Separate audit CLI runs also include program loading, report serialization and graph export. These wall times have different boundaries from the resident comparison.

## Reproduction

```sh
cargo build --locked --release -p eggfuse-cell-runtime --features precomputed-forest,slot-transfer-audit
cargo build --locked --release -p eggfuse-cell-runtime --features precomputed-forest,slot-transfer-audit --example native_forest_session
dir=benchmarks/pass3-cell-gpu/native-forest
families="$EGGFUSE_ARTIFACT_ROOT/repair-bake-families-20261120"
ref="$EGGFUSE_ARTIFACT_ROOT/pass3-atlas-integration-20261120"
reader="$EGGFUSE_ARTIFACT_ROOT/rotary-axes-20261119/packed-1703/final.pt"
weights="$EGGFUSE_ARTIFACT_ROOT/whole-pass-generation-20261120"
python "$dir/study.py" "$families" "$ref" "$reader" "$weights" \
  "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" "$CARGO_TARGET_DIR/release/examples/native_forest_session" \
  "$EGGFUSE_ARTIFACT_ROOT/NEW-native-forest"
```
