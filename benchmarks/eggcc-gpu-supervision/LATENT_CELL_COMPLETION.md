# Learned completion in the shared latent state

This connects the layout-weighted basis to a learned GPU transition. Unlike the
preceding oracle compression test, inputs are original local Cells and outputs
are predicted. Runtime recurrence keeps only the 128-dimensional latent. There
is no intermediate 34,080-dimensional body/boundary reconstruction or CPU refill.
It still repeats one fixed successful binding; it is not full successor/ruleset
saturation or dynamically growing tokens.

## Fixed dataflow

1. CPU encodes the original source once and projects it through the train-only
   basis. It also compiles the request, role code and attachment matrix.
2. A query attachment reads the current latent with one batched matrix multiply.
   Compile the old port projection through the common basis, inverse block scale
   and interface gain. The resulting matrix is 128 x 64 for each current layout.
3. Features concatenate tanh(latent), request, roles, tanh(attachment), and the
   request/attachment product, followed by fixed random tanh features.
4. Closed-form ridge predicts 128 next-state coordinates and an emission score.
   A score below 0.5 retains the old state; otherwise the absolute predicted state
   becomes the next input. No residual accumulation, nearest-catalog replacement
   or teacher value is used inside the recurrence.
5. After all rounds, decode once and measure the result against the existing
   finite candidate catalog. CPU f64 distances independently audit final selection.

Training uses initial-to-completed, completed-to-itself/no-emission, and no-request
identity controls. Each completed control's local idempotence is verified by the
conditional teacher. Only the train partition enters the ridge solve; validation
selects alpha (0.1). No backpropagation is used. The emission head is newly fitted
with these latent features, not copied from the previous model. Consequently this
changes the representation, features and stop head together; it does not isolate
compression's effect on accuracy.

## Result

850 test inputs, 16 free GPU rounds:

| Metric | Result |
|---|---:|
| Exact catalog target | 741 |
| Exact target and stopped | 738 |
| Initially novel but never emitted | 70 |
| Final active requests | 6 |
| False emissions on true completed latent states | 51 |
| Latent numerical audit | pass |
| Final full decoded-state numerical audit | pass |
| f64 decoder disagreements | 0 |
| Intermediate full-state decodes / CPU reads | 0 / 0 |

Numerical checks keep the existing 0.002/0.004 tolerances. Accuracy is below the
prior 790 stable narrow-state model, so this is not accepted as a correctness
improvement. The oracle's 850/850 separability result never implied this predictor
would achieve that accuracy. Its newly learned emission head misses required
outputs and rejects/accepts completed states incorrectly. Previously effective
Bake-local Eq/output hints are not yet included in this latent feature set.

The state-and-score coefficient matrix is 897 x 129; the old moments state readout
was 1,033 x 34,080. This is a matrix-size comparison, not measured speedup. Shared
basis storage and final decoding remain. Test attachment matrices alone contain
6,963,200 floats (850 x 128 x 64), and are currently prepared per input on CPU.
Sharing compatible compiled projections and charging encoding/preparation remain
necessary before a runtime performance claim.

## Reproduce and coverage

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/latent_cell_completion.py MANIFEST CATALOG_MODEL.npz ACTIVE_BASIS.npz ACTIVE_BASIS_REPORT.json NEW_MODEL.npz RESULT.json --rounds 16
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_latent_cell_completion
```

The basis and catalog fingerprints must match the supplied report and manifest.
`latent-cell-results.json` records model hashes and the complete outcome; binaries
stay on the external SSD. Tests compare folded attachment with explicit decode
plus the original interface read, including repeated bindings and empty requests,
and verify NumPy/Metal feature agreement. The related 53 tests pass.

The current catalog includes held-out targets. Exact selection is not proof of
native identity, visibility, scalar execution, global novelty or ownership
transfer. The next step is to fold useful Bake-local conditions into this same
latent dataflow and evaluate actual changed successor requests; restoring a
separate full runtime state would defeat the intended execution representation.
