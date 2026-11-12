# Robust ridge readout and frozen finite-model verification

This is standalone NumPy research on the finite teacher from `../cell-real-state`.
It does not establish real EggFuse execution, GPU throughput, general egraph
correctness or native semantic acceptance. The strongest result exceeds90% when
fresh trajectory counts are pooled, but does NOT meet90% at every tested length.

## Frozen verification result

`select_and_verify.py` fixes three candidates (gated,shaped,high-order), evaluates
new validation sequences and selects by mean trajectory accuracy, then minimum
accuracy as a tie-break. It writes selection.json BEFORE evaluating the three
fresh test sequences. The winner is `high_order.py`, trained readout poly3,
regularization10,noise.05, on frozen staged dynamics with denoising and a smooth
gate. Its original readout training selection and the later cross-candidate
selection are both retained.

| Fresh test length | All steps exactly correct | Rate |
|---|---:|---:|
| 12,seed314159 | 568/624 | 91.03% |
| 48,seed271828 | 559/624 | 89.58% |
| 96,seed161803 | 560/624 | 89.74% |
| Pooled | 1687/1872 | 90.12% |

Every successful trajectory must match all155 observations after EVERY event.
The pooled90.12% must not be presented as90% for48 or96 steps: both fall short,
and `all_fresh_sequences_at_least_90` is false. The existing independent evaluator
also reports single-event2542/2652=95.85%,initial reconstruction155/156,and the
rare rule-enabled boundary-feedback transition1/1. The latter is one finite
case, not proof of general repair. Existing evaluator sequences give558/624,
563/624 and560/624 at12/12/48 steps. They are distinct from the fresh selection
verification sequences above; do not interchange the counts.

The initial state reconstruction is a separate diagnostic. Trajectory accuracy
checks predictions following events; it does not silently include or replace
initial reconstruction. No model passes exact finite-domain semantic acceptance.

## What executes and what changed

The recurrent state is17 dense signed fractional coordinates, an encoding of
15 boundary relations and two flags in this fixed teacher. Dense real matrices,
polynomial features, Gaussian features and smooth residual gates evolve it.
The readout consumes that real state and predicts the155 observations. Its
thresholded observations are used only for scoring, never fed back as repaired
state. There is no nearest-state selection or symbolic execution fallback.

Readout training uses clean training states, admitted training-edge predicted
states, two-step predicted states whose intermediate/target remain training,
and Gaussian perturbations. A ridge solve fits the observation readout. The
transition itself is frozen during these readout experiments. `study.py` uses
the earlier compact denoiser; `staged.py`,`gated.py`,`shaped.py` use progressively
composed staged bases; `high_order.py` extends readout degree/penalty candidates.
Failed and intermediate results remain in results.json.

Crucially, the strongest base has EXTRA SUPERVISION: `cell-ridge-shared/staged.py`
learns an unclosed-apply intermediate and then its completed state, rather than
only the original closed-state transition label. That intermediate is computed
from an admitted training source, and final labels stay in training. This is
additional compiler-like information, not a like-for-like final-label-only
ridge comparison. The finite teacher still lacks fresh nodes,deletion,mutable
reads,Run ordering and real multi-entry Cell execution.

Denoising adds repeated dense feature/readout evaluations; gating and derived
observation readout add more work. Correctness improvements do not prove GPU or
end-to-end speed improvements. Dense real arithmetic alone is not a throughput
measurement.

## Adaptivity and data disclosure

This is adaptive research after earlier test inspection. New models and feature
families were motivated by prior outcomes. Each documented checkpoint selection
uses validation; the final three validation/test event-sequence seeds were new
at final selection time. They traverse the SAME156 held structural states as
earlier tests. Fresh action sequences are not new graphs or an independent
external structural holdout. Long trajectories share states and converge, so
pooled samples should not be treated as independent trials for a confidence
claim. The90.12% pooled rate does not resolve this limitation.

## Frozen artifacts and reproduction

`results.json` bundles all output-relative result JSONs, the final selection,
independent evaluation and original source hashes. `current_source_sha256` is
an additional documentation-time snapshot, not a claim that historical runs
executed later modified code.

The winner's NPZ dependency chain is:

```
out/cell-ridge-readout/high-order/model.npz
  -> out/cell-ridge-attractor/staged-shape-gate/model.npz
  -> out/cell-ridge-attractor/staged/model.npz
  -> out/cell-ridge-shared/staged/model.npz
```

Models contain local `base_path`/`prior_path` references, so the top NPZ is NOT a
self-contained deployable model. Final verification records SHA256 for all four
files under `weights_dependencies`; these hashes were checked against current
files when documenting. Do not overwrite an upstream NPZ and assume the frozen
result remains valid. Binary model files stay ignored and are not committed.

Use the existing NumPy environment and generate the compact baseline,staged
base,staged Gaussian denoiser and shape-gate models in dependency order; see
sibling experiment READMEs. Reproduce readout experiments with fresh outputs:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-readout/high_order.py --output out/cell-ridge-readout/high-order
```

Run `gated.py --output out/cell-ridge-readout/gated` and
`shaped.py --output out/cell-ridge-readout/shaped` as well before final selection.
The verification script uses fixed artifact paths and requires its output
directory not to exist:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-readout/select_and_verify.py
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-real-evaluation/evaluate.py --adapter benchmarks/cell-ridge-readout/high_order.py --weights out/cell-ridge-readout/high-order/model.npz --output out/cell-ridge-readout/verification/evaluation.json
```

Keep original artifacts when rerunning in another checkout; do not overwrite
frozen dependencies. Evaluator completion is not correctness: inspect
`finite_checks_pass`. The native choice_diagnosis.py acceptance contract is
unchanged and has not been replaced with a90% approximate threshold.
