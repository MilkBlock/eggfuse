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
