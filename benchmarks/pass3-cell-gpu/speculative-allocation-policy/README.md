# Train the model to forecast physical Cell demand for a complete Run or page

The output is one nonnegative count for each active source rule/template. Run mode computes the vector before the first source search. Page mode also sees how many parent tokens the current neural page actually sealed, before validation. The shared head receives a constant, log counts of previous offers, winners and fresh primary Cells at this ruleset/rule, the previous fresh-to-offer ratio, log numbers of LHS atoms and template instructions, and the log current page size (zero at Run entry). Training labels are the actual later fresh root allocations. A binding that verifies or commits without creating a fresh primary Cell contributes no allocation label. Frozen predictions determine storage capacity only. Exact source validation and the root recipe still determine whether any physical record becomes visible.

PyTorch fits eight binary64 coefficients. The log-mean model uses regularized least squares. Two additional heads optimize symmetric or 80th-percentile pinball loss on physical counts. They share the initial log-space regression. Each root budget is predicted in log space and rounded to the nearest nonnegative count. At Run entry an 8,192-slot global budget is divided by largest remainder with stable source-order ties. Page budgets debit the remaining Run allocation as pages arrive. Capture includes 43,618 donor fresh primary roots across sum-bits, dot-product and Jacobi. No held-out payoff is used to select weights. The serving predictor is evaluated by Rust; Python supplies its serialized learned coefficients.

The controls reserve only record capacity, create full private records in a rule-specific pool, or bind those records to issued serials and authenticate their parent page. Private Cell records have a real template, epoch and fact buffer. Publication moves the initialized backing at its original source point. Unused records are dropped. Capacity-only reservations do not count as physically preconstructed Cells. Counts and archived heap estimates are separate from OS RSS. Pure physical underforecast falls back to the original source allocation and never fills missing neural matches. These standalone timing arms retain the original rule-local issuance. The [whole-Run integration](../wave-cell-allocation/README.md) measures the same forecasts when every proposal in the Run is sealed in advance.

| Source / allocation | Granted | Used | Unused | Real fresh roots | Peak private slots | Resident inference ms |
|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient / run-capacity | 97,293 | 59,752 | 37,541 | 96,535 | 3,719 | 648.81 |
| conjugate-gradient / run-pool | 97,293 | 59,752 | 37,541 | 96,535 | 3,719 | 665.08 |
| conjugate-gradient / run-named | 97,293 | 36,907 | 60,386 | 96,535 | 3,719 | 689.51 |
| conjugate-gradient / page-named | 145,209 | 66,034 | 79,175 | 96,535 | 4,571 | 665.52 |
| conjugate-gradient / run-tight | 54,519 | 17,249 | 37,270 | 96,535 | 256 | 685.84 |
| conjugate-gradient / run-previous | 96,439 | 37,266 | 59,173 | 96,535 | 4,035 | 663.09 |
| conjugate-gradient / run-balanced | 49,598 | 19,679 | 29,919 | 96,535 | 1,752 | 654.24 |
| 3mm / run-capacity | 232,796 | 137,864 | 94,932 | 228,095 | 8,192 | 1,904.00 |
| 3mm / run-pool | 232,796 | 137,864 | 94,932 | 228,095 | 8,192 | 1,933.10 |
| 3mm / run-named | 232,796 | 78,955 | 153,841 | 228,095 | 8,192 | 1,973.46 |
| 3mm / page-named | 361,557 | 143,795 | 217,762 | 228,095 | 8,192 | 1,928.18 |
| 3mm / run-tight | 114,989 | 28,441 | 86,548 | 228,095 | 256 | 1,951.63 |
| 3mm / run-previous | 226,998 | 81,009 | 145,989 | 228,095 | 8,192 | 1,951.66 |
| 3mm / run-balanced | 118,190 | 40,344 | 77,846 | 228,095 | 3,790 | 1,933.55 |

All trials used four paired measurements after warmup, seed 1703. Whole-program medians without speculation were 644.13 ms on CG and 1,818.79 ms on 3mm in this matrix. Identical per-Run RHS, effective writes, union, Spine, graph, signed winners and physical Cell IDs were required. [Training observations](donors.json) · [Weights](policy.json) · [Deployment evidence](results.json)

```sh
d=benchmarks/pass3-cell-gpu/speculative-allocation-policy
python benchmarks/pass3-cell-gpu/speculative-cell-batches/build.py "$EXP/private-cells"
python "$d/learn.py" "$EXP" "$EXP/private-cells/session" "$EXP/private-training"
python "$d/study.py" "$EXP" "$EXP/private-cells/session" "$EXP/private-training/policy.json" "$EXP/private-test"
python "$d/verify.py"
```
