# Joint nonlinear input and boundary features

The prior head appended boundary columns only after the original random nonlinear
projection. Its new columns therefore contributed additively to ridge scores.
`--joint-features` appends `tanh(X W)` over the complete existing input plus
boundary columns. W is fixed f32 Gaussian, seed 20261114, variance 1/input-width,
with 256 outputs. Only the final ridge coefficients are fitted; no gradients.
The GPU runner compiles the same matrix from explicit head metadata and consumes
these columns before producing the next token. Capture replay recomputes the
projection independently. Projection, compiled inference and replay tests pass.

Two fixed experiments used all 487 synthetic training inputs and alpha 10:

| Variant | GCD exact-source | LCM exact-source |
|---|---:|---:|
| Previous shared context | 17/41 | 28/99 |
| Equal total weight per observed training state | 12/41 | 22/99 |
| Joint nonlinear features, ordinary weights | 26/41 | 36/99 |

State balancing uses only training labels, retains mean row weight one, and
solves weighted ridge with unpenalized weighted intercept. A primal/dual check
covers the implementation. It regressed and was not selected. No validation
samples enter either fit. These are recurring development cases, not holdouts.

Actual GCD predicted-source GPU feedback improves from the prior shared-context
14/41 to **23/41**: direct 12/26, generated-source 11/15. It produces 41 Cells and
consumes generated sources 15 times. CPU graph and independent label audits pass;
exact kernels still authorize semantic effects. The reported improvement is
prediction accuracy, not proof that learned execution can replace those checks.
The historical original head's offline LCM result (80/99) remains substantially
better than these new heads; no global model promotion is claimed. LCM has not
yet been rerun in feedback mode with the joint head.

One extra fixed dense matmul and tanh is added to GPU inference. No runtime
speedup is claimed and encoding costs still need measurement. No ownership-slack
experiment was used in this GCD run (default zero).

Artifacts under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/enumerated-gpu-v1`:
`balanced-fit-argv.json`, `joint-fit-argv.json`, corresponding weights/reports,
`gcd-joint-argv.json`, execution/capture/label files. Tracked
`joint-feature-ridge-results.json` preserves both successful and failed trials
and their report/weight hashes. Binary captures and weights remain untracked.
