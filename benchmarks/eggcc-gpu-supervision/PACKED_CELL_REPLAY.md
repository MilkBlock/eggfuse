# Pack Cell aggregation without splitting the ridge readout

The frozen four-channel model now has reusable GPU execution plans. Grouping
similar edge counts removes most padded coefficients while preserving one
batched ridge readout per dependency layer. Model coefficients, training data,
consumer inputs and observed connections are unchanged.

Three plans are compared:

- **Flat:** one positive-edge aggregation group per layer.
- **Degree buckets:** group counts by powers of two; allocate each group's
  actual maximum width, not the rounded bound.
- **At most two groups:** sort by edge count and select the single split that
  minimizes padded slots. This uses only known plan dimensions, not target
  states or held-out accuracy.

Zero-edge Cells receive a constant zero provider vector and do not gather dummy
states. The flat control gets this same improvement. Groups' pooled vectors are
concatenated in a compiled order, then all Cells in the layer share **one** ridge
matrix computation and one destination update. Preparation rejects a dependency
on a same/later valid layer; this proves only the numeric replay ordering, not
concurrent egraph write safety. Invalid-capture boundaries remain explicit.

Preparation hoists per-instance normalization and route selection out of the
edge loop. It also avoids constructing unused fallback vectors on every edge.
Plans and uploaded arrays are reusable; the second call starts from the same
initial state and produces identical results. Static shape choices occur on the
host during compilation, with no new GPU-side variable control flow and no
intermediate state readback.

## Actual dot-product replay

All plans use the same 31 dependency layers and 31 ridge readouts:

| Plan | Aggregation groups | Padded edge slots | Coefficient bytes | Largest layer coefficient bytes |
|---|---:|---:|---:|---:|
| Flat | 30 | 91,014 | 48,055,392 | 25,990,800 |
| Degree buckets | 114 | 16,343 | 8,629,104 | 3,192,288 |
| At most two groups | 59 | 27,831 | 14,694,768 | 6,534,000 |

All have one additional zero-input group. Coefficient sizes count actual NumPy
plan arrays before upload, cumulatively across layers. Source/destination index
bytes are separately recorded in `packed-cell-replay-results.json`. Model and
instance-state storage are unchanged. Allocator temporaries, shader binaries
and Python object storage are not included; these are not peak-device-memory
measurements. Template coefficients are still duplicated across instances.

All three plans and the previous replay recover exactly **3,647 / 3,855**
training-dictionary-covered states. The 1,190 unseen states, 508 unseen-template
instances and 382 incomplete captures remain uncovered. CPU/GPU and
new-plan/original comparisons pass atol=0.002 / rtol=0.004, with maximum absolute
numeric difference about 1.61e-6. Repeated calls using the same GPU plan are
bit-identical in this diagnostic. No model fitting or backpropagation occurs.

## Cost accounting, not an end-to-end speed claim

| Plan | CPU plan preparation | GPU first call | GPU second call | CPU execution |
|---|---:|---:|---:|---:|
| Flat | 19.13 ms | 19.43 ms | 6.01 ms | 24.74 ms |
| Degree buckets | 18.13 ms | 8.75 ms | 5.58 ms | 15.68 ms |
| At most two groups | 19.00 ms | 6.77 ms | 5.44 ms | 15.41 ms |

GPU setup/upload is reported separately in the artifact. Each plan was invoked
twice to verify reuse, not in a statistical throughput campaign. First calls
include compilation and are affected by shared shader caches and execution
order. Earlier diagnostic calls were also made while adding the two-group plan
and removing redundant host preparation. Do not interpret these samples as a
robust speed ratio. Full corpus parsing/encoding and actual matching are outside
these execution times, and the earlier encoding cost has not been eliminated.

The at-most-two-group plan is a concrete memory/dispatch tradeoff: it preserves
most storage savings with fewer than half as many aggregation groups as the
fine buckets. Both options remain experimental. No native executor, token
ownership, matching, unknown-state coverage or saturation behavior changed.

## Reproduction and tests

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/packed_cell_replay.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/port-channels4-factored.npz" "$ROOT/port-channels4-factored.json" \
  "$ROOT/packed-cell-replay.json"
```

The runner checks model, trace and training provenance against the frozen model
report. Three tests verify destination coverage and readout counts, numeric
agreement and reusable state, and rejection of same-layer dependencies. The
related suite passes 84 tests. Raw inputs and models remain on the external SSD;
the SSD was remounted after it was found connected but unmounted during this
run, without changing its stored data.
