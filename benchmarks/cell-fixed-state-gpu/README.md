# Fixed-path whole-Cell ridge on Metal GPU

This standalone experiment replaces the prior GPU node-by-node encoder. It uses
the same native-checked, five-rule multi-entry corpus and original grouped split:
272 training, 95 validation, 102 test entries, with 24 known completion classes.
No Rust runtime changes, effect publication or online lifecycle takeover occur.

## Representation

Bake-like compilation reads only each entry's static topology, with all scalar
values erased. It propagates fixed seeded real-valued operator/edge/literal
projections symbolically once to produce a per-layout affine matrix and bias.
This is structural algebra, not rule application, closure computation or fitting
to labels. Unlike the old encoder, there is no nonlinear operation at each node:
linearity allows all intermediate node calculations to be eliminated exactly.

For instance scalar slots v, the CPU constructs
`phi(v) = [v/4, (v/4)^2, sin(v), cos(v)-1]`, then
`x = concat(b_layout + phi(v) @ A_layout, static_metadata)`.
The result is a 72-dimensional real-valued Cell state. Metadata contains operator
counts and node/root/scalar counts, not layout IDs or target IDs. Node references
are static wiring, never numerical features. Layout-specific coefficients are
fixed random structural projections; learned ridge weights are dense floats.

Runtime projection reads a precompiled list of scalar positions: it does not
traverse edges. It still performs per-instance CPU work, explicitly charged.
This adapter reads exported arrays, not live compressed runtime slots. The
182 layout matrices consume 1,273,024 bytes across the corpus: precomputation is
not free storage. A future compressed-slot adapter must reuse existing ownership
and validity metadata. Dynamic Eq changes are not covered by this static-topology
fixture and cannot be silently omitted.

## Training and GPU execution

No backpropagation or gradient descent. Train-only means/scales and centers are
used; ridge is solved with linear algebra. Six candidate configurations (quadratic
or fixed random tanh, three regularizers) are ranked by validation macro accuracy
then micro accuracy. Test labels do not select weights/configuration. The shared
projection seed is fixed before this run. These are previously used test data,
so this is a development result, not a fresh blind generalization estimate.

The selected model is quadratic ridge with regularization 0.001. Normalization
and linear readout are folded into weights. GPU executes exactly:

```
Y = X @ L + square(X @ P + q) @ N + b
```

Three dense matrix multiplications, one elementwise square, fixed additions.
All layouts share one batch and one compiled function. No GPU node traversal,
hash lookup, union, conditional routing or saturation loop exists. The choice
between quadratic and tanh is made on the CPU once after training. CPU receives
24 class scores; this is known-template recognition, not generation of arbitrary
saturated graphs. MLX 0.32.4 Metal GPU is required; no CPU fallback.

## Results and limits

- Validation: 94/95; held entrance test: **92/102 (90.20%)**.
- Previous node-encoding model: 89/102. This changes the representation and fits
  new ridge weights; it is not merely a faster execution of the old model.
- GPU/CPU top-1 results agree on every test row; max score deviation 0.000079.
- Affine plan/reference equivalence checked on all 469 rows, plus 546 independent
  scalar perturbations across 182 layouts. Perturbation tests verify compilation,
  not additional semantic completion labels.
- Warm GPU numeric batch: 102 rows 0.283 ms; 1,632 rows 0.355 ms;
  13,056 rows 0.466 ms. Larger batches repeat existing inputs, not new evidence.
- CPU gathering and projection for 102 rows: 0.707 ms. Complete prototype request
  through GPU score return: median 0.923 ms (excluding proof/publication).
- The **same new model on CPU** takes 0.042 ms for numeric inference; therefore
  this small batch does not establish a GPU advantage over the new CPU path.
- Necessary containment checking costs 5.279 ms and accepts 3 wrong predictions.
  It is not a sufficient proof and does not authorize effects. Full derivability
  validation, lifecycle and publication remain unimplemented, not zero-cost.

The prior per-layout GPU prototype took ~15.7 ms for its 102-row encoding plus
ridge. The new fixed-path compute is much smaller, but comparing those numbers
alone omits CPU projection, changed model, precomputation and validation.
First GPU call was 484 ms; driver/compiler cache affects this. No claim about
actual egglog/eggcc runtime speedup is supported.

