# Closed-form correction of predicted Cell states

This standalone experiment tests the distribution gap diagnosed in
`BAKE_STOP_FEATURES.md`. The base positional-role state readout and Bake-informed
emission head are frozen. A second closed-form ridge readout repairs the raw
candidate state before it becomes the next recurrent input. No gradients are
computed through either readout.

For each train/validation input, compute the base raw proposal `u = s + f(s)`.
Fit `g(u)` to `target - u`, using the same request and recomputing attachments and
Bake hints from `u`. Also fit `g(target) = 0` as an identity control. Use only train
rows to solve; validation selects regularization. Test records are excluded from
feature/target construction for this fit. Base-model training inputs produce the
training proposals, so this is not out-of-fold augmentation.

GPU recurrence becomes:

```
score = unchanged_stop_head(current)
proposal = current + unchanged_state_readout(current)
corrected = proposal + correction_readout(proposal)
next = where(score >= 0.5, corrected, current)
```

Both heads and the correction are fixed matrix/nonlinear dataflows. The optional
model branch is selected when compiling, not a per-token GPU control path.
Correction adds another feature evaluation and dense state readout per round;
there is no performance claim. Even inactive lanes may execute the candidate and
correction arithmetic before the final mask. A missed first emission cannot be
rescued by this design because its correction is discarded.

The correction labels are numerical residuals, not new logical matches or stop
labels. Inference still has no oracle refill, CPU intermediate read, hard stop
or nearest-catalog projection between rounds. The candidate dictionary is used
only at final measurement and still contains held-out states. This is fixed
binding recurrence, not successor discovery or native egglog execution.

Reproduce using the previous saved Bake-stop model:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/fit_cell_correction.py MANIFEST BASE.npz CORRECTED.npz FIT.json
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST CORRECTED.npz PROBE.json
```

The existing probe independently checks NumPy recurrence at its unchanged
numerical tolerances and final candidate selection using f64 distances. A failed
check remains a failure, regardless of apparently improved candidate accuracy.

## Result: partial recovery, worse tail instability

3,760 training rows and 1,472 validation rows select alpha 10.0. No test rows
enter fitting. All base arrays, including the emission head, are byte-value equal
under `numpy.array_equal`; only the 905 x 34,080 correction matrix is added.

| Four-round test metric, 850 inputs | Base Bake-stop model | With correction |
|---|---:|---:|
| Emissions per round | 768 / 7 / 7 / 7 | 768 / 5 / 5 / 5 |
| Exact catalog target and stopped | 815 | 823 |
| Median per-input body RMSE | 0.06466 | 0.04237 |
| Maximum per-input body RMSE | 2505.86 | 5493.51 |
| Aggregate body RMSE | 86.20 | 188.71 |
| Initially novel but never emitted | 11 | 11 |
| Fixed-tolerance recurrence audit | pass | pass |
| f64 decoder disagreements | 0 | 0 |

Three previously active requests stop, but one previously stopped request becomes
active. Five remain active in total. Better median recovery and candidate scores
do not compensate for worse tail drift. This variant is not accepted as a stable
runtime improvement. Numerical audit agreement means NumPy and GPU implement the
same recurrence within tolerances; it does not mean that recurrence is correct.

Training here covers one raw proposal per train input plus true-target identity
controls. It does not train the distribution reached by repeatedly composing the
base predictor and correction. The result motivates investigating that recurrent
composition and the scale of large initialization Cells, rather than silently
clamping or stopping all bad predictions. It does not prove that adding more
single-step correction samples will resolve instability.

`cell-correction-results.json` includes exact model hashes, active-request changes
and the full probe. Binary model files remain on the external SSD. The 36 related
unit tests pass; the full GPU probe provides the numerical integration check.

## Eight-round falsification

Extending the same fixed-binding GPU recurrence to eight rounds fails for both
models (`long-recurrence-results.json`). The base model remains finite but has
904 coordinates outside the unchanged NumPy agreement tolerance; aggregate body
RMSE reaches 827,087. The correction model reaches nonfinite state at round eight,
with 34,080 nonfinite coordinates in the union of the two backend outputs. Neither
result is accepted; both probes exit 1.

The corrected model's maximum absolute boundary coordinate progresses through
1.20, 14.77, 223.84, 6707.20, 2.28e7, 1.65e14 and 8.82e27 before becoming nonfinite.
Teacher boundary channels are tanh outputs and therefore bounded by [-1,1]. The
base also leaves this range on the first round. Scale summaries are reduced on
the GPU and returned only at the end; they do not correct intermediate values.

One plausible amplification path is now visible in the implementation: state
residuals are unconstrained, raw body features bypass the random tanh branch,
and output/difference energies enter the extra linear columns quadratically.
The correction readout can therefore amplify a state already outside the training
range. This is a mechanism hypothesis, not an isolated causal attribution. A
bounded-feature/readout ablation is warranted before more unconstrained fitting.
Simply clamping the old predictions would change their meaning and would require
its own accuracy and recurrence verification.

The probe now persists a strict JSON failure report for nonfinite states and does
not report catalog success for them. Tests ensure identical NaN/Inf outputs still
fail backend agreement; matching bad floating-point values are not a pass. The
38 related tests pass. Finite comparison differences are evaluated in f64 to avoid
an overflow in the audit itself; acceptance tolerances are unchanged.
