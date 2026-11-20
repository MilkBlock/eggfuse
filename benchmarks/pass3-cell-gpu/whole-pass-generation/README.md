# Whole-pass generation before validation

Generate the complete proposal tensor before the source scheduler takes its first step. The MPS policy has access to the compiled program, static initial fact counts and its own generated root latents. It receives no Run numbering, actual iteration counts, live device rows, observed RHS, verifier feedback or reference trace. A compiled nullary rule can issue a root; a neural child names the root token, an effect port and a certified consumer entrance. Every possible typed edge from these roots has one candidate position. The network learns to activate those positions. Parents remain symbolic at generation time.

This bounded policy generates a two-level forest. The empty-LHS roots are compiler-selected; credit to the neural generator counts only accepted child proposals that win a distinct source RHS ordinal. The learned model scores all statically compatible candidate edges. It cannot invent additional levels or cover bindings outside this grammar. All generated tokens are available together for verification. The execution includes the following distinct costs.

1. The GPU checks every generated proof envelope in a batch before starting source execution. For a single table atom with distinct fresh slots, every row in the named parent port relation supplies its entire LHS. The compiler determines the precise RHS-input permutation from the lowered program. The global sweep can mark this binding program proved.
2. The source executor resolves the reference when the named parent's actual RHS wins the source commit and executes that exact effect. It records the physical row and its publication generation. At the original consumer Run it validates generation, visibility, and delta ownership. A prechecked proof materializes projected fields directly. A multi-atom entrance performs exact residual boundary checks. Source-order processing and publication still occur. Several source occurrences can attempt a token. They never invoke the network.
3. Optional ordinary Metal search completes uncovered obligations. A negative control disables it. Stable order, effective writes, Spine events, union events, class representatives and the final typed graph are compared with the CPU-aligned source reference after execution.

The only neural output frame is the sealed set of proposed edges. Preparation of typed candidate slots and initial counts is an offline compiler step. In the isolated test the online worker reads only the compiled plan NPZ, matching device image/manifest and frozen weights. Exact source iteration counts and labels never cross this boundary. The no-residual and assisted passes must yield identical neural tensors byte for byte.

The **point** arm freezes the same tokens and verifies even precheckable bindings through the ordinary point route. The **all** arm activates every statically compatible edge, providing a deterministic comparison with the neural selector. The **wrong-parent** arm corrupts every parent reference before the global sweep. The **none** arm retains only projected roots. The **no-residual** arm uses exactly the learned forest and removes the exact fallback from every source Run. The **exact** arm runs the existing GPU engine without this policy or verifier.

The model has a 12-field root latent and a shared MLP for children. Parent/consumer features include table and consumer identities, program/initial-graph sizes, effect position, arities and the initial cardinality of the parent effect’s table. The training targets come from the actual publication ordinals and consumed parent ports in four train-only program families. Sum-bits, dot-product and two held-out families are evaluation programs. No training/test artifact enters the GPU generator except the checkpoint and the evaluation program's own static inputs. The adapter specializes a fresh in-process copy of the shared executor with narrow checked insertion points. Upstream source mismatches fail explicitly.

## Observed full Pass 3 execution

Each row includes two compiler-projected empty-LHS bindings. Child credit requires an actual unique source RHS ordinal with matching parent ordinal, effect port, row and publication generation. Times are resident medians over six interleaved samples, including the complete neural forward and global sweep, verification, residual search, source commit and synchronization. Offline compilation and post-run audits are outside this interval.

