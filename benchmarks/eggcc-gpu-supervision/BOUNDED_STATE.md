# Output-range ablation for recurrent Cell states

This is an inference-only diagnostic on the frozen Bake-stop model, not a new
trained model or a runtime default. `corpus_repeat_probe.py --bounded-state`
projects accepted proposals to a conservative range before the next round. It
does not force emission off, replace states with teacher answers or perform a
nearest-catalog decode between rounds.

Boundary channels are produced by tanh in the teacher, so each coordinate lies
in [-1,1]. The body encoder sums one tanh vector per fact and divides by sqrt(N),
so each body coordinate has magnitude at most sqrt(N). For the supported local
constructor/union teacher, each effect adds at most one fact; union and canonical
normalization cannot increase fact count. The static per-input bound is therefore
sqrt(max(1, number of source facts + number of effect instructions)). Including
copy/union instructions makes this conservative. It uses no target values or
observed target fact count. The probe also checks every teacher target against
these bounds before executing. This bound is not a claim about arbitrary egglog
primitives, global closure or an unbounded sequence of distinct requests.

The output projection is elementwise min/max, with a per-Cell body scale and
constant boundary scale. It introduces no runtime graph lookup, intermediate host
read or per-token loop. All underlying model coefficients and decision thresholds
are unchanged. The compiled path uses the same projection in the NumPy audit.
Clipped states are not necessarily valid encoded graphs, much less correct
completion states. Boundedness alone gives no contraction or termination proof.

## Reproduction

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST BAKE_STOP.npz BOUNDED_8.json --rounds 8 --bounded-state
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST BAKE_STOP.npz BOUNDED_16.json --rounds 16 --bounded-state
```

Large inputs/models remain on the external SSD. Related unit tests cover range
preservation, both channel groups, and NumPy/Metal agreement for the projection.
Full recurrent probes retain the original numerical tolerance. No native runtime
semantic acceptance or throughput claim is made.

## Evidence and rejection

| Metric | Unbounded, 8 rounds | Bounded, 8 rounds | Bounded, 16 rounds |
|---|---:|---:|---:|
| Exact catalog target and stopped / 850 | 815 | 817 | 817 |
| Final active requests | 7 | 5 | 4 |
| Aggregate body RMSE | 827087.06 | 0.8340 | 0.8342 |
| Backend coordinates outside tolerance | 904 | 3 | 41430 |
| Backend emission disagreements | 0 | 0 | 0 |
| Numerical audit | fail | fail | fail |

The projection prevents the observed scale explosion but does not make the
recurrence converge reliably. Even the three-coordinate eight-round disagreement
is a failure under the original acceptance tolerance; it is not waived. By round
16 the backends diverge substantially in latent state while still agreeing on all
emission decisions. Candidate counts therefore cannot certify continuous-state
stability. The experiment remains rejected as a reliable completion runtime.

This isolates a useful distinction: range preservation mitigates overflow, but
stable continuation requires controlling sensitivity of the recurrent mapping.
A next model should represent bounded outputs during fitting and measure recovery
from nearby predicted states, rather than relying on post-hoc clipping of an
unconstrained residual. This test does not establish that a particular bounded
nonlinearity or contraction constraint will retain the required information.

All paired reports are in `bounded-state-results.json`; 39 related unit tests pass.
