# Absolute bounded Cell readout

This experiment replaces the accumulated state residual with an absolute tanh
readout. It retains the previous Bake-stop emission head and original finite
conditional completion dataset. It is a standalone GPU prototype, not a native
runtime or a ruleset saturation implementation.

The source/compiler body bound from `BOUNDED_STATE.md` normalizes body coordinates.
Boundary coordinates already have unit range. The ridge feature vector uses this
normalized body, the original request/roles, current boundary attachment and Bake
hints. For the new state readout:

```
y = atanh(clip(normalized_true_completed_state, -0.9999, 0.9999))
C = ridge(features, y)
next_candidate = restore_body_scale(tanh(features(current) @ C))
next_state = where(unchanged_emission_head(current) >= 0.5,
                   next_candidate, current)
```

The finite inverse introduces at most 0.0001 error per normalized target
coordinate near saturation; it is explicit, not an exact inverse at +/-1.
Training rejects teacher values outside the declared ranges. No backpropagation
is used. The old residual coefficient remains in the checkpoint for provenance
and generating training perturbations, but does not define the new state output.

Each train/validation input contributes three rows: initial state, one bounded
proposal from the previous model, and true completed state. All three target the
same completed state. Train contributes 5,640 rows, validation 2,208; test adds
none to this fit. Validation chooses alpha 1.0 on the scaled preactivation loss,
not decoded-state or recurrent loss. Perturbations come from a previously fitted
model on the training inputs, not an out-of-fold model. The emission head is
unchanged, so missed first emissions remain outside this experiment's coverage.

This combines normalization, an absolute readout, tanh output and augmentation.
It is not a controlled attribution of gains to any one of those changes.
Bounded output does not imply a contraction, semantic validity, identity
preservation or completion. Arbitrary output growth and different successor
requests remain unimplemented here. The large padded state and final held-out
candidate dictionary remain unchanged.

## Reproduce

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/fit_bounded_cell.py MANIFEST BAKE_STOP.npz DIRECT.npz FIT.json
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST DIRECT.npz PROBE.json --rounds 16
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_bounded_cell_readout test_bake_stop_features test_corpus_repeat_probe test_corpus_cell_ridge test_observed_corpus test_observed_cell_targets test_boundary_cell_ridge test_chain_completion_audit
```

## Result: numerical agreement improves, completion accuracy regresses

| Sixteen-round test, 850 inputs | Post-hoc clipped residual | Trained absolute tanh |
|---|---:|---:|
| Exact catalog target and stopped | 817 | 775 |
| Final active requests | 4 | 6 |
| Aggregate body RMSE | 0.8342 | 0.7340 |
| Median per-input body RMSE | 0.06466 | 0.05905 |
| Maximum per-input body RMSE | 18.8963 | 11.3047 |
| Backend coordinates outside tolerance | 41430 | 0 |
| Backend emission disagreements | 0 | 0 |
| f64 decoder disagreements | 0 | 0 |
| Numerical audit | fail | pass |

The new state map passes the unchanged numerical audit over 16 free GPU rounds,
without intermediate teacher refill. It does not establish convergence or full
semantic correctness: six requests still emit, and the correct-and-stopped count
falls by 42. Lower continuous RMSE and reliable backend agreement do not imply
correct discrete completion. The fixed emission head still misses 11 initially
novel inputs. This variant is not accepted as an overall runtime replacement.

All original checkpoint arrays, including stop coefficients and the candidate
dictionary, are verified identical with `numpy.array_equal`. Only the direct
readout is added. The full results and model hashes are recorded in
`direct-bounded-results.json`; 43 related tests pass. Tests cover inverse-target
round trips, finite endpoint handling, invalid teacher rejection and CPU/Metal
agreement of decoding.

Next accuracy work should separate target/feature loss from numerical stability,
and evaluate decoded validation error rather than relying only on preactivation
loss. The current comparison does not prove which design choice lost the 42
successes. Full successor changes, growing token sets, native identity and CPU
supervision remain separate obligations.
