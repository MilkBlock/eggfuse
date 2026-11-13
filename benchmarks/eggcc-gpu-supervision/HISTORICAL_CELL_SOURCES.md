# Historical Cell context: ambiguity improves, accuracy and cost regress

This standalone GPU replay experiment fills inputs lacking adjacent-Run links
with earlier observed constructor-result tokens. It is opt-in through
`--encoding class-history`; the default is unchanged. It uses closed-form ridge,
no backpropagation, and no intermediate GPU token readback. CPU traces still
supply matches and routing. It is not autonomous execution or native acceptance.

## Observation policy and unproved obligations

For each typed input identity, retain all complete-state constructor observations
from the latest prior source Run that produced that identity. Only ports without
an adjacent-Run provider get historical candidates. Collect candidates before
adding results of the current Run, preventing same-Run/future leakage. Copies,
mutable sets/reads, scalar coincidences and incomplete producer states do not
supply history. All alternatives from the selected source Run remain; no unique
owner is inferred. An operation may have returned an existing constructor.

The source dictionary is CPU experiment preparation, not an added device hash
table. GPU execution uses the resulting fixed gather/matrix dataflow. Historical
identity observations **do not prove retirement, generation, lifetime, visibility
or ownership**. Changed endpoint roots are counted rather than interpreted as
proof. The result explicitly denies takeover authorization. Stale producer
state may help as context but is not a current fact certificate.

The test trace has 25,852 input Eq ports. Adjacent linking covers 5,675; history
finds candidates for 19,925 of the remaining 20,177. This adds 50,651 candidate
edges across 5,422 consumer instances, including 13,310 cross-ruleset ports.
The cache peaks at 2,697 identity groups and 3,414 retained provider records.
All 382 incomplete producer states are excluded. The model consumes zero CPU
boundary tokens. Current input-interface correlations are retained exactly as
in `class-interface`; output codes and model dimensions are unchanged.

## Controlled evaluation

Training and validation partitions, template/state deduplication, scalar inputs,
model widths and readout threshold remain unchanged. Model alpha is selected on
original euler validation; boundary policies use the five-workload validation
set, with no test selection. Both models select token alpha 0.1; both readout
experiments select alpha 100 for MSE/false-merge and 0.1 for partition accuracy.

| Policy | Context | Exact Eq partitions / 5,454 | False Eq pairs | Missed Eq pairs |
|---|---|---:|---:|---:|
| MSE / false merge | Adjacent + full interface | 4,288 | 379 | 2,038 |
| MSE / false merge | Historical | 4,248 | 693 | 1,919 |
| Partition | Adjacent + full interface | 4,415 | 883 | 1,828 |
| Partition | Historical | 4,396 | 864 | 1,776 |

All original test instances remain in scope; missing/no-comparison cases keep
existing treatment. Neither result authorizes unions. Exact f32 ambiguity falls
from 28 to 0 groups in training, 108 to 5 in validation, and 2 to 0 in test.
The minimum query-error lower bounds fall from 36/163/7 to 0/5/0 respectively.
These are within-case, within-template audits, not universal injectivity proofs.
Removing exact collisions does not guarantee that the learned function decodes
the resulting states well; the fixed-population correctness results demonstrate
that distinction. Additional context can also be stale or irrelevant.

## Costs and decision

Dependency depth grows from 31 to 91. Base edge coefficients grow from 1,805,952
to 8,289,280 floats and route coefficients from 56,436 to 259,040 (about 4.6x).
Whole-model preparation grows from 4.961 s to 7.807 s. Cold GPU replay including
plan/upload/compilation is 1.013 s versus the earlier 0.195 s diagnostic; CPU
replay is 1.007 s versus 0.196 s. These single diagnostic runs are not a robust
throughput benchmark, but clearly provide no evidence of a speedup. The later
information and readout audits run concurrently and are not timing comparisons.
CPU/GPU numerical checks pass. The related suite passes 109 tests.

Do not adopt this broad historical expansion as the runtime path. It establishes
that older observed Cell context distinguishes the known ambiguous examples,
but worsens complete-partition accuracy while increasing dependencies and data
movement. A next experiment should retain separate evidence for useful context,
prefer compiler-proven relevant producer roles, and avoid mixing all historical
observations into the same pool. It must account for lost matches, lifecycle
obligations and added storage rather than hide them behind candidate counts.

## Reproduction

Use the expanded training manifest, original validation manifest and dot-product
test in `multi_entry_ridge.py`, with `--channels 4 --encoding class-history` and
fresh `class-history.npz` / `class-history.json` outputs. Run the commands in
`TOKEN_INFORMATION.md` and `EQ_READOUT_SELECTION.md` against that model, using
`history-information` and `history-selection` output stems. Source-count audit:

```sh
python3 benchmarks/eggcc-gpu-supervision/historical_cell_sources.py \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/historical-sources.json"
```

Committed text reports are `class-history-results.json`,
`historical-sources-results.json`, `history-information-results.json` and
`history-selection-results.json`. Raw traces, weights and local error marks
remain on the external SSD. Four source tests check chronology, typed identity,
alternatives, exclusion of incomplete states, and avoiding duplicate adjacent
links. No native executor changes belong to this experiment.
