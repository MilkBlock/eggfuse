# Historical-context regression is mostly present before recursive rollout

`audit_context_rollout.py` freezes both the whole-Cell model and the previously
validation-selected MSE boundary decoder (alpha 100). It does not fit, select
thresholds or choose configurations using test results. Four input conditions
separate oracle output decoding, one-step fitting with oracle providers,
recursive GPU rollout and the previously fitted no-provider control.

All rows below use the same 5,454 comparable dot-product instances. Columns are
exact local Eq partitions, false Eq pairs and missed Eq pairs, respectively.

| Context | Token condition | Exact | False | Missed |
|---|---|---:|---:|---:|
| Full input interface | Oracle output state | 4,248 | 300 | 2,041 |
| Full input interface | Oracle providers | 4,281 | 325 | 2,042 |
| Full input interface | Predicted providers | 4,288 | 379 | 2,038 |
| Full input interface | No-provider refit | 4,240 | 373 | 2,047 |
| Historical | Oracle output state | 4,248 | 300 | 2,041 |
| Historical | Oracle providers | 4,256 | 684 | 1,912 |
| Historical | Predicted providers | 4,248 | 693 | 1,919 |
| Historical | No-provider refit | 4,240 | 373 | 2,047 |

The historical regression is already present with oracle providers. Recursive
rollout adds only nine false pairs and seven misses in this comparison. This
rules out attributing most of this particular false-merge increase to recursive
error accumulation. It does not establish the cause for all workloads.

Historical model token RMSE is 0.03475 with oracle providers and 0.03549 with
predicted providers, lower than interface-only RMSE 0.04048 / 0.04292. Output
encoding is identical, so this comparison is meaningful numerically. Yet the
Eq readout worsens. Optimizing average token coordinates does not necessarily
preserve decision-relevant relations. The audit does not separate limitations
of the token fitting objective from decoder sensitivity to off-target states.
Oracle output itself still has 300 false pairs and 2,041 misses, so improving
rollout alone cannot establish a correct boundary decoder.

All inference/readout modes run floating matrix operations on GPU, with numerical
readout checks against CPU. Oracle modes are diagnostics, not available runtime
inputs. No union is applied or authorized. Scalar results, ownership, lifecycle,
autonomous matching and saturation are not certified. This is a standalone
prototype experiment, not native egglog semantic acceptance or a speed benchmark.
The no-provider coefficients were fitted in the earlier model experiment; this
script performs no additional training. Existing helper tests cover expansion,
query accounting, ridge selection and numeric checks; both real audits passed.

Reproduction (repeat with `interface` and `history`):

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_context_rollout.py \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-history.npz" "$ROOT/class-history.json" \
  "$ROOT/history-selection.npz" "$ROOT/history-selection.json" \
  "$ROOT/history-rollout-audit.json"
```

Committed `interface-rollout-audit-results.json` and
`history-rollout-audit-results.json` retain model, decoder and trace fingerprints.
The next representation experiment should distinguish relation-bearing context
from unrelated historical content and evaluate both oracle and predicted inputs;
reducing scheduling depth first would not repair the observed one-step error.
