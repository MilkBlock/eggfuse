# Preserve port roles in floating provider aggregation

Four floating channels improve known-state recovery over a matched zero-channel
control, without expanding the 128-float Cell token. They do not increase unknown
state coverage or establish a speedup. All results use the same three training
workloads, euler validation and dot-product test as the original replay.

## Representation and matched control

The original aggregate adds all role-weighted producer tokens into one vector.
The new aggregate retains that vector as channel zero and adds three signed
projections of the consumer-port and producer-result roles. A fixed seeded
128×3 dense matrix and tanh generate these three real-valued coefficients.
They are neither binary masks nor learned by backpropagation. All provider
alternatives remain present; no unique owner is inferred.

For an edge e, let b[e] be its existing 128-float role weight and r[e] its four
channel coefficients. With producer token h[e], aggregation is:

```
M[e, :] = h[e, :] * b[e, :] / sqrt(number_of_edges)
P[channel, :] = transpose(R) @ M
```

Bake/trace preparation supplies fixed source indices, b and r. GPU executes
batched gathers, elementwise weighting, this dense floating matrix product,
and the existing ridge/nonlinear readout. There is no per-port interpreter or
new data-dependent branch on GPU. Observed matching and routing still come from
the CPU trace; this is not autonomous matching or saturation.

The raw feature width grows from 448 to 1,216, with the same 256 random tanh
features. Target state stays 128 floats. The control uses the **same widths and
random projection**, but zeros the three additional channel coefficients.
Both models select ridge alpha from validation independently. No-provider
refits remain available as separate controls. Channel count four was the
predeclared comparison, not chosen by scanning test recovery rates.

## Recovery and limitations

| Predictor | Known-state recovery / 3,855 | Mean per distinct state |
|---|---:|---:|
| Previous single channel | 3,627 | 81.04% |
| Four-channel shape, added coefficients zero | 3,614 | 80.37% |
| Four active role channels | **3,647** | **82.60%** |

The active model recovers 33 more instances than the matched zero control, and
20 more than the previous single-channel model. These are normalized slot states
selected from the **training-only** dictionary, not native graph correctness.
There remain 1,190 unseen states of known templates and 508 unknown-template
instances; dictionary coverage is unchanged. Another 382 incomplete captures
remain marked boundaries. No whole-program 90% claim follows.

On the 1,677 instances with multiple possible providers, predicted-state RMSE
is 0.04292 for active channels and 0.04388 for zero channels. On the 3,280 instances
of variable training templates, active-channel RMSE is worse (0.01847 versus
0.01631). State-discrimination improvement and squared-error improvement remain
different questions.

Both models pass the CPU/GPU audits for gold inputs and 31-layer predicted-state
replay, with zero coordinates outside atol=0.002 / rtol=0.004. No intermediate
state is read back. No gradients or backpropagation are used.

## Factorization and actual storage charge

The first implementation stored each outer product r[e] × b[e]. The final
implementation stores its two factors and uses the matrix product above. The
expanded and factored implementations recover the same 3,647 / 3,614 states;
a direct numerical regression checks factored versus expanded aggregation.
The frozen old single-channel model also retains all previous dictionary
recovery counts after this refactoring.

For the test trace, unpadded edge coefficients shrink from 7,223,808 floats
(28,895,232 bytes) to 1,805,952 base floats plus 56,436 route floats
(7,449,552 bytes). This is a storage result, not a throughput result.

Padding still matters. Across the prepared layers there are 93,748 padded edge
slots. Base and route arrays total **49,498,944 bytes**, versus 191,995,904 bytes
for expanded coefficients. The largest layer has 49,225 edge slots. Source
indices add 374,992 bytes, and the instance state array is 3,038,720 bytes.
These are cumulative plan-array counts, not peak allocator measurements;
Python objects and temporaries are excluded. The primary inference weights
also grow to 499,840 floats, versus the previous 204,928.

The recorded factored GPU replay wall times are 0.291 s (active) and 0.189 s
(zero); corresponding CPU times are 0.189 s and 0.197 s. These include plan
construction, compilation and dispatch and are single diagnostics. Compiler
cache effects differ between runs. **No speedup is established.** Further
work must address padding and shared template coefficients as well as fidelity.

## Reproduce and verify

Use the existing `multi_entry_ridge.py` command with `--channels 4`; for the
matched control add `--zero-role-channels`, writing different model/report paths.
Run `audit_multi_entry_dynamics.py` on each model. It reads channel metadata from
the saved model; old models default to one channel. Text results are the
`port-channels4-factored[-zero]*-results.json` files. Binary models remain on the
external drive.

`layout_costs(dataset(trace, 4))` reproduces the counters in
`port-channel-layout-costs.json`. New tests verify that swapping producer
connections changes role channels while preserving channel zero, and that the
factored GEMM agrees with explicitly expanded outer products. The related suite
passes 81 tests. No CPU executor behavior changed.
