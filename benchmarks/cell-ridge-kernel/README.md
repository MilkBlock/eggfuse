# Dense polynomial ridge: full state and compact boundary state

These are standalone finite-teacher NumPy experiments. They do not execute the
EggFuse runtime, commit graph mutations, establish native semantic acceptance,
or measure GPU speed. The unchanged teacher in `../cell-real-state/study.py`
contains six boundary ports, twelve fixed constructors, two positive rule-enable
flags,806 closed states and155 observations. There is no fresh-term growth,
deletion, arbitrary mutable read, source Run visibility or multi-entry scheduling.

## Representations

`study.py` retains32 or35 train-only PCA coordinates from the full observation
vector. It uses all496 training-state vectors as dense polynomial feature
centers, solves an action-specific normalized ridge residual and clips its real
output to train-derived coordinate bounds. A fixed degree/regularization screen
is followed by eight augmentation iterations using predicted intermediate
states, repetition and composition. Training sources AND closed destinations
are in training; composition intermediates remain in training. Validation
chooses the checkpoint. The selected35-dimensional degree4 model has held
single-event correctness79.41% and12-step all-step correctness44.87%.

`compact.py` encodes only the15 boundary equalities and two flags into17 dense
signed real PCA coordinates. This representation is chosen using the finite
teacher's structure: derived constructor observations are functions of the
boundary and flags in this model. It is not a demonstrated general-purpose
compression of arbitrary egraphs. Runtime steps consume the dense continuous
state directly; derived observations are produced by a separately learned
nonlinear ridge readout only for scoring. No observation threshold, decoded
fact vector, symbolic repair or nearest-state lookup feeds the recurrence.

Compact transitions use the same dense polynomial ridge family with train-only
centers. The validation-selected checkpoint is degree5,regularization10,zero
augmentation rounds. The selected nonlinear readout is independently validated.
Test single-event correctness is93.14%,12-step all-step correctness75.80%, and
initial reconstruction98.72% (154/156 states). Initial reconstruction is reported
separately; trajectory scores require each predicted step, not the unmodified
initial state, to be correct. FP32 inference is a numerical experiment, not
hardware FP16 validation or an efficiency result.

## Evaluation and limits

Structural splits stay frozen at496 train,154 validation,156 test states. The
teacher has been repeatedly inspected during this adaptive research. Models are
selected with validation, but these results are not an untouched external test
benchmark. Multiple sequences share initial structural states and eventually
converge, so trajectory samples are not independent novel graphs. Scores require
all155 observations at each step; per-bit accuracy is not substituted.

`results.json` bundles the original result/evaluation JSON files under their
output-relative paths, including all validation checkpoints and original source
hashes. `current_source_sha256` identifies the files at documentation time and
is separate from the hashes recorded when experiments ran. Binary NPZ files
remain in ignored `out/` directories.

The later strongest readout experiment in `../cell-ridge-readout` uses an
additional two-stage model trained with unclosed-apply intermediate supervision
from `../cell-ridge-shared/staged.py`. Its results must not be attributed to
compact.py alone or compared as if the supervision were unchanged. That model
also adds denoising and continuous gates, with unmeasured inference cost.

## Reproduction

Use the NumPy environment from `../cell-real-state/requirements.txt` and fresh
output directories. The downstream scripts reference the shown baseline paths;
freeze those artifacts once generated.

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-kernel/study.py --output out/cell-ridge-kernel/first
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-kernel/compact.py --output out/cell-ridge-kernel/compact
```

Both expose `load_adapter(path)` with encode,step,decode. Independent evaluation
uses `../cell-real-evaluation/evaluate.py`; completion of the evaluator is not a
semantic pass. Consult `finite_checks_pass`, which remains false for these
approximate models. Native `choice_diagnosis.py` requirements are unchanged.
