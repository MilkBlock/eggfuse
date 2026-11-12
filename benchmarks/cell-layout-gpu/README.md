# Shared-layout multi-entry completion on Metal GPU

This is a standalone GPU prototype over the native-checked multi-entry corpus.
It is not integrated into the Rust Cell runtime and does not publish effects.
The compression worktree motivates the interface: shared static wiring plus
instance residuals. This prototype compiles that interface from initial exported
DAGs; it does **not** yet read live compressed PortProgram/component slots.

## Representation and computation

A shared plan contains operators, static edge references, roots and scalar-slot
read positions. Dynamic inputs are float32 scalar values gathered by those read
positions. Node identities never become numerical features. This fixture's
initial topology is static per plan; variable runtime Eq relations would require
additional input evidence and are not silently treated as static.

The 102 held-out inputs use 43 layouts and 642 scalar values (2,568 bytes).
Layout compilation reads only the initial graph, never the target. Distinct
entries can share a layout while varying scalar values. GPU evaluation performs
real-valued fixed random projections, sin/cos/tanh and batched matrix products,
then the fitted quadratic ridge readout. Learned weights are dense float32;
this is not a Boolean matrix representation. Template operators and links are
captured by the compiled function. The orthogonal class-code readout is folded
into the final dense weights exactly.

The existing two-view ridge is reused unchanged, not retrained against test
labels. It was fitted without backpropagation and selected on validation data.
All original train/validation/test assignments remain unchanged. This predicts
one of 24 known completion graphs; it does not generate arbitrary new closures.

## Measured result

See `results.json` for synchronized timings and input hashes. Metal GPU was
required and used (MLX 0.32.4); there is no CPU fallback. GPU raw features and
scores are checked against the original NumPy model, including identical top-1
predictions for all 102 inputs. Accuracy remains 89/102 (87.25%). Five incorrect
predictions pass input containment: containment is not a derivability proof.

Per-layout compilation reduced the initial eager implementation's roughly
34 ms warm batch to roughly 15.7 ms. The original CPU encoder plus ridge took
roughly 7.0 ms for these 102 inputs. **The small natural batch is still slower
on GPU.** Repeating each layout's rows 128 times gives 13,056 rows in roughly
17.2 ms; repetitions are throughput probes, not additional accuracy examples or
real workload occupancy. No same-size CPU speedup is claimed.

Dynamic gathering, input/output materialization, cold execution, warm GPU
encoding plus ridge, and necessary containment checking are reported separately.
First process execution took roughly 2 seconds before the Metal cache was warm;
the saved rerun records 66.5 ms first execution in that process. This is not a
guarantee of cold-driver startup latency. Shared-memory Metal array
materialization must not be described as a measured PCIe transfer. Existing
exports are already canonicalized; export/canonicalization, live instance routing,
lifecycle maintenance and derivability certification are not measured. Missing
costs are null, not zero. No end-to-end runtime acceleration claim is supported.

## Reproduce

Use the corpus/model generation commands in `../cell-multi-entry-ridge/README.md`
with encoder seeds `20261115,20261116` and no moments. Install `mlx==0.32.4` in
that experiment's environment on a supported Apple Silicon machine, then:

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-layout-gpu/run.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --model out/cell-multi-entry-ridge/release-two/model.npz \
  --catalog out/cell-multi-entry-ridge/release-two/catalog.json \
  --output out/cell-layout-gpu/results.json
```

`--eager` disables per-layout compilation for comparison. All timings explicitly
force lazy results to complete. Binary weights/build outputs stay untracked.

Next structural target: batch compatible layouts together or compile a broader
shared expression schedule, reducing the 43 separate dispatch streams. That
must preserve distinct topology and dynamic bindings; padding or larger batches
must be charged. A live runtime adapter must use existing slot ownership and
lifecycle metadata, not reconstruct a second fact graph.