| Program / seed | Emitted children | Global projection won | Additional suffix check won | Unused children | Remaining exact RHS | Assisted / exact ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 94 | 89 | 2 | 3 | 7172 | 936 / 873 |
| sum-bits/1709 | 98 | 90 | 2 | 6 | 7171 | 931 / 874 |
| dot-product/1703 | 195 | 185 | 10 | 0 | 6507 | 976 / 926 |
| dot-product/1709 | 195 | 185 | 10 | 0 | 6507 | 971 / 916 |
| gemm-bias-relu/1703 | 207 | 207 | 0 | 0 | 15253 | 3033 / 2947 |
| gemm-bias-relu/1709 | 207 | 207 | 0 | 0 | 15253 | 2947 / 2890 |
| stable-argmax/1703 | 128 | 128 | 0 | 0 | 8060 | 962 / 936 |
| stable-argmax/1709 | 129 | 128 | 0 | 1 | 8060 | 951 / 899 |

With seed 1703, sum-bits emitted 94 children, of which 91 committed. Turning on every candidate supplied 96 children and raised post-publication point-route or projection attempts from 169 to 2,084. Dot-product supplied 195 of the 201 credits observed with all candidates active. Each accepted child consumes a potential source obligation only when its recorded parent generation, current schedule and surviving binding agree. The learned domain covers a small portion of the entire workload even when the classifier ranks nearly all of its available winners correctly.

Without residual search, sum-bits still committed its two compiler roots and 91 / 92 neural children, and dot-product two roots and 195 / 195 children. All four workloads and both seeds diverged at the third source Run. A complete set of valid positive proofs in this forest does not specify all other source-rule matches. [Raw execution and timing](results.json) · [Per-proof attribution](proof-counts.json)

## Freezing one forest across two checker schedules

The dense arm visits the static candidate range of every scheduled consumer, including inactive positions. The event-driven arm creates port subscriptions in one GPU pass after the entire forest is generated. When a parent effect is published its subscribers enter the matching consumer queue. At legal activation only that queue is visited. A displaced generation or a completed obligation is removed. Both arms preserve the original source scheduler, checked parent identity and effective publication order. For every case the study compares actual GPU tokens and the global RHS ordinal of every individual root and child. A proof-only verifier declines every sealed proposal that lacks a universal projection proof. The accepted neural bindings in this arm require zero suffix-table searches. It also runs without exact residual search. Eight resident repetitions per timed arm include neural generation and disposition of unused proposals. Diagnostics separately count candidate-slot visits. [Event-driven ablation](event_study.py)

For seed 1703 the event path visited 263 scheduled candidates on sum-bits, versus 57,422 with dense scheduling. It retained all 91 neural commits and lowered median time from 894 to 879 ms (exact engine 849). Dot-product visited 390 versus 138,850, retained 195 commits and took 946 versus 973 ms (exact 922). The stricter proof-only arm committed 89 and 185 model children respectively through projected fields, with zero suffix lookups for those children. The complete MPS generator plus independent global envelope sweep took 0.46–0.53 ms across two seeds and the two anchor workloads in the isolated phase benchmark. [All event timings](event-results.json) · [Isolation evidence](isolated.json)

## Reproduction

Run in the external EggFuse workspace with PyTorch MPS. The experiment owner keeps traces under the workspace experiment root.

```sh
dir=benchmarks/pass3-cell-gpu/whole-pass-generation
families="$EGGFUSE_ARTIFACT_ROOT/repair-bake-families-20261120"
labels="$EGGFUSE_ARTIFACT_ROOT/recurrent-compositions-train-20261120"
ref="$EGGFUSE_ARTIFACT_ROOT/pass3-atlas-integration-20261120"
reader="$EGGFUSE_ARTIFACT_ROOT/rotary-axes-20261119/packed-1703/final.pt"
out="$EGGFUSE_ARTIFACT_ROOT/NEW-whole-pass"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/policy.py" "$families" "$labels" "$out"
python "$dir/study.py" "$families" "$ref" "$reader" "$out" "$out/paired"
python "$dir/proof_counts.py" "$families" "$ref" "$out/paired" "$out/by-proof.json"
python "$dir/event_study.py" "$families" "$ref" "$reader" "$out" "$out/events"
python "$dir/isolated.py" "$families" "$ref" "$reader" "$out" "$out/isolated"
```
