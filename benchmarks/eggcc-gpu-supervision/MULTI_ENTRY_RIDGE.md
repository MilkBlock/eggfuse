# Multi-provider numeric Cell replay

The GPU now consumes **predicted** producer states along actual multi-entry
connections and evaluates changed consumer requests. This is a standalone
observed-wiring experiment, not autonomous matching, token generation or egraph
saturation. The current aggregation fails to beat a model without producer
states, despite stable numerical replay.

## Data and representation

Training uses fitsinside, loopfact and recfact (3,663 complete captured local
states). Validation uses the smallest eligible original validation workload,
euler. Dot-product remains test. `collect_rhs_training.py --split validation`
selects the original validation partition without reassigning workloads; the
new validation capture passes per-Run and final reference graph comparisons.
Manifest, recipe, trace and model hashes are retained in text results.

Each template supplies fixed 64-dimensional role vectors from slot sort,
query/effect uses, constructor/primitive kind and argument position. Captured
Eq identities are used only to group equal slots. Their numeric IDs never
enter floating features. For each group the role vectors are summed and
normalized; each slot receives tanh(role + group context), or a dynamic scalar
code instead of Eq context. Numeric scalars use a signed log magnitude and
fixed dense direction; other scalar categories use fixed codes. A token is:

```
128 floats = tanh(concat(sum(messages)/sqrt(slot_count), mean(messages²)))
```

This is a lossy local slot-state encoding, not an exact graph serializer.
Template instructions and the observed routing remain external metadata. It
cannot certify identities, ownership, lifetimes or graph semantics. The exact
float32 encoding audit finds no conflicting normalized slot states among the
506 distinct train/validation codes or 1,009 test codes. This finite observation
does not prove injectivity; a regression test explicitly demonstrates the
information-loss case when equal roles hide swapped scalar slots.

For a consumer, linked Eq slots are removed from its gold input seed. The seed
retains external Eq inputs and scalars. All possible provider returns contribute
through fixed role-weighted edges; no unique owner is inferred. Fixed edges
preserve producer/result-slot to consumer-slot metadata, but pooling their
numeric messages is still lossy. Scalars and external inputs are observed at
the consumer boundary; this experiment does not generate those inputs itself.

## Fit and execution

The feature vector contains the external seed (128), template request (64),
pooled provider state (128) and seed × pool (128), followed by a constant and
256 fixed random tanh features. Ridge fits 128 atanh-transformed target columns
with an f64 closed-form solve. Validation selects the regularization strength;
output tanh bounds the prediction. **No backpropagation or gradient descent.**

GPU replay uses precomputed dependency layers and padded gather indices/edge
weights. Each layer performs batched gather/reduction, matrix products and tanh,
then writes predicted tokens into the shared state array. Later layers consume
those predictions. There is no per-node GPU interpreter or intermediate host
state readback. The host submits fixed layers; this is not one monolithic GPU
kernel. All candidate matches, routing and order come from the CPU trace.

Dot-product has 5,935 instances and 31 dependency layers. The 382 incompletely
captured instances are marked CPU boundaries and excluded from scoring. None
of these boundary tokens is consumed as a producer in this dataset; external
consumer inputs still come from observations. The scored full-capture subset
has 5,553 instances, including 2,819 linked consumers and 1,677 consumers with
more than one **possible** provider application. The latter differs from the
link audit's stricter requirement that multiple providers are necessary.

## Result and negative control

| Test subset | Gold provider RMSE | Predicted provider RMSE | No-provider model refit | Shuffled provider RMSE |
|---|---:|---:|---:|---:|
| All complete captures | 0.03890 | 0.03889 | **0.03731** | 0.04550 |
| Linked consumers | 0.04667 | 0.04666 | **0.04268** | 0.05723 |
| Multiple possible providers | 0.04296 | 0.04313 | **0.03848** | 0.05401 |

Both original and no-provider models fit only training data and select alpha on
validation. Shuffling is a fixed diagnostic, not a model-selection criterion.
Provider information affects the prediction, but has not demonstrated useful
incremental accuracy over the external seed and template alone. No exact-state
success percentage or 90% correctness claim follows from latent RMSE.

CPU/GPU float32 audits pass for gold-input inference and predicted-state replay
at the existing atol=0.002 / rtol=0.004, with zero coordinates outside tolerance.
Preparation/encoding took 2.010 s and both fits took 0.069 s. GPU replay including
plan/array construction and dispatch took 0.0517 s; CPU replay took 0.0470 s.
These are single diagnostic runs, not a warmed throughput campaign. **No GPU
speedup is established.** The preparation cost is larger than either replay.

Next structural question: how much prediction loss is in dynamic port relations
versus the easily predicted template component, and does pooling erase useful
producer-to-consumer correspondence? Those require explicit dynamic-state
metrics and a representation test before treating more templates as progress.

## Reproduction

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/multi_entry_ridge.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/rhs-validation-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/multi-entry-ridge.npz" "$ROOT/multi-entry-ridge-results.json" \
  --corpus-manifest "$ROOT/observed-corpus-20261113/manifest.json"
```

PYTHON must provide NumPy and MLX/Metal. ROOT is the external artifact directory.
Binary models and raw traces remain outside Git. Tests cover identity-renaming
invariance, Eq-partition sensitivity, dynamic scalars, all-provider contribution,
predicted-state dependency, a deliberate encoding collision and preserved
partition selection. The related suite passes 76 tests.
