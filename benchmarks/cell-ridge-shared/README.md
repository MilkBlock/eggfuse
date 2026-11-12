# Shared dense action/state ridge

Standalone finite-teacher negative result, not runtime execution or GPU timing.
Uses unchanged source and target structural split from cell-real-state.

35 train-PCA coordinates are concatenated with 35 dense action coordinates.
The latter are mean latent deltas of each action over admitted training edges,
scaled by training action-code variance. A shared cubic projection onto 512 or
1024 training edge centers supplies features for one ridge matrix, rather than
17 independent action banks. Inference is continuous real projection, cubing,
residual addition and clipping. There is no discrete lookup, symbolic repair,
or decoded-fact feedback. Training adds predicted inputs for repeated and
composed actions; every target remains training. Codes and centers are fixed
before validation. All 12 validation checkpoints are recorded; held test scores
are computed only for the validation-selected checkpoint.

This does not improve the independent-action baseline: the selected model's
held single-event exact rate is 60.33%, and original 12-step whole-trace rate
is 20/624 (3.21%). Sharing via average action effects is insufficient here;
it does not encode which particular binding causes feedback. No 90% claim.

Reproduce:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-shared/study.py --output out/cell-ridge-shared/new
```

`load_adapter(path)` exposes encode, step and decode. Binary models stay in
ignored out; source and text result are retained. Features/weights/state use
FP16 rounding at existing teacher helper boundaries with FP32 accumulation.

## Compact-state per-action specialization

`specialized.py` reuses the frozen compact encoder/readout from
`out/cell-ridge-kernel/compact/model.npz`. Each action independently screens
degree 2/3/4/5 and regularization .001/.1/10 on the unchanged strict training
edges. Two selection metrics (complete-observation accuracy or boundary
accuracy, then latent MSE) create two combined models. Each combination tests
six rounds of the original predicted-input algebraic augmentation. The best
combined validation trajectory model is frozen before one test evaluation.

The selected full-observation/iteration-zero combination gives validation
single 91.63%, trajectory 74.35%; held test single 93.89%, trajectory 72.92%.
It does not improve the parent compact model's trajectory result. This is
consistent with per-action single-step selection not optimizing composed
stability. All 204 action/config screens and 14 combination checkpoints are
in specialized-results.json. Its runtime uses action-selected dense polynomial
projections and weights; boundary decoding is only an offline selection metric.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-shared/specialized.py --output out/cell-ridge-shared/specialized-new
```

The adapter exports encode/step/decode. No runtime or semantic acceptance code
was changed and there is no 90% whole-trajectory claim.

## Offline margin-target refinement

`margin.py` starts from the frozen compact model and, only during training,
inverts the dense 17-dimensional code into continuous boundary scores. Scores
below .75 for true labels or above .25 for false labels create a signed margin
correction. New regression targets are the true training labels plus this
correction times a fixed gain (.25, .5 or 1). These targets are re-encoded to
17 dense real coordinates before a new ridge fit. No inverse decoding or
thresholding is added to runtime. Every regression source and target originates
from the admitted training edges; correction values may extend outside [0,1].

Thirteen checkpoints per gain were evaluated on validation. Validation selected
the original model, iteration zero: test single 93.137%, trajectory 75.801%.
No refinement beat it. Results are in margin-results.json. This negative result
means the attempted confidence-margin target correction does not improve
composition; it does not prove all margin-aware objectives ineffective.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-shared/margin.py --output out/cell-ridge-shared/margin-new
```

The saved model uses `specialized.load_adapter` (all actions share degree 5).

## Two learned stages with compiler apply intermediates

`staged.py` changes the supervision contract explicitly. For each of the 6,224
admitted (training source, training closed target) edges, offline code applies
only the requested boundary union or flag-enable to the source partition. It
records the 17 unclosed boundary/flag observations. No held source or held closed
target provides these training labels. There are 501 distinct intermediate
codes; they need not themselves be valid closed states.

Stage one independently learns each action's unclosed dense 17-dimensional
state. Stage two shares a polynomial ridge map from that intermediate to the
closed dense state. Its fit optionally includes stage-one predictions, with the
same training closed targets. At runtime both stages are continuous matrix
projections and polynomial operations; there is no union-find, bit predicate,
nearest-state operation or symbolic closure. Decode remains scoring-only.

The fixed screen compared stage-one degree 2/3, regularization .001/.1;
stage-two degree 3/5, regularization .001/.1/10; and true-only versus
true-plus-predicted intermediate training (48 configurations). Validation selects
degree 3/.1 then degree 5/10 with both intermediate types. Held test single-event
accuracy is 95.25%, and 12-step whole-trace accuracy is 79.49%. This improves on
compact's original trajectory result, but is below 90%. It is not a same-training-
information comparison: the extra offline unclosed-action labels are crucial to
state in any report. Source and complete screen results are staged.py and
staged-results.json, with generated weights under out/cell-ridge-shared/staged.

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-shared/staged.py --output out/cell-ridge-shared/staged-new
```
