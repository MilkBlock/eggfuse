# Validation expansion exposes conflicting readout objectives

This is a **standalone Eq boundary-readout experiment**, not a GPU egraph
implementation or native semantic acceptance. The expanded-training whole-Cell
model remains frozen (`class-balanced-expanded.npz`); predicted tokens still
feed later Cells on GPU. No backpropagation, test-driven threshold search or
new token-model fitting occurs here.

## Validation inputs and provenance

The original validation partition is expanded from euler to its five smallest
complete workloads below 8,000 observed bindings: euler (3,742 applications),
ackermann (4,589), gcd (5,473), lcm (6,010), and newton (7,572). All selected
sources satisfy the collector's saved CPU reference-time limit of one second.
There are 27,386 actual RHS applications and 1,795 cross-ruleset observed
consumer connections. All five captures pass per-Run graph, final graph and Run
control-count equality against CPU reference execution. These are observations,
not causal ownership proofs or GPU mutations.

The existing euler capture is hash-checked and reused; the same capture-binary
fingerprint is required. No workload changes partition. Training stays at ten
workloads and 1,153 unique `(template,state)` examples; validation expands from
364 to 1,361 such examples. The test remains dot-product. Source and artifact
fingerprints are retained in the reports.

## Fixed candidates, three declared selection policies

`select_eq_readout.py` fits the same four ridge candidates (alpha 0.1, 1, 10,
100), using train-only centering/scaling and oracle training tokens. The existing
ridge formula is reproduced by a regression test. Every candidate uses the same
static-class pair layout and fixed threshold 0.5. It selects:

- `mse`: minimum query MSE on deduplicated **oracle validation tokens**, matching
  the previous criterion.
- `partition`: highest complete-partition accuracy on **predicted validation
  tokens**, averaged equally across workloads; ties prefer lower false-pair rate.
- `false_merge`: lowest false-pair rate on predicted validation tokens, averaged
  equally across workloads; ties prefer higher partition accuracy.

The second and third policies change both the evaluation input (predicted versus
oracle) and selection metric. This experiment reports those policies explicitly;
it does not isolate only a loss-function change. False-pair rate counts errors
against all audited slot pairs, not just proposed positives. The fitting helper
never sees validation data. Policy choices are finalized before test labels are
loaded. All selected policies are reported; the test does not pick a winner.

## Results on the unchanged 5,454 comparable test instances

| Validation set | Policy | Alpha | Exact partitions | False Eq pairs | Missed Eq pairs |
|---|---|---:|---:|---:|---:|
| Euler | MSE | 1 | 4,368 | 888 | 1,874 |
| Euler | Partition | 10 | 4,370 | 935 | 1,816 |
| Euler | False merge | 100 | 4,265 | 735 | 1,989 |
| Five workloads | MSE | 100 | 4,265 | 735 | 1,989 |
| Five workloads | Partition | 0.1 | 4,385 | 1,014 | 1,850 |
| Five workloads | False merge | 100 | 4,265 | 735 | 1,989 |

The single-workload MSE control reproduces the previous 4,368 result. More
validation coverage changes the chosen regularization substantially, but does
not yield an option that improves all metrics. The partition policy after
expansion marks 1,069/5,454 instances (19.60%); MSE/false-merge mark 1,189/5,454
(21.80%). These are Eq mismatch fractions only: scalar/external identity and
lifecycle correctness still require checks. Ninety-nine complete captures have
no comparable Eq pair; 382 incomplete captures remain outside this audit.

The failure mode is visible **in validation**, not merely in test: alpha 0.1
produces 4,117 false Eq pairs on ackermann, versus 54 at alpha 100. Yet ackermann
has 3,696 exact partitions at alpha 0.1 versus 3,583 at alpha 100. Counting exact
instances gives one failure to both a mildly wrong instance and a catastrophically
wrong large instance. Consequently even a task-shaped metric such as full
partition accuracy cannot be the sole acceptance/selection objective.

Expanded-validation mean oracle MSE decreases from 0.03320 at alpha 0.1 to
0.02458 at alpha 100. Mean predicted partition accuracy moves the opposite way,
from 78.99% to 76.60%. The evidence establishes a real tradeoff; it does not
justify choosing a threshold or test-winning combination post hoc. No candidate
authorizes union. Transitive closure still adds false equalities (1,131 total
for the selected partition policy; 1,175 for MSE/false-merge).

## Accounting and limits

The expanded run fits four candidates in 0.123 s. Test CPU feature construction
is 0.306 s, GPU readout plus transfers for the two distinct selected candidates
is 0.034 s, and CPU audits/marks for three policies take 0.374 s. These exclude
corpus preparation and token replay; they are component diagnostics, not total
runtime or speedup claims. Matrix readout is batched; no dynamic GPU control flow
is introduced. CPU/GPU comparisons pass with zero threshold disagreements on
all five validation workloads and test.

There are 3,447 JSONL marks across the three expanded-validation policies; MSE
and false-merge select the same candidate and thus intentionally duplicate their
per-policy marks. Do not interpret their sum as unique bad test instances. Each
mark identifies policy, Run, binding, rule and wrong slot pairs, and explicitly
sets `union_authorized: false`. The related suite passes 102 tests.

This result rules out treating broader validation or another single scalar
selection metric as a sufficient fix. The next useful diagnosis is whether
incorrect relations are distinguishable in the current floating features,
including oracle-token features, before adding more fitting machinery.

## Reproduce

```sh
python3 benchmarks/eggcc-gpu-supervision/collect_rhs_training.py \
  "$ROOT/observed-corpus-20261113/manifest.json" \
  target/debug/examples/capture_rhs_results \
  "$ROOT/rhs-validation-expanded-20261114" --split validation \
  --max-cases 5 --max-bindings 8000 \
  --reuse "$ROOT/rhs-validation-20261114/manifest.json"

$PYTHON benchmarks/eggcc-gpu-supervision/select_eq_readout.py \
  "$ROOT/rhs-training-expanded-20261114/manifest.json" \
  "$ROOT/rhs-validation-expanded-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-balanced-expanded.npz" "$ROOT/class-balanced-expanded.json" \
  "$ROOT/eq-selection-expanded.npz" "$ROOT/eq-selection-expanded.json" \
  --marks "$ROOT/eq-selection-expanded-marks.jsonl"
```

Use the original validation manifest and fresh `eq-selection-original*` output
paths for the control. Reports are `rhs-validation-expanded-results.json`,
`eq-selection-original-results.json`, and `eq-selection-expanded-results.json`;
raw captures, weights and marks remain on the external SSD.
