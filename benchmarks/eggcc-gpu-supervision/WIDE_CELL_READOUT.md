# Bounded state readout capacity experiment

The common-failure audit found 41 shared failures on exact training inputs. This
experiment adds 512 fixed random tanh features to the projected absolute state
readout while retaining its existing features, input/target construction, data
partition and loss. There is no backpropagation. Regularization is selected from
the same candidates on validation, not test.

The original 384 x 512 random matrix remains a prefix. Additional columns use
seed 120 and the same normal scale 1/16. The state readout has 1,417 input columns
instead of 905. The separate emission head retains its original random matrix and
coefficients. Checkpoints store `direct_w` separately; old checkpoints fall back
to their existing `w`. This avoids silently changing the stop-head features.

Training additionally reports decoded reconstruction RMSE separately for original,
base-predicted and completed controls, on train and validation. Body error is in
normalized coordinates here; the recurrence report uses physical body scale, so
the values must not be directly compared. Boundary error averages the existing
globally padded channels, which dilutes active-slot error. These are reconstruction
metrics, not semantic acceptance or a substitute for final candidate/stop checks.

The extra dense features increase storage and compute. The direct coefficient
matrix grows from 905 x 34,080 to 1,417 x 34,080. No throughput claim is made. This
is still a fixed-binding local GPU prototype, not successor closure, ownership
transfer, or a native runtime implementation.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/fit_bounded_cell.py MANIFEST BASE.npz WIDE.npz WIDE_FIT.json --readout clip --extra-features 512
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST WIDE.npz WIDE_PROBE.json --rounds 16 --case-output WIDE_CASES.json
```

## Result: modest capacity benefit, no uniform improvement

| 16-round metric / 850 inputs | 905 features | 1,417 features |
|---|---:|---:|
| Exact catalog target and stopped | 790 | 794 |
| Final active requests | 4 | 6 |
| Aggregate body RMSE | 0.9827 | 0.8658 |
| Median per-input body RMSE | 0.05392 | 0.04820 |
| Numerical audit | pass | pass |
| f64 decoder disagreements | 0 | 0 |

Paired inputs show 10 gained successes and six lost successes. Six of the 41
previously common exact-training-input failures are now successful. This supports
some capacity limitation but does not isolate it as the sole cause. The increased
feature width is about 57%, while net success improves by four inputs. This does
not justify claiming a faster or fully reliable runtime, nor unlimited feature
expansion as the main direction.

Validation selects alpha 1.0 instead of 0.1 for the narrow model; scaled validation
loss changes from 3.2548e-8 to 2.7304e-8 under the same target/loss definition.
The new reconstruction diagnostics show nonzero training error on all three
input kinds. They do not prove that merely lowering regularization will improve
held-out or recurrent results. The same 11 required first emissions remain missed.

`wide-readout-results.json` records fit/reconstruction reports, the complete GPU
probe and changed input identities. 47 related tests pass, including preservation
of original feature columns when the random projection is extended. The frozen
stop head is deliberately independent of `direct_w`; feature-conflict auditing
also reads the correct state projection from newer checkpoints.