## Reproduce

Use the existing `cell-multi-entry-ridge` corpus-generation instructions, then:

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/run.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --output out/cell-fixed-state-gpu
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/check_projection.py \
  --corpus out/cell-multi-entry-ridge/corpus.json
```

The command trains, checks CPU/GPU equivalence, runs synchronized benchmarks and
writes model weights and results under untracked `out/`. Only source and text
results are committed. The saved report fingerprints the corpus. No performance
campaign or semantic changes to the CPU runtime were made.

## Typed projection and actual-slot benchmark (next iteration)

The original all-node/root sum loses operator-local information. Optional typed
pooling retains an additional affine sum for each of the five constructor types.
These sums are computed symbolically into the layout matrix; they add no GPU
traversal or dynamic routing. The selected model uses 64-dimensional structural
projections, giving `(2 + 5) * 64 + 8 = 456` state coordinates. All layouts still
share the same fixed GPU formula.

`tune.py` evaluates a declared grid on train/validation only: two structural
widths, three edge scales, typed pooling on/off, polynomial degrees 2/3 and five
ridge regularizers. Projection randomness uses one fixed seed, not a seed sweep.
Selection maximizes validation macro then micro accuracy, then minimizes validation
MSE, then prefers smaller state/degree. Only the frozen winner is evaluated on
test. Labels, validation selection and fit remain entirely CPU-side; no backprop.

A first grid without typed pooling reached 95/95 validation but remained 92/102
on test (`validation-only-results.json`). The expanded grid's winner reached
**97/102 (95.10%)**, versus 92/102 for the previous fixed-state baseline, with
95/95 validation (`tuned-results.json`). This is a previously examined development
test, not an untouched blind test. The type-pooling experiment was motivated by
the representation, but the procedure has now been iterated on this dataset.
A fresh fixed evaluation set is still needed for stronger generalization claims.
None of the five incorrect predictions pass necessary containment in this run;
that finite observation still does not make containment a proof of derivability.

### Read actual slots, then replay without graph traversal

The new Rust example `completion_slot_inputs` compiles each original input and
reads its constructor operands **before any rewrite Run**. It resolves scalar
fields through `Graph.argument`, which calls `Graph.slot` for slot operands.
It checks those values against ordinary row reads, exports source fingerprints,
and measures a warm precompiled operand-read list independently of compilation
and JSON export. This is a diagnostic example; it adds no runtime registry or
second maintained binding graph.

`bench_slots.py` verifies source hashes and exact initial graphs against the
labelled corpus. At setup it maps exported operands into each plan's scalar
positions. During timed replay it only reads scalar buffers through compiled
indices, performs the affine projection, and executes the single GPU function.
It does not reconstruct or traverse nodes in that timed path. This is **real
slot input captured and replayed**, not a live Rust-to-GPU completion callback.
The one-time graph adapter is still needed and is separately charged; moving
that mapping into compiler-native layouts remains outstanding.

All 469 admitted examples agree with their old corpus inputs and projection
reference; all 3,028 operand reads are actual slot reads, not literal constants.
The tuned projection also passes 546 independent scalar perturbation checks.
`slot-results.json` records timings and source artifact hashes. Layout matrices
now occupy 8,876,224 bytes across 182 layouts (versus 1,273,024 previously), and
the 102-row GPU input grows from 29,376 to 186,048 bytes. Accuracy has a storage
and projection cost, not a free improvement. Device model weights use 567,200
bytes. Timings vary with concurrent activity; these short diagnostics are not
an actual eggcc speedup or a controlled runtime performance campaign.

```sh
cargo build --locked -p eggfuse-cell-compiler --example completion_slot_inputs
./target/debug/examples/completion_slot_inputs \
  out/cell-multi-entry-ridge/inputs.json out/cell-fixed-state-gpu/slot-inputs.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/tune.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --output out/cell-fixed-state-gpu/typed-pooling
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/check_projection.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/bench_slots.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --slots out/cell-fixed-state-gpu/slot-inputs.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --output out/cell-fixed-state-gpu/slot-results.json
```

## Native projection and expanded-entrance stress test

`emit_native_plan.py` freezes shared affine matrices plus operand addresses into
an artifact. The artifact is assembled from the checked initial-instance adapter,
not yet emitted directly by the general Cell compiler. The release Rust example
`completion_project_slots` creates fresh actual Graph instances, verifies the
source hash and operand-owner template, and reads `Graph.slot` directly into the
affine projection. It never exports, canonicalizes, enumerates witnesses or
interprets node edges to produce vectors. Addresses are only valid for the exact
unchanged initial fixture; this is not a producer/op universal-address assumption
and does not support relocation across Runs. No prediction authorizes effects.

`bench_native_states.py` checks those native vectors against Python projection,
then feeds one batch into the unchanged fixed GPU model. On 102 original test
instances, prediction remains 97/102; max vector difference is 2.39e-6. Native
warm release projection sums to 0.079 ms over the 102 instances; synchronized GPU
numeric execution is 0.359 ms. These are separate component measurements, not an
end-to-end speedup: source compilation, serialization and subprocess transport
are excluded. A corrupted owner template is rejected before projection.

A stronger entrance test exposes the model's remaining weakness. Before model
evaluation, `generate_holdout.py` froze 120 extra sources by adding facts already
present in each parent's known completion. `collect.py` ran actual Cell and
native egglog executions with a one-second per-case timeout and two unchanged
verification Runs. All 120 completed graphs agree with native and retain the
expected completion. Generation deliberately uses completion graphs; this tests
additional entrances to the known catalog, not natural traffic or novel targets.
The model is frozen and is not refitted for this test.

After deduplicating initial graphs:

| Cohort | Correct / total |
|---|---:|
| All unique generated inputs | 38 / 108 |
| Inputs absent from the original corpus | **20 / 90** |
| Skeletons absent from the original corpus | **18 / 82** |

Thus the 95.10% original development result does **not** establish robust
multi-entry completion. Adding already derivable facts changes the additive
feature state too much. This failure is preserved in `holdout-results.json` and
must remain visible during further representation/training changes. Once used
to guide development, this cohort is a stress/development set, no longer blind.
No test exclusions or correctness rules were broadened to improve the result.

Reproduce (regenerate addressed slot export after updating the Rust example):

```sh
cargo build --locked -p eggfuse-cell-compiler --example completion_slot_inputs
./target/debug/examples/completion_slot_inputs \
  out/cell-multi-entry-ridge/inputs.json out/cell-fixed-state-gpu/slot-inputs-addressed.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/emit_native_plan.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --slots out/cell-fixed-state-gpu/slot-inputs-addressed.json \
  --inputs out/cell-multi-entry-ridge/inputs.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --output out/cell-fixed-state-gpu/native-plan.json
