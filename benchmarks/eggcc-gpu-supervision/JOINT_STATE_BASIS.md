# Joint body/boundary state basis: representation viability

The preceding Eq projection satisfied some boundary equalities without fixing the
independently predicted body. This experiment asks whether one shared linear
latent state can represent both fields before attempting another learned transition.
It is an oracle compression test, not an improved prediction or saturation result.

For each of 1,880 training inputs, collect the original and completed states.
Normalize body coordinates by the source/compiler bound, then weight body and
boundary blocks by inverse square-root width. Fit a 128-dimensional uncentered
basis using a fixed-seed randomized SVD, 16 oversampling columns and one power
iteration. No validation/test state enters basis fitting. Zero remains zero.

On validation/test **true completed states**, the GPU computes weighted state to
latent to reconstructed state in one compiled matrix dataflow. CPU independently
reconstructs it and checks the existing 0.002/0.004 tolerances. Final known-catalog
selection uses f64 distances; uncompressed oracle targets are evaluated with the
same catalog and tie rule as a baseline. The dictionary still contains held-out
states, so this is finite-catalog separability, not general graph decoding.

A shared basis reduces representational degrees of freedom but does not prove
that every decoded vector is a valid Cell. In particular, it does not enforce
nonlinear body/boundary consistency, exact Eq, valid identities or visibility.
Linear reconstruction may also leave the original boundary range. The tested
basis is not an information-theoretic compression limit.

Besides padded boundary RMSE, the report measures error only on represented
interface slots and in the actual fixed query attachment. These distinguish
small average error over mostly empty storage from disruption to subsequent
computation. They use known finite interface layouts, not arbitrary token growth.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/joint_state_basis.py MANIFEST MODEL.npz REPORT.json --rank 128 --basis-output BASIS.npz
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_joint_state_basis
```

Large basis/input artifacts stay on the external SSD. Tests verify orthogonality,
known low-rank reconstruction, rank checks and restoration of body scale. No
native executor code or trained ridge transition is changed in this experiment.

## Layout-weighted comparison

The initial global-width loss diluted boundary error with mostly empty storage.
An explicit `--active-boundary-weighting` ablation multiplies each row's boundary
block by sqrt(capacity / max(1, interface_port_count)) before fitting/projection,
and reverses this gain after decoding. Interface size comes from the existing
finite layout, not target values. Thus boundary coordinates have weight
1/sqrt(16 * represented_port_count), instead of 1/sqrt(16 * global_capacity).
Body normalization, rank, algorithm and split remain unchanged.

| Oracle representation metric | Global-width weighting | Interface-width weighting |
|---|---:|---:|
| Validation exact catalog target / 736 | 723 | 736 |
| Test exact catalog target / 850 | 832 | 850 |
| Test body RMSE | 0.00223 | 0.06347 |
| Test padded boundary RMSE | 0.01349 | 0.01238 |
| Test active boundary RMSE | 0.17797 | 0.16464 |
| Test query attachment RMSE | 0.05293 | 0.01487 |
| Test maximum absolute boundary coordinate | 1.22093 | 1.23487 |
| GPU/CPU reconstruction audit | pass | pass |

Both uncompressed oracle baselines select every target exactly. Interface-aware
weighting loses no candidate identity in this finite evaluation, but it does not
preserve exact state or equal-port constraints. It trades body reconstruction error
for query-relevant boundary fidelity. Large active-port error and range violations
remain, despite the perfect catalog selection. This is not 100% prediction,
semantic acceptance or a contraction proof.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/joint_state_basis.py MANIFEST MODEL.npz ACTIVE_REPORT.json --rank 128 --basis-output ACTIVE_BASIS.npz --active-boundary-weighting
```

`joint-basis-results.json` and `joint-basis-active-results.json` preserve both
reports and artifact fingerprints. The weighting mode must travel with the basis
report; it is required to reconstruct the correct per-instance scaling. The
51-test related suite passes. A transient external-drive file-creation error on
the first attempt was investigated with a successful write probe; the completed
runs above exited zero and saved their artifacts.

The next justified experiment is to learn the shared latent completion rather
than supplying its true state, then fold the static query attachment through the
same decoder. That can test actual recurrent use without recreating independent
body/boundary predictors. Initial encoding cost, decoder storage, new token
interfaces and CPU audit remain live obligations; this representation check does
not remove them.
