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