cargo build --locked --release -p eggfuse-cell-compiler --example completion_project_slots
./target/release/examples/completion_project_slots \
  out/cell-fixed-state-gpu/native-plan.json out/cell-fixed-state-gpu/native-states.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/bench_native_states.py \
  --states out/cell-fixed-state-gpu/native-states.json \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --output out/cell-fixed-state-gpu/native-results.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/generate_holdout.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --inputs out/cell-multi-entry-ridge/inputs.json \
  --output out/cell-fixed-state-gpu/fresh-inputs.json
python3 benchmarks/cell-multi-entry-ridge/collect.py \
  --inputs out/cell-fixed-state-gpu/fresh-inputs.json \
  --runner target/debug/examples/real_completion_dataset \
  --output out/cell-fixed-state-gpu/fresh-runtime.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/evaluate_holdout.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --runtime out/cell-fixed-state-gpu/fresh-runtime.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --output out/cell-fixed-state-gpu/holdout-results.json
```

## Learning tolerance to redundant established facts

The next iteration keeps the typed affine representation and fixed quadratic GPU
formula unchanged. It augments only train/validation **source parents** with
already-derived constructor facts, then obtains labels from actual Cell and
native executions. There is no closure or extra graph interpretation at inference.
240 training-parent and 120 validation-parent cases were collected independently,
with the same one-second per-case timeout and native/fixed-point checks.

`train_augmented.py` rejects duplicate entries and any augmented skeleton that
collides with another original split or the frozen stress cohort. Training
augmentation is admitted first; validation augmentation also excludes those
training skeletons. Parent identity/split and expected completion are checked.
The stress set's structure is used only to protect against overlap, never to fit
weights or choose regularization. An intentionally wrong completion label is
rejected. Original train/validation/test assignment remains unchanged.

169 train and 80 validation augmentations survive (441 train, 175 validation
rows total). Five regularizers are selected by equally weighting original and
augmented validation accuracy, then validation MSE. No new projection seed,
representation or test-dependent branch is selected. Validation is 173/175
(95/95 original plus 78/80 augmented). Full logs and accepted IDs are preserved
in `augmented-results.json`.

| Frozen evaluation cohort | Before | After augmentation |
|---|---:|---:|
| Original development test | 97/102 | 95/102 |
| Additional previously unseen entries | 20/90 | **80/90** |
| Additional previously unseen skeletons | 18/82 | **75/82** |
| All unique additional inputs | 38/108 | 97/108 |

The original test loses two correct cases; the stronger entrance test improves
substantially. This establishes learned tolerance on these finite cases, not
mathematical invariance to arbitrary redundant facts. The stress set has already
influenced the decision to augment training, so it remains a development stress
test even though its labels do not select parameters. Targets are still the same
24 known completion classes.

State width remains 456. Ridge center count grows from 272 to 441, model weights
from 567,200 to 892,356 bytes. GPU remains three matmuls plus a square; there is
no gradient training or runtime graph traversal. Warm numeric GPU inference for
102 states measured ~0.257 ms in the training run; native-produced states were
also checked with the new model, giving identical top-1 predictions and 95/102.
The separate native run measured ~0.170 ms total projection plus ~0.365 ms GPU;
short-run variation and excluded transport prohibit an end-to-end speed claim.

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/generate_holdout.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --inputs out/cell-multi-entry-ridge/inputs.json \
  --split train --limit 240 --output out/cell-fixed-state-gpu/augment-train-inputs.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/generate_holdout.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --inputs out/cell-multi-entry-ridge/inputs.json \
  --split validation --limit 120 --output out/cell-fixed-state-gpu/augment-validation-inputs.json
python3 benchmarks/cell-multi-entry-ridge/collect.py \
  --inputs out/cell-fixed-state-gpu/augment-train-inputs.json \
  --runner target/debug/examples/real_completion_dataset \
  --output out/cell-fixed-state-gpu/augment-train-runtime.json
python3 benchmarks/cell-multi-entry-ridge/collect.py \
  --inputs out/cell-fixed-state-gpu/augment-validation-inputs.json \
  --runner target/debug/examples/real_completion_dataset \
  --output out/cell-fixed-state-gpu/augment-validation-runtime.json
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/train_augmented.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --train-runtime out/cell-fixed-state-gpu/augment-train-runtime.json \
  --validation-runtime out/cell-fixed-state-gpu/augment-validation-runtime.json \
  --stress-runtime out/cell-fixed-state-gpu/fresh-runtime.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --output out/cell-fixed-state-gpu/augmented
```

