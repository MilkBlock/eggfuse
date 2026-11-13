# Local port moments for the bounded Cell readout

The existing dynamic attachment projects current boundary channels through
slot-specific fixed weights and sums them before applying nonlinearity. This
experiment augments that first-order signal with second/third-order projections:

```
m2 = tanh(sum_i ((current_port_i ** 2) @ slot_weight_i))
m3 = tanh(sum_i ((current_port_i ** 3) @ slot_weight_i))
```

Each adds 64 columns. Input indices and weights come from the existing compiled
binding projection; the current predicted state supplies channel values. Gather
once, square/cube locally, and use two batched matrix/reduction operations. The
fixed two-operation expansion does not schedule individual nodes or perform
runtime graph traversal. Whole Cell instances remain batch rows. This reuses
existing Bake wiring rather than claiming a new compiler coverage capability.

Squaring before aggregation can distinguish cancellation that aggregation first
would hide; cubing retains sign. This is a feature construction argument, not a
proof that it distinguishes all required local graphs. The projection remains
compressed, input-role-conditioned, and finite. Scalar semantics and exact identity
are not recovered by moments.

The experiment keeps the narrow 512-column random projection and all existing
state features. Total state-readout width is 1,033 versus the baseline 905 and
wide experiment's 1,417. Data partitions, three training controls, projected
absolute output, ridge regularizer candidates and frozen emission head are the
same. No test samples enter fitting and no backpropagation is used. Additional
features have compute and storage costs; no speedup follows without measurement.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/fit_bounded_cell.py MANIFEST BASE.npz MOMENTS.npz FIT.json --readout clip --port-moments
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST MOMENTS.npz PROBE.json --rounds 16 --case-output CASES.json
```

Model metadata controls the optional feature path for both CPU and GPU. The
initial-feature conflict auditor uses the same moment path. Tests verify that
opposite current channel values produce a nonzero square signal but cancelling
cube signal, that changing the current values changes those signals, and that
NumPy and Metal agree.

## Result and failed relaxation control

| 16-round test / 850 inputs | Narrow baseline | Port moments | Moments, half-step |
|---|---:|---:|---:|
| Exact target and stopped | 790 | 808 | 180 |
| Final active requests | 4 | 4 | 3 |
| Aggregate body RMSE | 0.9827 | 0.5807 | 0.6172 |
| Backend coordinates outside tolerance | 0 | 7634 | 0 |
| Backend emission disagreements | 0 | 0 | 0 |
| Numerical audit | pass | fail | pass |

The full-step moments model gains 18 diagnostic successes over the narrow model
and loses none. It also exceeds the 794 of the wider random-feature model, with
fewer columns. However, its numerical audit fails and it is not accepted. Matching
emission decisions and final f64 decoder checks do not waive latent disagreement.
Validation selects alpha 0.1; the training/validation rows and split are unchanged.

A subsequent explicit inference-only ablation uses
`--relaxation 0.5`: after computing the candidate, update halfway from the current
state to it, retaining the same learned emission decision. This introduces no
forced stop or teacher value, but changes the intermediate state distribution.
It passes numerical agreement and catastrophically reduces completion success.
The round-two emission count is only 71 after 768 initial emissions, leaving many
partial updates stopped. This is consistent with a frozen stop head that is not
calibrated for half-completed states; the experiment does not prove this accounts
for every error. Neither the full-step nor half-step variant is adopted as a
reliable runtime. The `accepted: false` result applies to the overall experiment.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST MOMENTS.npz HALF.json --rounds 16 --relaxation 0.5
```

`port-moment-results.json` includes both probes, fit metrics and full-step paired
changes (diagnostic only because that probe fails). 48 related tests pass. These
are local fixed-binding tests, not full ruleset saturation or new-token generation
from arbitrary successor queries. No existing native path was changed.
