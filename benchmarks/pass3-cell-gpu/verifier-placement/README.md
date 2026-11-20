# Three placements and typed integer requests

The current matrix measures CPU weights with a Rust verifier, GPU weights with a Rust verifier, and GPU weights with a Metal verifier. Use the same sealed proof stream and report generation, transfer, validation, actual committed work and residual source execution. The earlier [network-placement experiment](../neural-device/README.md) includes a historical CPU-to-GPU diagnostic. The C++ version used for earlier CPU-prefix timings and the Rust implementation below have different binaries.

## The same closed-prefix certificate in Rust and Metal

Each of the 9 / 13 token positions names a member of a compiler-proved closed constructor domain. The neural network chooses a parent and activation over 24 waves without intermediate verification. A five-word token encodes presence, result identity, parent address, depth and value. Depth and value follow from the compiler's projection along the neural parent. Rust and Metal both check order, origin, bounds, depth, signed integer recurrence and every uncovered member after generation. Neither implementation appends missing children. A missing terminal leaf leaves all remaining proofs legal and one member uncovered. Other controls corrupt a parent, depth or value.

| Whole prefix, median ms | CPU weights + Rust | GPU weights + Rust | GPU weights + Metal |
|---|---:|---:|---:|
| sum-bits, 1703 | 0.856 | 5.165 | 5.268 |
| sum-bits, 1709 | 0.871 | 5.314 | 5.476 |
| dot-product, 1703 | 0.886 | 5.383 | 5.375 |
| dot-product, 1709 | 0.878 | 5.132 | 5.297 |

Each of the 24 interleaved repetitions includes generation, transfers to the selected verifier and obtaining the final host verdict. These figures start with the weights, compiled program and graph resident. The result covers the initial 8 / 10 source Runs, including the setup rule, using one final coverage check. The [full Pass 3 forest study](../native-forest/README.md) separately measures the authoritative Rust Cell graph and the Metal graph on the wider vocabulary. [Prefix samples and controls](prefix.json) · [Rust predicate](src/lib.rs)

## When an exact integer decides the next Cell

The compiler can place integer information in different places depending on its use.

* An internal arithmetic value with a unique definition can stay symbolic. A successor can name the producing effect port; the checker computes it when it resolves that port.
* A branch implied by a known literal can be folded at Bake time. Rule 143, for instance, constructs a SubTuple of literal length 1. No CPU question remains about whether its length exceeds 1.
* A dynamic guard can be compiled into the sealed certificate as a conditional. The CPU graph reads its authoritative version and dispatches the valid arm. When the answer completely determines the next instruction, this takes one publication/check boundary without another network call.
* An early reply may help if unresolved alternatives would consume expensive neural slots or private descendants. Request a typed value or a small branch mask, carry the producer address, generation and epoch, and retain the underlying proof reference. An answer can guide neural choice even when its threshold alone cannot establish a future match. Final verification still checks every external premise and source visibility.

The Rust diagnostic exposes one read-only operation. It compares a signed 64-bit port value with the compiled threshold, checks handle, epoch and publication ticket, and returns below/equal/above or stale. It cannot mutate the graph or choose an arbitrary rule. Compilation recognizes a one-constructor literal alternative paired with a greater-than guard on the same field. In these images the pair is rules 137 / 138 on the SubTuple length. Lengths below one lie outside both branches of this pair. Other source rules can still consume that constructor.

We replay exact historical publication events on a Rust integer snapshot. A small GPU categorical head is fitted on four disjoint training families using the producer rule and effect. The blind arm chooses its most likely branch and folds proven literal values. The deferred arm emits symbolic requests and asks Rust to resolve the whole sealed list once. The interactive arms request only dynamic ports and return the exact branch codes to the GPU, either individually or grouped by source epoch. The conditional control is a compiled branch dispatch. The diagnostic measures branch choices and the cost of moving information across the boundary; it does not credit actual RHS to a new online generator.

| Reference publications | Events | Compile-time literals | Dynamic requests | Changed blind choices | Epoch batches | Deferred / epoch / individual, ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 446 | 220 | 226 | 42 | 42 | 0.232 / 16.621 / 87.294 |
| dot-product | 267 | 165 | 102 | 10 | 18 | 0.227 / 7.631 / 41.301 |
| GEMM-bias-ReLU | 991 | 478 | 513 | 51 | 30 | 0.239 / 12.700 / 215.875 |
| stable-argmax | 473 | 242 | 231 | 30 | 19 | 0.233 / 7.100 / 85.973 |

The named neural-origin cohort is smaller. Of these events, 35 / 18 on the two anchors came from the seed-1703 pending-parent actor's winning RHS. All these events had compile-time literal length. The corrected 42 / 10 choices occur in the broader source publication stream. No subsequent expensive neural generation was charged in this replay. The empirical conditional entropy of the legal threshold branch given producer rule and effect is 0.195 / 0.130 bits on the anchors. The exact ternary reply determines the branch in this restricted pair, while unrelated premises and endpoint coverage remain unknown. Nine rotated timing samples per arm include all device synchronizations. [Raw requests and timings](transactions.json)

## Reproduction

```sh
dir=benchmarks/pass3-cell-gpu/verifier-placement
e="$EGGFUSE_ARTIFACT_ROOT"
cargo test --locked --manifest-path "$dir/Cargo.toml"
python "$dir/matrix.py" "$e/pass3-atlas-integration-20261120" "$e/closed-prefix-learned-20261120" "$e/NEW-three-way-prefix.json"
python "$dir/transactions.py" "$e/pass3-atlas-integration-20261120" "$e/repair-bake-families-20261120" "$e/recurrent-compositions-train-20261120" "$e/recurrent-compositions-20261120" "$e/compound-pending-pass3-v1/paired" "$e/NEW-integer-requests.json"
```