The previous native-plan/projection commands work with `augmented/model.npz` too;
regenerate the native plan because it binds the model hash. The new model should
not be tested against old model-bound native-state files.

## Coverage and bounded-center experiments: regressions retained

The next run expanded generated sources to 720 training-parent and 240
validation-parent cases. Previously collected cases were reused; only 480 new
training and 120 new validation cases were executed, each with the existing
one-second limit. `merge_collection.py` rejects duplicate IDs and retains source
chunk fingerprints/collector provenance. After the same overlap/duplicate
exclusions, 472 additional training and 129 additional validation entries were
admitted (744 training and 224 validation rows total).

This was **not an improvement**. Validation selected all 744 centers with ridge
0.001; original test fell to 93/102, new entrances to 76/90, new skeletons to
72/82. Weights grew to roughly 1.48 MB. The previous 441-center model remains the
retained baseline, with 95/102 and 80/90 respectively. The larger validation set
is harder, so its accuracy must not be compared directly with the old 175-row
validation accuracy.

`--center-budgets` adds a training-input-only greedy coverage selector. It starts
at the point nearest the training mean and repeatedly chooses the point farthest
from selected centers; labels, validation and test do not choose center positions.
Validation chooses budget/regularization, with tied accuracy preferring fewer
centers then lower MSE. Budgets 128/272/all did not beat the full-center validation
score. This is an offline training cost, not GPU control flow.

