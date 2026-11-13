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

## Shared coefficient layouts and width buckets

The live adapter now accepts a separate resident coefficient layout. A single
layout broadcasts over a batch; a bank of layouts accepts one checked integer
layout index per request. Source indices, generations, seed/query features,
readiness and edge masks remain dynamic. Invalid layout indices block readiness.
Both paths continue into the same proposal/admission call. This is a batched
coefficient gather followed by dense floating operations, not a GPU traversal or
per-port hash lookup. It still has gather cost and does not remove all indexing.

The saved-input audit groups exactly identical ordered edge/channel coefficients,
including provider multiplicity. This is numeric layout sharing, not a claim
that distinct Cells have identical semantics. Layout discovery currently uses
observed routes; the runtime compiler must supply legal layouts and live source
bindings. `pack_audit_requests` explicitly provides generation-one oracle state
and is not a runtime request builder.

Exact-layout grouping alone reduced inputs to 16,899,235 bytes but fragmented
execution into 1,558 batches. Width buckets instead pad shared layouts to the next
power of two, keeping different layouts in the same dispatch. On the same 5,935
saved inputs:

| Layout | Uploaded coefficient + request bytes | Batches | Warm GPU batch sum |
|---|---:|---:|---:|
| Expanded | 80,748,229 | 93 | 51.20 ms |
| Shared, width buckets | 19,391,897 | 96 | 47.09 ms |

The shared total contains 9,745,824 static bytes and 9,646,073 dynamic bytes. This
is a 76% input-byte reduction for this audit, not total runtime memory reduction.
Warm time sums the minimum of three executions of each prepared batch, with a
synchronization per batch. Preparation, upload/readback and actual matching are
not included; no end-to-end speedup is claimed. Initial compilation is sensitive
to persistent kernel caches: earlier first-use bucket execution took 2.80 s,
while the recorded repeated audit took 0.0757 s. Neither is a portable startup
estimate. Resident banks also retain padding and indexing overhead.

Both current audit modes retain maximum reference difference 4.11272e-6 and
identical direct-linked token MSE 0.00170610; this change does not improve model
accuracy. 56 mechanism tests pass, including mixed indexed layouts, invalid index
rejection, per-source generation checks and GPU numerical equivalence.

Reproduce with `audit_device_ridge_transition.py TRACE MODEL OUTPUT`, adding
`--shared-layouts` for exact grouping or `--bucket-layouts` for banked width
buckets. Reports are `expanded-ridge-layout-results.json`,
`shared-ridge-layout-results.json` and `bucket-ridge-layout-results.json`.
Reference Bake tip remains `2232ef9b`. No native runtime code is changed here.
