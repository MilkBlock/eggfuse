# Dynamic-state audit of the frozen multi-entry model

The earlier RMSE comparison was insufficient to judge provider usefulness.
With exactly the same ridge coefficients, predicted provider states recover
27 more known local states than the no-provider refit, despite higher RMSE.
This is a bounded dictionary result, not full egraph correctness or an overall
90% success claim.

`audit_multi_entry_dynamics.py` uses an exact static template key (query,
effects including literals, slot sorts; excludes rule names and runtime IDs).
For each template it builds a mean, most-frequent state and dictionary from
**training captures only**. The mean is the appropriate static squared-error
baseline; the mode is a stronger constant baseline for exact-state selection.
Test states never enter either baseline or dictionary. Model, training manifest
and test trace hashes must match the previous experiment.

On dot-product, 113 of 154 observed complete-capture templates occur in training.
There are 51 training templates with more than one normalized captured state.

| Complete test subset | Cases | Predicted-provider RMSE | No-provider RMSE | Template mean RMSE |
|---|---:|---:|---:|---:|
| Known template | 5,045 | 0.01827 | 0.01448 | 0.04361 |
| Variable training template | 3,280 | 0.01598 | 0.01307 | 0.05314 |
| Unseen state of known template | 1,190 | 0.02659 | 0.02215 | 0.08461 |
| Unknown template | 508 | 0.11499 | 0.11460 | unavailable |

The models do predict variation beyond template means; low error is not solely
static-template memorization. However, provider aggregation still loses on the
squared-error objective even within variable templates.

## Training-only state recovery

For templates/states present in training, choose the nearest training token in
f64 and compare its normalized slot-state key to the actual captured key.
Distance ties are ambiguous and fail. Eq identities are normalized within each
Cell; scalar values and slot assignments remain in the key. Equality here does
not include cross-instance identities, visibility, ownership, full graph facts
or native extraction semantics.

| Predictor | Recovered / 3,855 covered instances | Mean recovery per distinct state |
|---|---:|---:|
| Gold providers | 3,624 | 81.32% |
| Predicted providers | **3,627** | **81.04%** |
| No-provider refit | 3,600 | 78.09% |
| Template mean | 2,457 | 39.10% |
| Most frequent training state per template | 2,873 | 39.47% |

There are 266 distinct covered test states. The state-balanced metric first
averages success across instances of a state, then gives every distinct state
equal weight. It prevents high-frequency states from dominating the result.
Against the no-provider refit, predicted-provider replay has 105 wins, 78 losses,
3,522 joint successes and 150 joint failures. Net gain is 27 instances; no
statistical/generalization conclusion across workloads is established.

The denominator cannot omit unsupported cases when describing whole-system
coverage: 1,190 complete instances have unseen states in known templates and
508 have unseen templates. The training dictionary cannot decode these 1,698
instances. A further 382 instances were already excluded for incomplete capture.
The 3,627 recovered states therefore do not establish 94% overall correctness,
and do not certify even those instances as native graph executions.

## Implication

Do not discard provider inputs solely because their token RMSE is higher. Add
state-discrimination and coverage metrics alongside numeric error. At the same
time, the 105/78 tradeoff is too small and conditional to justify treating this
aggregation as solved. Next comparisons should preserve the port correspondence
and report dynamic-state recovery, unknown-state coverage and numeric stability
separately. Broadening a held-out dictionary would hide the main missing ability.

This audit reevaluates the frozen, previously GPU-audited coefficients on CPU.
No ridge retraining, GPU speed measurement or runtime change occurred. The only
change to `multi_entry_ridge.dataset` adds static family metadata; numerical
features and predictions are unchanged. Three tests cover exclusion of unknown
states, ambiguity handling, and static-key inclusion of literals but not names.
The related suite passes 79 tests.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_multi_entry_dynamics.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/multi-entry-ridge.npz" "$ROOT/multi-entry-ridge-results.json" \
  "$ROOT/multi-entry-dynamics.json"
```

Text results are committed as `multi-entry-dynamics-results.json`; models and
raw traces remain on the external drive.