A second search compared quadratic and radial ridge features at 272/all centers
and radial widths 0.25/1/4. Radial features did not win validation. Radial GPU
execution, when selected at model load time, is the fixed expression
`XL + exp(min(XP+q - sum(X²*s), 0))N+b`: three matmuls and fixed reductions and
pointwise operations, with no input-dependent dispatch. Normalization constants
are folded into weights, including the center/mean cross-term. Independent
random-input CPU/GPU folding checks cover both feature kinds and three widths;
unknown model kinds are rejected.

Two further representation candidates divide each static pooling group by its
size or square root of size. Factors are folded into layout coefficients at
compile time. They scored only 205/224 and 211/224 validation correct versus
215/224 for sums; neither was evaluated on test. All three projection modes
match their reference on all 469 original inputs (1,407 checks). New modes are
optional; the default sum preserves the old representation. Model loaders now
read this metadata and reject unsupported GPU feature kinds instead of silently
running a quadratic function for a radial artifact.

`feature-search-results.json` preserves the failed searches, source hashes,
admitted IDs, validation logs and measured costs. These results narrow the next
work: more examples, smaller centers or simple normalization alone have not
solved completion invariance. No stronger accuracy claim is made this round.

To reproduce expanded collections, run `generate_holdout.py` with `--split train
--limit 720` and `--split validation --limit 240`, then use the existing collector.
To reuse saved prefixes instead, collect only IDs absent from the old files and
merge the two disjoint chunks:

```sh
python3 benchmarks/cell-fixed-state-gpu/merge_collection.py \
  --inputs out/cell-fixed-state-gpu/augment-train-runtime.json \
           out/cell-fixed-state-gpu/extra-train-runtime.json \
  --output out/cell-fixed-state-gpu/expanded-train-runtime.json
```

Apply the same merge to validation. Run `train_augmented.py` with the expanded
runtime files and `--center-budgets 272,all --feature-kinds quadratic,radial`.
For validation-only representation comparisons add `--pool-normalization mean`
or `sqrt` and `--validation-only`; this writes no model and never evaluates test
scores. `check_gpu_model.py` checks folded GPU arithmetic independently of data.

## Learn a foldable entrance projection (no gradients)

`train_invariant.py` freezes the prior augmentation admission manifest, checking
its input hashes and split isolation. Only training vectors/labels build the
within-completion scatter `Sw` and between-completion scatter `Sb`. It solves a
regularized generalized eigenproblem via symmetric eigendecompositions. Validation
chooses shrinkage, rank and the final quadratic ridge regularizer; test and stress
labels do not build the projection. This is a supervised discriminant projection,
not a proof that all entrances become identical. Optional training-only PCA
residual directions are also tried; no additional runtime traversal results.

Near-zero discriminant eigenvalues are excluded using training spectrum rank.
An early residual trial included null directions beyond the at-most-23-dimensional
between-class signal; folding exposed amplified float cancellation. The trial
failed the numerical gate and was not exported. The implementation now skips
unsupported discriminant ranks rather than relaxing the error threshold.

For a learned affine map `x_new = x_old S + t`, each shared layout is rewritten:

```
A_new = A_old S_dynamic
b_new = concat(b_old, static_metadata) S + t
```

The native runtime reads the same slots and directly computes the reduced state.
There is **no 456-dimensional runtime intermediate or extra GPU projection**.
`model_projection.py` checks dimensions/finite values and folds once per layout.
It is used by export, replay and native-input verification. GPU inference remains
three matmuls and a square; no backpropagation or device-dependent dispatch.

On the 441-row training / 175-row validation admission, validation selects 16
discriminant dimensions and no PCA residual. It scores 172/175 validation,
91/102 original test, 80/90 new entrances and 74/82 new skeletons. The previous
456-dimensional model scored 95/102, 80/90 and 75/82. **This is a compression
tradeoff, not a new accuracy win; it does not replace the accuracy baseline.**

Using the same 182 original layouts gives a fair storage comparison:

| Quantity | 456-D model | Folded 16-D model |
|---|---:|---:|
| Shared affine layout matrices/biases | 8,876,224 B | 316,800 B |
| GPU input for 102 cases | 186,048 B | 6,528 B |
| Device ridge weights | 892,356 B | 73,956 B |

