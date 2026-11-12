# Enhanced continuous-state ridge

Standalone finite-teacher research, not the EggFuse runtime or a GPU benchmark.
This continues `../cell-real-algebra`, preserving its structural split, teacher,
32-dimensional train-only PCA encoder, decoder and original Run-free model.
No native semantic acceptance rules are changed.

## What improved

The selected model retains idempotency, composition and reverse-order training
examples generated from its own predicted states. It standardizes features
when solving ridge, folds that scaling into the final weights, and replaces
560 quadratic features with 288 linear/cubic projection features:

```
z: 32 signed fractional coordinates
C: 256 training-state latent centers (fixed after compilation)
phi(z) = concatenate(z, (1 + z C^T / 32)^3)
next(z, action) = clip(z + phi(z) W_action + b_action, -bound, bound)
```

This is dense real arithmetic. Every center contributes a smooth feature; it
does not retrieve the nearest state, choose a stored successor, decode Boolean
facts between steps or invoke symbolic repair. Only initial encoding and final
scoring touch observations. FP16 coefficients/features/states and FP32 matrix
accumulation are simulated with NumPy; no hardware claim follows.

Feature standardization is computed only from admitted training examples,
separately per action. It changes the ridge penalty to reflect feature scale;
it is folded into the matrix, so it adds no inference normalization pass.
The frozen model was selected on validation at cubic/256 centers, lambda=1,
augmentation iteration 5.

## Independent results

Every successful trajectory has all 155 observations correct at every step.
The initial structural states remain held out from training. Models were frozen
before the fresh sequence seeds were evaluated; sequences share the same finite
state domain, so these are new action sequences, not new independent graphs.

| Fresh sequence length | Previous ridge | Enhanced ridge |
|---|---:|---:|
| 12 (seed 49999) | 195/624 | 257/624 |
| 48 (seed 67867967) | 161/624 | 207/624 |
| 96 (seed 32452843) | 147/624 | 178/624 |

On the prior independent evaluator's fixed sequences, counts improve from
173/183/155 to 219/241/202 (12/12/48 steps). Exhaustive ordered event-pair
correctness improves from 29,775/45,084 to 31,112/45,084. Single-event correctness
slightly declines, from 2,040/2,652 to 2,027/2,652. This is improved autonomous
composition, not a universal accuracy improvement. Neither model passes the
finite semantic gate or the sole held-out rule-enabled boundary-feedback event
(both 0/1, with 24 wrong observation bits). No runtime takeover is justified.

The failure still involves a constructor equality enabling a boundary union.
Its target is in training; it cannot be dismissed as an unseen target. Further
work must retain this slice, not train on the known failing test example.

## Experiments and selection history

1. `study.py`: predeclared 4 representations x 2 regularizers x 5 checkpoints.
   Tried 8-step predicted trajectories, feedback weight 8 versus 1, and radial
   exponential features with 128/256 centers. Every trajectory intermediate and
   target remains in training; only five admitted direct feedback edges exist.
   The selected long-trajectory quadratic model scored 150/624 on the original
   12-step test sequence, below the preceding ridge's 180/624. It did improve
   one 48-step sequence, but did not establish an overall improvement. Weighting
   rare feedback did not win validation. Keep these negative results.
2. `anchored.py`: following that result, fixed 3 feature families x 2
   regularizers x 7 checkpoints. Restored the previous exact augmentation sample
   and used train-only feature standardization throughout. Best validation
   12-step scores: quadratic 229/616, radial 229/616, cubic 230/616. The previous
   unnormalized model had 197/616. Thus normalization with retained anchors is
   promising; the near tie does NOT establish that cubic features caused most
   of the gain. The chosen cubic representation is also smaller.
3. The existing independent evaluator and `fresh.py` scored frozen selected
   models. No test scores selected checkpoints. These follow-up experiments are
   adaptive research on an already inspected finite teacher, not a pristine
   external benchmark. All validation checkpoints and unsuccessful study
   outcomes are preserved in `results.json`.

## Cost accounting

- Persistent latent state remains 32 scalars.
- Feature width falls from 560 to 288.
- Per-action transition banks fall from 305,184 to 157,216 scalars; the new
  projection centers add 8,192, for 165,408 total (excluding common encoder,
  decoder and bounds).
- Old output projection uses 17,920 multiply-accumulates per row. The new
  center projection plus output projection uses 8,192 + 9,216 = 17,408.
  Cubing adds elementwise work; the old model has its own quadratic products.
  Thus roughly halving feature storage does NOT halve arithmetic or latency.
- Event grouping, launch overhead, initial encoding, readout and batch size
  remain unmeasured. No throughput improvement is claimed.

Next priority: distinguish numerical attraction toward valid continuous states
from representation of the conditional feedback itself. Retain the stronger
normalized ridge as a baseline and evaluate richer feedback structures on a
separately declared dataset. Do not increase model width or change test splits
just to remove this specific failure.

## Reproduce

Use the NumPy environment from `../cell-real-state/requirements.txt`, fresh
output directories, and one BLAS thread:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-ridge-enhanced/study.py \
  --output out/cell-ridge-enhanced/first
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-ridge-enhanced/anchored.py \
  --output out/cell-ridge-enhanced/anchored
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-real-evaluation/evaluate.py \
  --adapter benchmarks/cell-ridge-enhanced/anchored.py \
  --weights out/cell-ridge-enhanced/anchored/model.npz \
  --output out/cell-ridge-enhanced/anchored/evaluation.json
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-ridge-enhanced/fresh.py \
  --baseline out/cell-real-algebra/reproduced/model.npz \
  --candidate out/cell-ridge-enhanced/anchored/model.npz \
  --output out/cell-ridge-enhanced/fresh.json
```

Run the independent evaluator with `study.py` and `first/model.npz` for the
first experiment. See `../cell-real-algebra` to regenerate the prior baseline.
Sources, hashes and text results are committed; binary models stay under ignored
`out/`. Evaluator completion is not correctness: inspect `finite_checks_pass`.
