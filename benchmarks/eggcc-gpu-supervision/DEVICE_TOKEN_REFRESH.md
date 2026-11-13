# Refresh source state before direct continuation

This is a standalone GPU mechanism, not the autonomous Eggcc runtime. No
backpropagation is used. Stable Cell semantics do not imply immutable floating
features: Eq completion can change the source partition while its actual result
identities and storage slots remain unchanged. Consuming the old token loses
information even on a single direct continuation, independently of rollout depth.

`device_token_refresh.refresh` reads current slot roots, typed roles and scalar
codes, recomputes the existing class-balanced 128-dimensional representation,
and clears the dirty flag only for complete, visible, settled states. Missing
fields, invalid identities, unavailable scalar features and unsettled equality
remain explicit obligations. Inactive but visible shared sources can refresh;
this does not transfer their ownership or retire their payload.

A compiled Metal test closes Eq, rejects consumption of the dirty source,
refreshes it, and admits its successor without intermediate CPU readback. Its
successor weights are a test transform, not a fitted ridge model. The refresh
produces features, not proof of a predicted completion or stage saturation.

## Saved real-state audit

`device-token-refresh-results.json` records 5,553 complete dot-product states
across 154 templates and 192 batches; 382 incomplete states are excluded.
Maximum GPU versus CPU reference encoding difference is 6.25849e-7, with no
component outside the 2e-5 tolerance. The audit remaps typed equality identities
to local labels because only equality matters to this encoding; it is not a
runtime identity allocator. Post-state labels and scalar encodings are supplied
by the CPU for this audit only, not proposed as runtime inputs.

Measured preparation: 0.125 s; CPU reference encoding: 0.170 s; GPU upload:
0.00318 s; GPU encoding including shape compilation: 1.100 s; readback:
0.000721 s. These cold, heterogeneous batches do not demonstrate speedup.
Uploaded arrays total 12,123,972 bytes; the largest partition mask has 156,816
elements. The slot-pair mask is quadratic and remains an optimization liability.
Accuracy gain is not measured by this audit. All 50 related mechanism tests pass.

## Bake alignment and remaining work

Reference `9d61be39` removes hash payloads only after exact port-domain lookup
has taken over their role. Apply the same discipline here: refreshing from
existing slots adds no second identity registry, but this prototype has not yet
replaced host encoding in the observed-trace training driver. Therefore no saved
runtime encoding work is claimed. Scalar feature generation on GPU and the
trained successor adapter remain live obligations.

Next accuracy experiments must separate correct-source direct consumption from
predicted-source consumption, retain the same target representation, and measure
false merges/missed relations as well as exact-state accuracy. Candidate local
features should project current source slots and Bake operand relationships;
future post-state facts must remain labels. GPU stage advancement still requires
closure of uncovered and pending work, not merely zero accepted tokens.