`invariant-slot-results.json` verifies all 469 real-slot inputs. The unchanged
native projection runner consumes the new folded artifact; all 102 predictions
match the Python reference, max state discrepancy 3.58e-6. Native projection
sums to 0.0116 ms and GPU inference ~0.360 ms in that diagnostic. Python adapter
replay remains ~1.28 ms because gathering/interpreter/materialization costs remain.
Component timings exclude transport and do not establish runtime acceleration.
546 perturbed scalar tests also pass with the folded model.

Repeating the projection search on expanded training admission selected 31 state
dimensions (23 discriminant plus 8 PCA), improving its validation to 221/224 but
only scoring 89/102 and 74/90 on the two test cohorts. It is retained as a failed
generalization experiment in `invariant-expanded-results.json`, not adopted.
Thus a small floating state is feasible, but better validation scores still do
not reliably transfer to unseen entrance structure.

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/train_invariant.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --train-runtime out/cell-fixed-state-gpu/augment-train-runtime.json \
  --validation-runtime out/cell-fixed-state-gpu/augment-validation-runtime.json \
  --stress-runtime out/cell-fixed-state-gpu/fresh-runtime.json \
  --admission benchmarks/cell-fixed-state-gpu/augmented-results.json \
  --model out/cell-fixed-state-gpu/typed-pooling/model.npz \
  --residual-ranks 0,8,16 --output out/cell-fixed-state-gpu/invariant
```

Use that `model.npz` with the existing check_projection, emit_native_plan,
completion_project_slots and bench_native_states commands. `fold_plan` folds
projection metadata automatically; old unprojected models remain supported.
The expanded trial instead uses expanded runtime files and the original expanded
admission artifact, whose fingerprint is recorded in its results.

## Fixed blend reaches 90% on the additional-entrance benchmark

A completion-structure target-code experiment first compared categorical targets
with normalized vectors of training completion graphs. A fixed nearest-code
readout was folded into the last weights. Validation selected zero structural
weight, reproducing the 95/102 and 80/90 baseline; it was not an improvement.
Logs are in `structured-target-results.json`. The experiment remains catalog
classification, not arbitrary generation of completion graphs.

The 456-D and 16-D models make partly different errors. `blend_models.py` freezes
both models and selects a blend from {0, .25, .5, .75, 1} on validation only,
with tied validation scores preferring fewer device bytes. It selects .5 and
174/175 validation correct. No test/stress labels select the blend. The new
entrance cohort is an already-examined development stress set, not a blind test.

| Fixed cohort | Prior augmented model | Selected blend |
|---|---:|---:|
| Original development test | 95/102 | 94/102 (92.16%) |
| Previously unseen additional entrances | 80/90 | **81/90 (90.00%)** |
| Previously unseen skeletons | 75/82 | 75/82 (91.46%) |
| All unique additional inputs | 97/108 | 99/108 |

This is one extra correct new entrance, not a large or statistically established
accuracy gain. The original set loses one correct prediction. Earlier model and
failure reports remain intact; none of the failing samples was excluded.

### Exact algebraic reduction, not another learned stage

Directly concatenating both branches keeps three matmuls but needs 1,740,840
weight bytes. `compile_blend.py` instead expands the 16-D branch's quadratic:

```
H[i,j,c] = sum_k P[i,k] P[j,k] N[k,c]
l' = l + 2 P diag(q) N
b' = b + square(q) N
```

Its 441 center activations become a fixed 16x16 outer-product feature. Both the
original state and the 16-D projection are folded into the shared layout, so
runtime directly generates a 472-D vector; it does not execute a separate state
conversion. GPU evaluates the selected blend using **four fixed matmuls**, a
square and an outer product. A constant slice selects the last 16 coordinates.
There is no graph traversal, input-dependent branch, search, saturation loop or
backpropagation. The fourth matmul trades a small fixed operation for less weight
storage; it must not be described as the earlier three-matmul implementation.

Device weights decrease to 946,692 bytes, approximately 6.1% above the original
augmented model rather than nearly double. State width is 3.5% larger than that
baseline. Host/layout/serialization storage is separate from this device figure.

67 arbitrary real inputs check the algebra against independent branch evaluation.
`check_blend.py` then checks 589 original and generated rows: all top-1 outputs
agree, maximum score discrepancy 1.48e-5. The reduced model independently retains
81/90 on the frozen stress cohort and 94/102 through the native slot runner.
546 scalar perturbations pass the folded-layout test. Native projection totals
0.080 ms for 102 instances, and synchronized GPU compute ~0.506 ms in the saved
run. These are separate component timings, excluding compilation/transport and
correctness authorization. No eggcc/egglog end-to-end speedup is established.

Reproduce the selected blend and exact reduction:

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/blend_models.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --validation-runtime out/cell-fixed-state-gpu/augment-validation-runtime.json \
  --stress-runtime out/cell-fixed-state-gpu/fresh-runtime.json \
  --admission benchmarks/cell-fixed-state-gpu/augmented-results.json \
  --left out/cell-fixed-state-gpu/augmented/model.npz \
  --right out/cell-fixed-state-gpu/invariant/model.npz \
  --output out/cell-fixed-state-gpu/blended
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/compile_blend.py \
  --left out/cell-fixed-state-gpu/augmented/model.npz \
  --right out/cell-fixed-state-gpu/invariant/model.npz \
  --selection out/cell-fixed-state-gpu/blended/results.json \
  --output out/cell-fixed-state-gpu/compact-blend
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/check_blend.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --stress-runtime out/cell-fixed-state-gpu/fresh-runtime.json \
  --left out/cell-fixed-state-gpu/augmented/model.npz \
  --right out/cell-fixed-state-gpu/invariant/model.npz \
  --compiled out/cell-fixed-state-gpu/compact-blend/model.npz \
  --selection out/cell-fixed-state-gpu/blended/results.json
```

