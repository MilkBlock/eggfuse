# Separate contextual channels: numerical acceptance unfinished

Two opt-in whole-Cell GPU models compare historical/adjacent source separation.
Both use eight channels, the same chronological source edges and full input
interface, fixed role projections and unchanged output encoding. `class-history-repeat`
places the same four role channels in both halves, normalized by sqrt(2).
`class-history-split` places adjacent sources in the first four channels and
historical sources in the last four. Route vector norms match; both models have
the same feature width and fixed random feature matrix. No GPU dynamic branch
or backpropagation is added. Historical source lifetime remains unproved.

Models use the same expanded training manifest and original validation manifest.
Boundary policies use the expanded validation manifest. No test-driven selection
is performed. Source depths and edges are unchanged from broad history; storage
and readout width increase compared with the four-channel baseline.

The repeat control passes numerical checks. Its validation-selected MSE policy
recovers 4,231/5,454 test partitions with 723 false and 1,947 missed Eq pairs;
partition selection recovers 4,329 with 839 false and 1,839 missed pairs. These
are standalone boundary diagnostics, not committed mutations or native acceptance.

The split model passes whole-token numeric checks, but boundary selection aborts
in validation: all scores are finite and within the numeric tolerance, maximum
absolute CPU/GPU difference 8.682697781647875e-6, yet **two classifications cross
the fixed 0.5 threshold**. The stricter threshold-agreement gate remains intact.
No split-model test result is reported, and no superiority claim is justified.
`context-split-validation-failure.txt` retains the exact failure. The next step
is to identify the near-threshold queries and define an audited uncertainty path,
not silently widen tolerance or count the incomplete run as a pass.

Reproduce training using `multi_entry_ridge.py` with `--channels 8` and each of
`--encoding class-history-repeat` / `--encoding class-history-split`, keeping the
expanded training/original validation/test paths from the historical experiment.
Run `select_eq_readout.py` with each resulting model and the expanded validation
manifest. Use fresh output stems matching each mode. The three successful JSON
reports retain provenance; binary weights and raw diagnostics stay on the SSD.
The route test verifies disjoint channels, preservation of role vectors and
matched norms. Focused route, history, replay and boundary tests pass (26 tests).
The generic readout error now includes numeric metrics so future failures can
be diagnosed without weakening acceptance.

## Threshold disagreement located

The diagnostic now retains exact query locations and compares original CPU
scores, GPU scores, and CPU float64 accumulation after rounding both operands
to float32. Both disagreements occur in validation case `000-ackermann`, Run 71,
rule 51, slots (0,2), bindings 81 and 82, candidate alpha 1.0:

- GPU: 0.500000536441803
- Original CPU: 0.49999964696746546
- CPU with f32-rounded operands and f64 accumulation: 0.4999995699495261

Rounding inputs alone does not reproduce the flip; accumulation differences
also matter at this margin. These scores are model outputs, not certificates of
true equality. No test evaluation or acceptance bypass was added. The gate still
rejects the run. A future uncertainty path must count these queries as requiring
CPU semantic audit, or a selection policy must explicitly disqualify numerically
inconsistent candidates using validation only. Neither is implemented here.
`context-threshold-diagnosis.txt` records the failure and source locations.
Thirteen focused tests pass, including mapping learned quotient-query indices
back to the original Run/rule/slot pair without confusing static pairs.

## Validation eligibility, without relaxing numerical acceptance

The opt-in `--reject-unstable-candidates` policy now audits every candidate on
all validation workloads and excludes any candidate with a numeric or threshold
disagreement. It does not replace GPU scores with CPU values, alter threshold
0.5, discard query rows or use test results to choose candidates. If none remain,
selection fails. Default behavior remains fail-fast. Test evaluation retains the
strict gate for all selected candidates and cannot reselect after test failure.
Per-candidate numeric checks remain in the report, including rejected candidates.

In the split experiment only alpha 1 fails validation; 0.1, 10 and 100 remain.
MSE and false-merge policies select 100, partition policy selects 10. Test scores
pass tolerance and have zero threshold disagreements:

| Policy | Alpha | Exact / 5,454 | False Eq pairs | Missed Eq pairs |
|---|---:|---:|---:|---:|
| MSE / false merge | 100 | 4,273 | 383 | 1,982 |
| Partition | 10 | 4,369 | 508 | 1,816 |

Against the same-width repeat control at the same alpha 100, this improves
4,231 exact partitions / 723 false pairs / 1,947 misses to 4,273 / 383 / 1,982.
It trades 35 additional misses for fewer false merges and more complete exact
partitions. Comparing partition-selected configurations is not a fixed-alpha
ablation (repeat selects 0.1, split selects 10).

The simpler four-channel interface-only model at alpha 100 still achieves
4,288 / 379 / 2,038. Thus separating contexts helps relative to mixing the same
history, but does not establish that broad historical expansion is worthwhile.
It retains the larger history edge set, deeper schedule and eight-channel model
costs. No runtime takeover or union authorization follows from numerical agreement.

Reproduce the split selection command with fresh `context-eligible*` outputs and
`--reject-unstable-candidates`. `context-eligible-results.json` retains provenance,
per-workload candidate checks and every selected policy. Fourteen focused tests
pass, including mandatory rejection of unstable candidates and failure when all
candidates are ineligible. This implements candidate eligibility only; per-query
runtime uncertainty/correction remains future work.
