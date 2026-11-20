# Training a CPU keep/compose action on two existing owners

This experiment compiles a nine-parameter policy into the decision boundary of the pinned native Cell CPU storage experiment. The executor discovers a compiler-checked component. Its two distinct old owners must still cover all component members, permit transfer at the settled Run boundary and have an externally observed output. A one-time policy call sees eight counts from the current storage layout. For each of the destination and source owner it sees the number of members, slots and fact operations. It also sees the number of distinct birth epochs and source templates. The model receives no workload, rule ID, absolute epoch, owner address, future consumer or allocation result. An immutable receipt binds the decision to both physical owners and their member IDs, the component shape, current epoch, weights, features and score. Verification and the immediate keep/merge run in one synchronous native call. This is a physical representation decision. The original exact source matcher selects every RHS and enumerates the eligible owner pair.

## Training

Four generated source programs contain a typed producer chain, a downstream reader, and different numbers of additional effects and input roots. Four separate workload programs (affine-twins, clamped-ramp, segmented-prefix and window-laplacian) supply a second distribution. We Bake a source-local fragment catalog and prepare two independently allocated old owners at an eligible component. Two split positions and two candidate-skip counts are tried. These interventions can yield the same physical state or no pair; they are not independent program families. Each resulting decision has a native keep run and a native compose run from the same initial program. Before assigning credit the collector checks old members, readable source rows, external readers, all prefix Run checks and the resulting graph. The immediate reward for composing is allocator bytes freed minus bytes requested *inside the physical action*. Keeping has reward zero. Every admitted transfer retires one old owner, so always-compose is also the optimizer for rewarding only the count of owners retired. Peak extra bytes are separately observed. The experiment does not train on wall time.

The sixteen eligible synthetic episodes lost 32–488 bytes under forced composition, across eight distinct feature vectors. Of sixteen attempted workload episodes, ten had a pair. Their four distinct feature vectors yielded two positive and eight neutral rewards. Segmented-prefix supplied no eligible state at these preparation points. The same local vector `[2,1,4,1,3,1,3,2]` saved 96 bytes on clamped-ramp and zero on affine-twins and window-laplacian. The marginal allocator response depends on more state than these counts capture.

PyTorch trains a linear Bernoulli policy by differentiating the exact expected paired return, `sigmoid(score) * saved_bytes`, with L2 regularization. Zero initialization and full-batch updates are deterministic. Each curriculum gets 160 updates. Real-only and synthetic-only use a single sample pool. Synthetic-then-real switches pools after update 80. Joint replay uses the concatenated dataset at every update, so its full batches contain more examples. A fifth policy uses the identical joint-replay batches, model, regularizer and optimizer to regress the measured return difference directly with squared error. This loss was added after inspecting the three original evaluations. Two further workload families (GEMM-bias-ReLU and gated-state) were reserved before evaluating it. The checkpoint folds the constant input scaling into the exported eight coefficients, rounds coefficients and bias to multiples of 1/4096, and the native CPU gate composes for positive logit. The Python audit independently checks the weights and scalar score against the action, then compares the full source trajectory and graph to a separate reference. The token hash identifies this in-process issue and provides no external authentication. No policy is refitted on test programs.

## Native action results

Signed entries are the measured reduction in requested live heap bytes inside the transfer. A keep action gives zero. Every row in the table had two already allocated owners at the prepared boundary. Parent enumeration, source matching, the audit read of old ports and the policy itself are outside this byte delta.

| Prepared source | Always compose | Real only | Synthetic only | Synthetic then real | Joint expected reward | Joint return regression |
|---|---:|---:|---:|---:|---:|---:|
| Four-stage fixture, near the generated training structure | −224 | −224 | 0 | 0 | 0 | 0 |
| dot-product | +124 | +124 | 0 | 0 | 0 | 0 |
| stable-argmax | +96 | +96 | 0 | 0 | 0 | +96 |
| GEMM-bias-ReLU, prospective | +100 | — | — | — | 0 | 0 |
| gated-state, prospective | +96 | — | — | — | 0 | +96 |

Only keep, always-compose, joint expected reward and joint return regression were deployed on the two prospective programs. These two policies see the same paired training data at every update. Regression captures 96 of 196 available bytes on the prospective pair and 192 of 416 across the four prepared Pass 3 decisions. Its two chosen transfers each temporarily require an additional 304 bytes. A synthetic warm start alone did not recover the missing benefit; all synthetic-initialized expected-reward policies kept both owners everywhere they were evaluated. These are three initial decisions and two prospective decisions, not a workload-wide speed measurement. The dot-product and GEMM misses show the model still leaves useful actions unchosen. [Paired training measurements](train.json) · [Frozen parameters](policies.json) · [Native issuer and allocation receipts](test.json) · [Prospective controls](fresh.json)

In normal pooled traffic the number of components meeting the two-whole-owner requirement was **zero** on each program. The prospective natural control counted eligibility with the original census, and the first three programs enabled the actual frozen gate on natural traffic. Native source-local Bake used each program to discover candidate shapes, so this experiment tests action selection on new source families with an already available catalog. For every policy, independent checks compared each Run's ordered RHS, effective writes, Spine resumes, committed unions, and the final graph. Old references and subsequent external readers agreed with keeping both owners. No admission, source RHS or runtime speedup on a natural workload is credited to this gate.

## Reproduction

Use the parent [existing-owner transfer build and catalog instructions](../existing-owner-transfer/README.md) to produce the base pinned build, its bake executable, and the three evaluation program catalogs. The implementation compiles new Rust code into a separate copied source tree.

```sh
d=benchmarks/pass3-cell-gpu/owner-action-policy
python "$d/build.py" "$BASE" "$EXP/action-build"
python "$d/collect.py" "$EXP/action-build/engine" "$BAKER" "$CORPUS" "$EXP/action-data"
python "$d/train.py" "$EXP/action-data/train.json" "$EXP/action-weights"
python "$d/evaluate.py" "$EXP/action-build/engine" "$EXP/action-weights" "$CATALOG" "$CORPUS" "$EXP/action-test"
python "$d/fresh.py" "$EXP/action-build/engine" "$BAKER" "$EXP/action-weights" "$CORPUS" "$EXP/action-fresh"
python "$d/verify.py" --fresh "$EXP/action-fresh/fresh.json" --train "$EXP/action-data/train.json" --policies "$EXP/action-weights/policies.json" --test "$EXP/action-test/test.json"
```
