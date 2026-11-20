# Joint deployment of native PGO and union-aware request activation

The [native backend study](../native-backend-pgo/README.md) measured profile-guided code generation while its two-view learned Rust issuer used the original root search. The [incremental subscription study](../incremental-request-ports/README.md) measured how changing the issuer and maintaining its projection indexes across table updates and unions affected a separately built binary. This experiment links the incremental provider, re-collects its LLVM profile with that new path active, and executes the two choices inside each deployed binary.

The plain and instrumented learned binaries are compiled from the same Rust source tree and use the same one-unit code generation, target, allocator, frozen weights and release optimization as the matched LLVM comparison. The instrumented binary runs sum-bits, dot-product and Jacobi three times each, with reverse activation and actual displaced-class repair enabled. Each training run must perform real reverse activation, transfer checked function parents and repair stale subscriptions across unions. The compiler receives a fresh merged profile from this executable. The training programs, sealed plan identities, source outcomes and repetition counts match the separate earlier donor cohort. Both conjugate-gradient and 3mm remain held out. The exact PGO reference is the previously measured, independently trained default CPU executable. An ordinary default release is separately included as the speed target.

On the learned arms, **original** uses shared single-parent headers and delayed arithmetic before the original multi-parent issuer. **Union** activates the compiled complete-key function request from changed source/target ports, transfers its checked physical function source, and updates stable subscriber addresses using table deltas and displaced equivalence classes. Both choices retain the original ordered source verifier and perform the same source RHS. A compiler profile collected with the latter active is used for *both* settings on the PGO binary, so changing one request option isolates the provider in that exact executable.

A separate native default audit records all ordered source RHS, writes, Spine, unions, schedule and final state. Every learned arm also checks old winning parents, actual fresh Cell IDs and absence of residual matches. Raw streams agree across codegen within a provider. The two providers can produce slightly different numbers of false raw candidates before exact verification. Timed requests assert active provider counters and source results again. Four interleaved resident repetitions after warm-up include the whole inference, with process setup and final export outside that interval. API round-trip additionally charges graph/model setup, export and reply decoding. Permission to choose a provider makes no claim that the dispatch itself was learned.

The separately trained PGO original issuer is also tested in a second interleaved matrix. Disabling activation in the new binary could otherwise make its original code path cold in the optimizer's feedback. Comparing against the independent original-trained executable shows the combined deployment difference, including the cost of linking the new code.

## Complete native execution

| Held-out program | Default exact | Exact PGO | Plain original | Plain union | PGO original | PGO union, ms | Joint / default exact | Joint / PGO exact |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 358.38 | 302.70 | 617.90 | 616.99 | 539.21 | 530.00 | 1.48× | 1.75× |
| 3mm | 878.79 | 757.00 | 1,910.42 | 1,855.46 | 1,599.17 | 1,673.44 | 1.90× | 2.21× |

With activation enabled the fresh PGO image took 14.10% less time than its plain compiler control on conjugate-gradient and 9.81% less on 3mm. Both improved on all four native timing pairs. Changing the issuer inside the same PGO image gave a 1.71% lower CG and 4.64% higher 3mm median. The activation itself was faster in just two of four pairs in each codegen mode and each workload. These samples establish a code-generation gain without a reproducible additional win for the route switch. CG joint API round-trip was 623.48 ms versus 465.77 ms default and 401.47 ms profiled exact; 3mm was 1,880.68 ms versus 1,111.96 ms and 962.41 ms. [Signed source/physical ledger, timings and activity](results.json)

Training the fresh compiler profile executed 112, 106 and 112 cross-union repairs on sum-bits, dot-product and Jacobi respectively in each repetition; 378 / 462 / 1,904 checked function references were transferred. Its linked runtime IR carries positive donor-derived entry counts on 876 functions, with a subscription routine receiving 1,476 observed entries. The joint 3mm runtime made 10,510 direct function requests, built 10,326 directory rows, patched 10,365 addresses and directly transferred 8,415 function references. Trained code generation preserved the raw stream, accepted parent source identities, original 294,917 RHS and 229,311 directly allocated IDs out of 229,880 fresh Cells. [Donor hashes, codegen and activity evidence](build-evidence.json)

## Fresh profile control

| Held-out program | Original-trained PGO, original search | Activation-trained PGO, original search | Activation-trained PGO, union search | Faster joint vs original-trained pairs |
|---|---:|---:|---:|---:|
| conjugate-gradient | 578.13 | 574.32 | 565.23 | 3/4 |
| 3mm | 1,723.66 | 1,741.01 | 1,709.11 | 3/4 |

This compact run used the exact frozen binaries from the two detailed source audits, with no retraining. It rechecked final graph, Run/RHS counts, root allocations, raw tuple counts and active union-repair counters on every request. The joint median improved on the separately trained original by 2.23% on conjugate-gradient and 0.84% on 3mm. The ordering of the activation-trained on/off arms on 3mm differs from the main six-arm measurement. The data support native PGO across these programs and leave the incremental provider as a workload-sensitive choice. [All four samples and round-trip times](profile-transfer.json)

## Reproduction

Use the source trees and disjoint donor programs of the two linked studies. Start each output in a fresh directory. The old benchmark directory contains the two independently trained vanilla/learned profiles; the new build reads only its vanilla binary and training identities for comparison.

```sh
d=benchmarks/pass3-cell-gpu/profiled-request-ports
python "$d/build_joint.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/joint-compile"
python "$d/study_joint.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/joint-compile" "$EXP/joint-test"
python "$d/profile_transfer.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/joint-compile" "$EXP/joint-test" "$EXP/profile-transfer"
python "$d/archive_joint.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/joint-compile" "$EXP/joint-test" "$EXP/profile-transfer"
python "$d/verify.py"
```
