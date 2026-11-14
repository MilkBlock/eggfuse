# Sender/receiver role transport: rejected experiment

The current shared boundary encoder adds typed-root context to each port, sums
the enriched ports within a Cell, and broadcasts that sum. This experiment
tests explicit role modulation at that transport step, without changing the
output width or fitting an encoder with gradients.

Bake computes `gate = tanh(roles @ role_weight)` from existing fixed template
roles. The experiment computes `cell = sum(enriched * gate) / sqrt(count)` and
then `tanh(enriched + cell * gate)`. All gates are fixed template arrays. GPU
execution uses the existing connectivity, floating arithmetic and nonlinear
operators; the optional implementation branch is chosen at graph construction.

Use `fit_completion_classifier.py --shared-context --normalized-joint
--role-transport` with the recorded argv. Training still uses the same 641
synthetic entries, 256 nonlinear columns and ridge alpha 10. Captured original
features are verified using their own encoder settings before constructing the
experimental features. No future labels enter feature construction.

| Fixed development inputs | Existing context | Role transport |
|---|---:|---:|
| GCD total | 36/41 | 28/41 |
| GCD direct source | 23/26 | 15/26 |
| LCM total | 93/99 | 47/99 |
| LCM direct source | 72/78 | 27/78 |

Reject this replacement. Matching dimensions and numerical parity do not imply
equivalent or better information preservation. The original representation
already incorporates port roles before aggregation; this result does not prove
that it lacks role information or that topology alone explains its errors.

This is an offline selected-family Python/MLX experiment, not full Eggcc or an
actual feedback rollout. The runtime runner rejects this experimental head
rather than silently using the original encoder. Existing default behavior and
the active model remain unchanged. There is no speedup claim.

The result JSON records the archive, weight checksum and numeric errors. Tests
cover CPU/GPU parity, dense/scatter agreement, typed ID renaming and retired
sources. The archive contains the complete argv, trained head, report and log.
