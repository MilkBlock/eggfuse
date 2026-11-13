# Class-balanced whole-Cell tokens: improved recall, unresolved false merges

This standalone experiment changes the **whole-Cell state encoding**, not just
its Eq boundary decoder. Actual CPU-captured multi-entry wiring is replayed on
GPU across 31 dependency layers. Predicted tokens feed later Cells; there are
no intermediate token readbacks and no backpropagation. Matches, routes and
external input observations are still supplied from CPU traces. This is not an
autonomous GPU egraph or a native semantic acceptance result.

## Representation and isolation

The original encoder gives every slot a message. Repeated members of one Eq
class influence both the class context (sum divided by square root of member
count) and the final moments. The optional `--encoding class-balanced` changes:

- Each Eq class context becomes the mean of its member role vectors.
- Each member message has weight `1 / class_size`; a class has total weight 1.
- Scalars retain individual weight 1 and their dynamic scalar encoding.
- The first moment is the weighted sum divided by square root of total weight;
  the second is the weighted mean of squared messages. Concatenation and tanh
  still produce 128 floats.

This removes repeated weight for identical-role aliases, but does not discard
distinct roles in a class or promise invariance to arbitrary template rewrites.
Roles, requests, four routing channels, candidate providers, GPU layer schedule
and token width are unchanged. It does not contract the routing edges. The
input encoder uses only current input roots; target roots after the Run are
training/audit labels. The target partition is never injected into an input.
Graph IDs are grouping keys only, never floating features. The main token
transition and no-provider control are separately refit with closed-form ridge;
alpha 10 is selected on validation. Decoder alpha remains 100.

Model files record the encoding. The dynamics audit, packed replay and boundary
decoder all read this metadata; historical models without it retain `slot`.
The new mode is optional and does not change the default.

## Results and regressions

All splits and source hashes are unchanged from `port-channels4-factored`.
There are 5,553 complete test instances; 382 incomplete captures are excluded
from complete-state scoring. Zero incomplete tokens are consumed as providers.

| Diagnostic | Slot encoding | Class-balanced encoding |
|---|---:|---:|
| Train-dictionary state recovery / 3,855 covered cases | 3,647 | 3,666 |
| Mean recovery over 266 distinct covered states | 82.60% | 86.17% |
| Dictionary-free Eq partitions / 5,454 comparable cases | 4,287 | 4,438 |
| New state, known template Eq partitions / 1,177 | 966 | 966 |
| New template Eq partitions / 508 | 200 | 176 |
| Recall of Eq beyond static proofs | 37.68% | 47.19% |
| False Eq pairs | 789 | 962 |
| Missed Eq pairs | 2,038 | 1,727 |
| False Eq pairs after transitive closure | 2,052 | 2,150 |

Both Eq columns use the static-class decoder from `TOKEN_EQ_READOUT.md`, fitted
on oracle tokens of their respective encoding. They audit all 77,684 original
slot pairs using 34,240 learned class queries. Ninety-nine complete captures
have no comparable Eq pairs and are not counted as successes. The dictionary
still cannot represent 1,190 new states and 508 unknown-template instances;
its covered recovery rate is not an overall accuracy claim.

Predicted-token Eq marks drop from 1,167 to 1,016 (18.63% of checkable cases),
but this hides the false-merge regression. Unknown templates account for 744
false Eq pairs and suffer 95 full-partition losses versus static facts alone,
with zero wins. Even with oracle tokens, the new decoder produces 1,602 false
pairs, increasing to 12,718 after closure. It is unsafe to use closure as a
repair of these predictions. No learned Eq authorizes union.

Known-state recovery with the refitted no-provider control is 3,598/3,855, below
the connected model's 3,666. There are no observed exact code collisions in the
captured training/validation or test states, which is not a proof of universal
injectivity. Numerical CPU/GPU audits pass; boundary threshold disagreements
are zero. Raw RMSEs across the two encodings are in different coordinates and
must not be interpreted as an accuracy ranking.

## Costs and remaining obligations

The whole-model preparation diagnostic is 2.003 s and fitting 0.221 s. Cold GPU
replay (including plan construction/upload/compilation) is 0.191 s; CPU replay
is also approximately 0.191 s. This is one diagnostic, not evidence of a GPU
speedup. Routing/model dimensions and per-instance state storage do not shrink.
The additional group weighting is currently CPU preparation work.

The boundary experiment prepares test data in 0.940 s, encodes features in
0.296 s, runs GPU ridge plus transfers in 0.0104 s, and audits/writes marks on
CPU in 0.169 s. Its full CPU feature matrix still occupies 210,644,480 bytes.
These separately run diagnostics are not an end-to-end runtime timing.

The evidence supports reducing alias bias, but does not solve unknown-template
readout, scalar verification, ownership transfer, new match/token generation,
novelty or saturation. The increase in false merges prevents adoption. Further
work must retain these negative results and distinguish learned completion
within covered Cell families from unsupported-family CPU boundaries.

## Reproduction

Use the same external `ROOT` and Python environment as `MULTI_ENTRY_RIDGE.md`:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/multi_entry_ridge.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/rhs-validation-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-balanced.npz" "$ROOT/class-balanced.json" \
  --corpus-manifest "$ROOT/observed-corpus-20261113/manifest.json" \
  --channels 4 --encoding class-balanced

$PYTHON benchmarks/eggcc-gpu-supervision/audit_multi_entry_dynamics.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-balanced.npz" "$ROOT/class-balanced.json" \
  "$ROOT/class-balanced-dynamics.json"

$PYTHON benchmarks/eggcc-gpu-supervision/token_eq_readout.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/rhs-validation-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-balanced.npz" "$ROOT/class-balanced.json" \
  "$ROOT/class-balanced-eq.npz" "$ROOT/class-balanced-eq.json" \
  --static-equalities --quotient --marks "$ROOT/class-balanced-eq-marks.jsonl"
```

The three `class-balanced*-results.json` reports retain provenance and model
hashes. Binary models/captures/marks remain on the SSD. The related suite passes
98 tests, including alias duplicate weighting, identity renaming, partition
sensitivity, scalar sensitivity, empty states and unknown-encoding rejection.
