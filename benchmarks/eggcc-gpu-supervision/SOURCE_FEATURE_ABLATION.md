# Direct source consumption feature ablation

This is an observed-wiring numerical prototype, not autonomous Eggcc execution.
It preserves the intended runtime contract: semantic Cell tokens, repeated Runs
until a fixed point, then the original next stage. The experiment does not change
that controller or replace the resident model. There is no backpropagation.

The expanded training/validation manifests supply real captured RHS states and
observed provider edges. Correct completed source tokens are labels used only in
teacher-input training/diagnosis. Rollout consumes predicted source tokens, with
incomplete captures retained as explicit CPU boundary inputs. Historical wiring
has not proved visibility. No held-out test was used for feature selection.

The baseline uses template roles, input neighborhoods and routed source sums.
Two extra feature sets were tested with the same baseline random projection and
closed-form ridge selection over alpha = 0.1, 1, 10, 100:

- Message second moments: mean squared role-weighted source messages, 128 floats.
  These distinguish cancellation from absence without converting IDs to floats.
- Input/source interactions: s*s*p and s*p*p, 256 floats, where s is the current
  input encoding and p the first pooled source channel. These contain no consumer
  completion labels. Neither variant changes the 128-dimensional output token.

| Validation (26,637 valid instances) | Baseline | Moments | Input/source interactions |
|---|---:|---:|---:|
| Direct source token RMSE | .02162641 | .02171141 | .02158102 |
| Recurrent token RMSE | .02159373 | .02171456 | .02157864 |
| Multiple-source direct RMSE (18,380) | .02199454 | .02210396 | .02199201 |
| Direct maximum error | .607951 | .606638 | .624022 |
| Readout coefficient bytes | 852,480 | 918,016 | 983,552 |

Reject the moment feature. Interactions reduce direct RMSE by only about 0.21%
while increasing coefficient storage by 128 KiB and worsening the maximum error.
This is insufficient evidence to replace the runtime model or claim improved
exact Eq accuracy. Recurrent RMSE is comparable to direct RMSE in this partition;
long-chain stabilization alone is not a demonstrated remedy here.

CPU constructs the experimental features; Metal performs the batched readout.
Maximum CPU/GPU direct difference is below 2e-6. The standalone moment kernel
also passes compiled Metal parity, padding and permutation checks. This is not
an end-to-end GPU timing result. Three focused tests pass, including independence
from consumer completion labels. Results are in source-moment-validation.json.

Reproduce from this directory with the experiment venv Python:

```
python -m unittest test_source_moment_probe
python source_moment_probe.py TRAIN_MANIFEST VALIDATION_MANIFEST source-moment-validation.json
```

The next informative experiment should preserve source export-port roles and
which consumer input each source discharges before pooling. More aggregate
moments do not replace this structural distinction. Bake should compile those
roles from actual Entry projections; do not infer them from future output labels.
The reviewed Bake commit 6b86e7db colocates source routing with completed sources
and retains old IDs/fallback routing. Any eventual runtime feature storage should
reuse that ownership/lifecycle information, not add a second source directory.
