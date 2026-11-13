# Live-source ridge transition adapter

The device admission path previously used a square floating test transform,
while trained ridge ran only in observed-route replay. `device_ridge_transition`
now evaluates the trained feature map from current source tokens and can pass
its output directly into `closed_entry_proposals`. This bypasses rather than
adds to the square transform. No backpropagation is used.

The request carries dynamic seed and query features, source indices/generations,
edge roles, channel routing, padding masks and input readiness. It pools current
source tokens, includes seed/context products, applies the fixed random nonlinear
projection, and evaluates trained ridge weights. All operations run in one
compiled GPU call in the admission test. Visible settled shared sources remain
readable after their activation ownership has moved; dirty, missing, hidden,
nonfinite or recycled sources block inference readiness. Padded invalid values
do not poison valid rows.

This adapter is not the compiler or runtime matcher. Its caller must produce
legal requests, including the correct dynamic seed and source bindings. Numerical
readiness does not grant query coverage, ownership transfer or effect settlement.
A prediction admitted with unfinished effects remains unsettled. No second copy
of source token state is maintained by the adapter.

## Checks

54 related tests pass, including feature-map equality, invalid generations,
dirty sources, padding, shared readers and GPU inference directly into admission
without test weights. The integrated unit test uses synthetic ridge coefficients;
the saved-state audit below separately checks actual trained weights.

`audit_device_ridge_transition.py` uses the saved dot-product corpus and frozen
`class-history-neighborhood-input.npz` model (hash recorded in the JSON report).
It isolates direct consumption with oracle source states and observed routes;
these are audit inputs, not an autonomous runtime schedule. It performs no fit
or model selection on test data.

Across 5,935 inputs (5,553 complete, 5,550 complete and linked), GPU versus original
CPU model differs by at most 4.11272e-6; all outputs satisfy the original
absolute/relative tolerance. Direct linked token MSE is 0.00170610. This is a
numerical token metric, not Eq exact-state accuracy or committed mutation
correctness. No accuracy gain is claimed.

Preparation takes 1.450 s, CPU reference computation 0.0986 s, cold GPU inference
including compilation 0.888 s. Batch packing/upload/readback are not fully timed,
so these are not end-to-end throughput or speedup measurements. Request arrays
sum to 80,748,229 bytes, with at most 63 source edges per batch row. This identifies
an important remaining problem: the audit expands static role/routing data per
instance. Shared compiled layouts must remove that expansion in the runtime;
adding more features without this change may increase overhead substantially.

## Reference and next obligations

The tracked Bake branch advanced to `2232ef9b`: ownership admission discovers
candidates from existing ordinary sources instead of repeatedly scanning completed
history. It retains the same eligibility checks and adds no maintained queue.
The GPU candidate enumeration remains dense here; no analogous candidate-work
saving is claimed. A future resident batch layout should derive candidates from
existing active/pending state and keep static role matrices shared.

Still required: request construction from live multi-entry matching rather than
observed traces; GPU dynamic scalar/neighborhood encoding; a proved complete
ownership takeover; original Run closure and stage progression. This is a
standalone mechanism and saved-input numerical audit, not full Eggcc execution.
