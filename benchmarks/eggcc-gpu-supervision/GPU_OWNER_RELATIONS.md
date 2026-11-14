# Dynamic physical-owner context for floating Cell inference

Native synthetic capture showed that query witnesses carry physical owner roles
which Eq partitions alone cannot express. CPU frame retirement is not a valid
label for GPU token retirement: the GPU has its own logical token lifetimes,
physical payload projections and exact generation/coverage checks.

This change keeps transfer permission exact. It adds an optional feature to
`device_ridge_transition` and `device_join_transition.compile_transition(...,
owner_relations=True)`. The compiler supplies fixed structural role vectors.
GPU inference resolves requested logical sources through the existing
`slot_owner` array, checks owner liveness and generation, and computes shared
owner connectivity. Role products, batched floating matmul and tanh encode the
connection into a dense context appended to q. Physical IDs never enter the
floating vectors as numbers. This complements logical source sharing; the two
options can be enabled independently. Dense unaliased storage treats each
logical row as its owner.

There are no per-instance host branches or consumer searches. Configuration
branches are static when MLX compiles the function. Owner access is a fixed
array gather, not eliminated storage access; the relation block has quadratic
work in request source arity. This is an execution feature, not a speed claim.

A model using this feature requires a newly fitted random projection/readout
with the additional width (128 columns for the standard compiler roles). Old
weights are not silently reinterpreted. Current published classifiers and the
Eggcc family driver remain unchanged; no accuracy improvement is established.
No gradient descent is added.

## Validation

Run with the MLX Python environment:

```
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_device_owner_relations.py
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_device_ridge_transition.py
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_device_join_transition.py
```

All 13 tests passed on Metal. The three new tests cover padding and stale owner
checks; actual GPU slot transfer followed by floating inference in a single
compiled invocation; and compiler-generated multi-source matching, inference
and token admission with owner context. Outputs agree with NumPy within 2e-6.
The lifecycle test confirms that transferring physical payload changes the
next inference features while old logical readers remain usable. Weights in
these execution tests are deterministic random test weights, not trained
models or evidence of inference accuracy. This remains the standalone GPU
prototype, not native Eggcc execution on GPU.

Next: synthesize valid owner-sharing/detachment cases and fit the expanded
feature interface using synthetic-only labels, retaining exact transfer guards.

## Training capture replay and coverage

Owner-aware GPU match capture now saves the requested source-owner map, owner
epoch, physical generation/liveness and usable mask at inference time.
`floating_inputs` reconstructs the same extra floating context from this snapshot,
never from later state. The existing witness audit cross-checks each captured
owner against the actual selected query witness; corrupt epochs are rejected.
Missing owner context is an error for owner-aware replay. Other models keep the
previous capture format. Eight owner/capture tests pass, including actual Metal
capture -> NumPy input replay parity within 2e-6 and a corrupted-owner rejection.

Before fitting, `audit_owner_sample_coverage.py DIRECTORY OUTPUT` checks synthetic
input provenance and capture hashes and counts accepted query-atom witness pairs.
The saved 11-case local synthetic corpus has 94 accepted samples, 22 logically
shared pairs, **zero distinct-logical/same-physical pairs**. See
`synthetic-owner-coverage.json`. This counts query-atom pairs, not port repetitions,
transfer events or execution time. No expanded model was trained on this
insufficient distribution. Next generation must deliberately exercise legal
sharing and detachment; pure storage remapping must preserve semantic labels.
