# Bake-local conditions as latent quadratic forms

This restores useful local output/equality hints to the shared latent recurrence
without reconstructing the full state. It uses the existing supported finite
layout and direct input-union plan. These are numerical hints, not runtime proofs
or permission to retire a Cell.

For a latent row z and the shared decoder D, the energy of selected output
channels is `z Qout z^T`, where Qout is the average Gram matrix of those decoder
columns. For a known union pair, use the difference of its two port decoders;
its Gram matrix yields `z Qeq z^T`. Sum/average these for multiple pairs. Bake
compiles the two fixed matrices from the existing output layout, alias tracking,
shared basis, scale and per-interface gain. No target channel values enter them.

The device uses two batched quadratic forms, clamps tiny negative roundoff to
zero, and constructs eight columns from counts and energies. Dynamic energies
use bounded transforms e/(1+e), sqrt(e)/(1+sqrt(e)) and tanh(4e), avoiding the old
unbounded quadratic input columns. Both ridge state and emission readouts are
refitted using the same initial/completed/identity controls and workload split.
No-request controls have zero condition matrices/counts. No backpropagation.

## Actual learned recurrence result

| 850 test inputs, 16 rounds | Latent baseline | With folded conditions |
|---|---:|---:|
| Exact catalog target and stopped | 738 | 788 |
| Initially novel but never emitted | 70 | 12 |
| False emissions on true completed latent | 51 | 12 |
| Final active requests | 6 | 4 |
| Latent numerical audit | pass | pass |
| Final decoded-state numerical audit | pass | pass |
| f64 decoder disagreements | 0 | 0 |
| Intermediate full-state decodes / CPU reads | 0 / 0 | 0 / 0 |

Both select alpha 0.1. There are no acceptance tolerance changes. The result is
still below the earlier 790 narrow full-state model and is not a full-runtime
correctness claim. It is stronger than the oracle basis experiment: completion
states are predicted and fed back without teacher refill, but the request is
still the same binding across rounds. Changed successor requests and growing
output tokens remain untested in this path.

## Cost and limits

The learned coefficient matrix is 905 x 129, but compiled condition matrices are
currently stored per input: 27,852,800 float32 values for the 850 test cases,
111,411,200 bytes (about 111 MB). This is additional to 6,963,200 attachment floats,
the shared basis and the ridge weights. Zero/repeated matrices are not yet shared.
Every round performs the fixed forms even when some conditions are absent. No
speedup is claimed; preparation, storage and bandwidth cannot be ignored.

The compiler proves which ports to inspect, not that their compressed numerical
features establish Eq. Gram matrices are exact algebraic foldings of the current
decoder, which itself only approximately represents a Cell. Binding/source
provenance, identity, visibility, ownership and global novelty still require their
respective checks. The candidate dictionary still contains held-out states.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/latent_cell_completion.py MANIFEST CATALOG_MODEL.npz BASIS.npz BASIS_REPORT.json MODEL.npz RESULT.json --rounds 16 --bake-conditions
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_latent_bake_conditions test_latent_cell_completion
```

`latent-condition-results.json` records the complete outcome and model hashes.
Model weights must be paired with the result's feature-mode configuration.
Tests compare both quadratic energies with explicit decoded-port calculations,
NumPy/Metal evaluation, bounded transforms and the empty condition plan. The
55-test related suite passes. No native executor implementation changed.
