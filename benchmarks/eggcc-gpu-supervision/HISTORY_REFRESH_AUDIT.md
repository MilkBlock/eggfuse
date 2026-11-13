# Repeated observation versus new Cell dependency

This measures a **standalone CPU graph-shape counterfactual** on saved actual
Eggcc RHS captures. It neither changes the native runtime nor performs GPU
inference, and does not certify ownership, retirement, or semantic reuse.

The existing fallback-history experiment retains all constructor observations
from the latest producing Run for a typed identity. A later observation can thus
replace an old source with a whole newer Cell token, even when its returned
identity and representative are unchanged. This is a candidate source of artificial
serial dependence, distinct from inherently sequential egraph reasoning.

We compare that graph with two diagnostic alternatives, preserving adjacent
routes and incomplete-state exclusions:

- Earliest observed Run for the same typed identity.
- Earliest observed Run for the same typed identity **and recorded after-Run root**.

Both keep every alternative source operation in that first Run. Multiple latest
observers redirecting to the same alternatives are deduplicated per consumer
port; different consumer ports remain distinct. No unique owner is invented.
All replacement sources are no later than the original source and remain causal.
The root check compares historical observations, not consumer output labels.

## Results

The two counterfactuals coincide on the eligible edges in all 16 captures.
This does not mean roots never change: dot-product contains 7,580 constructor
observations, 4,465 reobservations of an identity, of which 4,374 also repeat its
recorded representative. The subset actually used by historical fallback is narrower.

| Split / case | Latest layers | Earliest layers | Latest edges | Earliest edges |
|---|---:|---:|---:|---:|
| train / fitsinside | 38 | 19 | 7,444 | 6,481 |
| train / loopfact | 48 | 22 | 6,243 | 5,625 |
| train / recfact | 54 | 25 | 6,948 | 6,627 |
| train / birthday | 62 | 30 | 8,607 | 8,011 |
| train / pascals-row | 69 | 30 | 13,089 | 11,503 |
| train / euclid | 80 | 35 | 14,648 | 13,241 |
| train / binary-fmt | 66 | 30 | 16,335 | 15,010 |
| train / dead-branch | 81 | 35 | 16,026 | 14,635 |
| train / sum-check | 70 | 37 | 21,556 | 19,076 |
| train / sum-sq-diff | 70 | 40 | 22,864 | 18,862 |
| validation / euler | 68 | 36 | 20,965 | 18,238 |
| validation / ackermann | 66 | 34 | 29,698 | 25,483 |
| validation / gcd | 89 | 29 | 39,059 | 32,873 |
| validation / lcm | 132 | 39 | 37,998 | 34,648 |
| validation / newton | 124 | 36 | 52,287 | 45,730 |
| test / dot-product | 91 | 45 | 50,424 | 43,377 |

Dot-product redirects 29,167 original historical edges; 4,639 instances become
shallower. Unlike omitting nullary history (91 to 89 layers), source refresh
policy has a large structural effect across the corpus. No workload partition,
model coefficient, threshold, or prediction label was changed or selected here.

## What remains live

An unchanged constructor identity/root is **not** an unchanged whole Cell state.
Later observations may carry useful surrounding facts. Earlier observations may
be retired or have lost visibility; current captures do not certify their lifetime.
The results do not authorize deleting repair, changing source Run ordering, or
committing an inferred equality. Nor do they show a speedup or accuracy gain.

The next numerical experiment should explicitly separate retained source state
from newly observed context: fit a causal earliest-source variant on training
only, select on the existing validation workloads, then compare full Eq partition
accuracy and false merges with the frozen latest-source baseline. Measure GPU
execution and preparation/storage together. Only after that evidence should Bake
attempt a typed proof that a source refresh is redundant. Persistent token ownership
must ultimately come from that proof and lifecycle metadata, not this trace heuristic.

## Reproduce

Run `audit_history_refresh.py TRACE_OR_MANIFEST OUTPUT.json` with Python 3.
Manifests are checked against each saved trace SHA256. Inputs used:

- `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/rhs-training-expanded-20261114/manifest.json`
- `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/rhs-validation-expanded-20261114/manifest.json`
- `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/observed-corpus-20261113/rhs-dot-product.json`

Committed reports: `history-refresh-train-results.json`,
`history-refresh-validation-results.json`, and `history-refresh-results.json`.

Validation: 10 unit tests across `test_history_refresh`,
`test_history_dependencies`, and `test_historical_sources`. These check causal
ordering, incomplete-state exclusion, preservation of alternatives, root separation,
and avoiding multiplication of repeated source alternatives. They are not native
runtime semantic acceptance tests.
