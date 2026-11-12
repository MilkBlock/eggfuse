# Dense real transitions with algebra-guided training

Standalone finite-teacher research, not an EggFuse runtime takeover. The
teacher, structural splits and 32-dimensional PCA encoding come from
`../cell-real-state/study.py`. State and weights are dense signed real values.

The transition is an action-conditioned quadratic ridge residual. Training
adds examples computed from the model's own predicted states:

- Applying the same action again should reach the same target (idempotency).
- A second action should reach the teacher's composed target.
- The reversed action order should reach that same target when both orders
  remain entirely in training states.

Teacher target states are used only as supervised labels. Runtime does not
decode bits, query the teacher, look up nearest states, or force a true
intermediate embedding. It clips each real coordinate to a fixed bound
derived solely from the training states (1.25 times the maximum absolute
coordinate, at least 1). This continuous box constraint is not projection
onto a valid symbolic state. FP16 state/weights and FP32 dot products follow
the previous study's numerical conventions.

Two regularizers (1 and 10), seven iterations each were specified before
reading test results. Selection prioritizes validation whole-trajectory
correctness, then single-step accuracy. The test set is evaluated once for
the selected checkpoint. Both training endpoints are train states; all
composition intermediates and targets also remain in train states.

Selected: regularization 10, iteration 3. Validation full 12-step trajectory
accuracy is 31.98%. On the held-out test set:

- Single-step complete state correctness: **76.92%**.
- Full 12-step trajectory correctness: **28.85% (180/624)**.
- No nonfinite rollout state; final maximum absolute latent coordinate
  remains bounded. Full changed/no-op counts are in `results.json`.

This improves stability over the earlier unconstrained quadratic ridge, but
does not satisfy semantic takeover requirements. No GPU or speed measurement
was performed. The result combines augmentation and clipping; it is not a
clean ablation attributing improvement to a single algebraic constraint.
The validated algebra applies only to this finite positive closure, not to
arbitrary ordered egglog effects.

Reproduce using a fresh output directory:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=4 out/cell-real-state/venv/bin/python benchmarks/cell-real-algebra/study.py --output out/cell-real-algebra/new
```

`load(path_to_model_npz)` returns `(model, encode, decode)`.
`encode(facts)` produces initial real states; `model.step(z, actions)` takes
an array of action indices; `decode(z)` returns observation scores without
modifying the states. The numeric model is saved in the ignored output
directory. No generated binary model is committed.

## Fixed-configuration ablation

The parent requested a predeclared 2×2 ablation at regularization 10 and three
augmentation iterations. These arms were not used to select a new model.
Clipping is consistently enabled or disabled during both augmentation and
inference.

| Arm | Single-step exact | Changed | No-op | 12-step whole trajectory |
|---|---:|---:|---:|---:|
| Original ridge, no clipping | 77.11% | 70.94% | 93.73% | 0/624 |
| Original ridge, clipping | 77.11% | 70.94% | 93.73% | 4/624 |
| Augmented ridge, no clipping | 77.15% | 70.42% | 95.26% | 0/624 |
| Augmented ridge, clipping | 76.92% | 70.17% | 95.13% | 180/624 |

The unclipped original/augmented models encounter nonfinite FP16 states at
step 5/7 respectively. Neither clipping alone nor augmentation alone produces
the selected model's stability. This supports an interaction between the two
changes, without establishing semantic correctness. Raw counts and model
configuration are retained in `ablation-results.json`.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=4 out/cell-real-state/venv/bin/python benchmarks/cell-real-algebra/ablation.py --output out/cell-real-algebra/ablation-new
```

The original predetermined sweep was rerun after adding `load_adapter`;
`results.json` now hashes the current `study.py`, and reproduces the same
checkpoint and test results. `load_adapter(path, precision='fp16'|'fp32')`
provides `encode`, `step`, and `decode`. FP32 mode retains the same already
quantized weights, while removing activation/state FP16 rounding.
