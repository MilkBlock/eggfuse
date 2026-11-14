# Joint boundary nonlinearity versus direct whole-state ridge

Two controlled experiments reuse the same 129 training instances from five original
training programs and the same GCD/LCM exact-source validation captures. No new graph
execution, gradient descent, alpha sweep, threshold tuning or test-set fitting is
performed. Neither candidate is installed in the resident runtime by this change.

## Rejected: a fixed joint nonlinear input map

`device_joint_boundary_features.py` jointly projects the 1408 original raw columns
and 512 boundary columns into 256 tanh features. Seed 20261119 and uniform biases
are fixed independently of labels. Existing 256 random features are not fed back
as raw inputs. The projection scale is `1/sqrt(1920)`. All old columns remain;
only output ridge weights are fitted, with alpha 10 and the frozen decoder.

This changes 2177 columns to 2433 and adds 1,967,104 static projection bytes plus
131,072 predictor bytes. The GPU evaluates the actual dense floating map and
predictor; maximum prediction discrepancy is 3.07e-6.

It fails validation: GCD falls from 35/41 to 34/41 (4 new expanded false merges),
and LCM falls from 82/99 to 80/99 (closure false merges 13 to 15). LCM direct-source
accuracy falls from 71/78 to 69/78. The candidate is rejected and does not justify
a full GPU rollout. This experiment disproves the sufficiency of this particular
joint random map, not every possible nonlinear representation.

## Implemented candidate: fit the completed state directly

The previous path optimizes token-coordinate error and then uses a second fitted
model to recover Eq state. The new experiment removes that intermediate training
objective:

```
existing 2177 floating input columns
  -> standardized ridge matrix -> state scores
  -> retain states compatible with actual current input Eq
  -> choose whole state
  -> baked Eq moments + actual dynamic scalars -> full 128-dimensional token
```

Each semantic template has a ridge head. Bake enumerates all type-compatible
partitions independently of observed labels, retaining completed static effects.
The three templates have 2, 15, and 15 states. Training observes only 2, 3, and 2
of those states, respectively, from 34, 77, and 18 instances. Unseen states remain
in the representation but have no positive training evidence. This is not an
exhaustive learned completion model.

Targets are one-hot state identities; these are supervised outputs, not Boolean
execution matrices. Runtime feature-to-state scores use real dense learned float
weights. The state mask preserves proven input Eq, and scalar contributions use
actual current query values. Future CPU equality is used only as the training or
validation target, never in feature construction or candidate selection. Scalar
results not available from query inputs are rejected by this experiment.

Ridge uses the same alpha 10 and training-only per-column mean/std policy as the
existing closed-form fitter, including its .02 scale floor. Mean and scale remain
explicit at inference. Folding them into coefficients produced cancellation error
up to 1.58e-5 in f32, so that form failed the existing 5e-6 numeric gate. Keeping
standardization explicit reduces score discrepancy to 2.03e-6 without relaxing
the gate or changing the regression objective. Unit tests compare against an
independent primal ridge solve.

Actual GPU batches perform standardization, state-score matmul, input-Eq mask,
argmax and complete token synthesis. GPU state choices exactly match CPU. Token
reconstruction error is at most 1.20e-7, and the frozen decoder recovers every
selected state without disagreement in these saved cases. This checks encoding
consistency, not whether the chosen state is semantically correct.

## Validation: higher complete-state accuracy, remaining false merges

| Metric | Original token ridge | Direct state ridge |
| --- | ---: | ---: |
| GCD complete states | 35/41 | 39/41 |
| GCD direct-source complete | 23/26 | 24/26 |
| GCD generated-source complete | 12/15 | 15/15 |
| GCD expanded false merges | 0 | 3 |
| GCD expanded missed equalities | 16 | 3 |
| LCM complete states | 82/99 | 96/99 |
| LCM direct-source complete | 71/78 | 76/78 |
| LCM generated-source complete | 11/21 | 20/21 |
| LCM expanded closure false merges | 13 | 9 |
| LCM expanded missed equalities | 35 | 0 |

The existing resident whole-state projection is a stronger safety comparator than
the original token ridge: on LCM it has 83/99 complete states and **7** expanded
false merges, so the new head's **9** is a regression on that metric. New direct
false merges are 3 on GCD and 6 on LCM, where the original model had none. These
results do not authorize direct union or default promotion, despite exceeding 90%
complete-state accuracy on these two development validation programs.

The complete output head bank is 278,656 bytes plus 52,376 bytes of means, scales
and biases. Existing input encoding, original random feature map, exact matching,
static token tables, ownership/lifecycle checks and boundary gather remain costs.
This replaces a 2177-by-128 output projection and its Eq decoder in the proposed
path; it does not yet remove them from the resident implementation. No end-to-end
speedup is measured or claimed. Full token feedback with this head remains the
next acceptance step, followed by broader independent validation and explicit
handling of incorrect completion proposals.

## Latest iterative Bake inspected

`codex/cell-parallel-admission` is now at `ae6250f0`. Its optional native binding
storage actually removes proven redundant bound values via shared `Stored`/`Native`
layouts. Admission checks current equivalence; unbound or different reused results
remain explicit, and append/retirement materializes values before source positions
change. Layout storage and selection costs are counted; total Program plus Graph
storage increases in its reported configuration despite smaller Graph storage.

The GPU head likewise derives template state separately from current instance
values. It cannot use a state index as a returned constructor address or an
ownership proof. The experiment continues to consume existing owner-projected
slots and actual scalar identities. It does not port or claim that CPU feature's
memory savings; no CPU executor changes are included here.

## Reproduce

Use the project MLX Python with `fit_joint_boundary.py` (same arguments as
`fit_scalar_context.py`) and `fit_completion_classifier.py MODEL SOURCE_MODEL
DECODER DECODER_REPORT OUTPUT`, passing the five saved training archives and two
validation archives via repeated `--train` / `--validation` flags.

All artifacts are under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`:
`joint-nonlinear-boundary.json/.npz` and `direct-completion-classifier.json/.npz`.
Model/capture paths are the same as `SCALAR_CONTEXT_AND_DIRECT_SUPPORT.md`.
For the classifier, MODEL is `five-program-boundary-model.npz`, SOURCE_MODEL is
`class-history-neighborhood-input.npz`; the decoder is the frozen five-program
one. Reports retain archive/model/weight hashes and partition checks.

Eight relevant tests pass, covering mixed nonlinear interaction, layout rejection,
GPU parity, independent ridge equivalence, current-Eq constraints including an
unobserved forced state, exhaustive small partition enumeration, and actual scalar
token synthesis. Binary weights remain on the external disk; sources and text
reports are committed.