Run emit_native_plan, completion_project_slots and bench_native_states with the
compact-blend model, regenerating model-bound artifacts. Run evaluate_holdout
with that same model and the frozen fresh-runtime file. These are the sources
of `compact-blend-native-results.json` and `compact-blend-holdout-results.json`.

The benchmark now demonstrates the requested chain: offline numeric layout
compilation, direct real-instance slot projection, one fixed GPU batch and
measured improvement on multiple entrances. Its scope remains five actual
rules and a catalog of 24 known completions, with initial-instance address
binding. General cross-Run binding/lifecycle support, compiler-native layout
discovery, novel-completion generation and authorized runtime effect takeover
are not established by this benchmark.

## Same computation on CPU versus GPU

`compare_cpu_gpu.py` runs the compact blend's identical float32 equations and
native-produced vectors on NumPy CPU, MLX CPU and Metal GPU. Each measurement
uses three warmups and 30 timed repetitions; MLX results are explicitly evaluated
before stopping the clock. CPU library threading defaults are retained (not a
single-thread comparison); NumPy build configuration is saved in the report.

Warm numeric medians in milliseconds:

| Batch rows | NumPy CPU | MLX CPU | Metal GPU |
|---:|---:|---:|---:|
| 102 | 0.085 | 0.100 | 0.431 |
| 1,632 | 1.052 | 1.006 | 0.588 |
| 13,056 | 8.130 | 8.411 | 1.284 |

At the natural 102-row batch CPU is about 5x faster than GPU. At 13,056 repeated
rows GPU is about 6.3x faster than NumPy for resident numeric execution. Using
already-available host states and returning host scores, MLX CPU/GPU medians are
0.108/0.452 ms at 102 rows and 8.628/1.661 ms at 13,056 rows. Timings are separate
runs, so do not subtract medians to infer transfer cost (noise can even make the
host-boundary median lower than the resident median). Metal shared memory is not
a discrete PCIe upload. Repeated rows are throughput probes, not new test data or
proof that the runtime can form those batches.

All CPU/GPU top-1 results agree. Maximum GPU score error versus NumPy is 2.06e-5;
MLX CPU matches NumPy exactly on these inputs. These measurements exclude live
slot extraction/projection, compilation, semantic verification and publication.
They are not end-to-end egraph timings. Full medians and percentiles are retained
in `cpu-gpu-results.json`.

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-fixed-state-gpu/compare_cpu_gpu.py \
  --model out/cell-fixed-state-gpu/compact-blend/model.npz \
  --states out/cell-fixed-state-gpu/compact-blend/native-states.json \
  --output out/cell-fixed-state-gpu/cpu-gpu-results.json
```
