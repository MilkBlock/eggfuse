# Direct-consumption feature and training experiment

This is a standalone, observed-wiring Cell-token experiment, not autonomous
Eggcc execution or a native correctness/performance result. The 128-float token
transition model stays frozen. No backpropagation, new identity encoding,
ownership permission, query fact store or GPU data-dependent branch is added.

## Why this change

The prior frozen-model audit misread many *actual completed state* tokens, before
any recurrent error. The first port-interaction extension helped, but left 904
such partition errors. We test whether more of the existing continuous token
information can be decoded using the same template endpoint descriptors.

Let l and r be the two 64-float token halves, and s, d, p, q be the existing
endpoint sum, absolute difference, product and template descriptors. The new
256 columns are l*l*s, r*r*d, l*r*p and (l-r)*(l-r)*q. These preserve even-order
activation information conditioned on the query. They are fixed floating
products, followed by the existing dense random projection, tanh and fitted
ridge readout. Original columns and random projection weights are preserved.
Feature construction is tested in compiled Metal against NumPy.

The second controlled option adds training examples made by applying the frozen
token transition once to *correct training source tokens*. Each retains its
training-label Eq partition. Original state examples remain in the fit. This
addresses a concrete discrepancy: the previous decoder trained on actual-state
encodings but consumed predicted states. It does not alter the transition model,
inject target states into inference, or use validation/test labels for fitting.
These are in-training-distribution predictions, not an out-of-fold experiment.

Ridge alphas .1, 1, 10 and 100 are selected using the existing validation policy.
Test results do not choose alpha, threshold, features or the partition budget.
CPU/GPU numeric and threshold checks remain mandatory; the quadratics-only .1
candidate is excluded because it fails the validation numeric eligibility gate.

## Results

All experiments reuse the prior corpus, frozen transition model and split hashes,
recorded in the accompanying JSON reports. The held-out dot-product capture has
5,454 comparable partitions. A partition is correct only when every pair agrees.
This test workload has been inspected in earlier research iterations; it is not
a fresh blind evaluation. Broader claims need new untouched workloads.

| Decoder | Validation macro exact | Test exact | False equal pairs | Missed equal pairs |
|---|---:|---:|---:|---:|
| Prior port interactions | 82.87% | 4,612 | 991 | 1,360 |
| Quadratic columns | 88.59% | 4,712 | 1,131 | 1,091 |
| Quadratics + direct-input training | 89.40% | 4,801 | 1,085 | 1,040 |

The final row selects alpha .1; quadratics alone selects 1. This improves complete
partition prediction but **does not dominate false-merge risk**. It remains
opt-in and cannot authorize union or ownership transfer.

The same selected readout is then audited with three kinds of tokens:

| Token input | Prior interactions exact | Quadratics exact | With direct training exact |
|---|---:|---:|---:|
| Actual completed state | 4,550 | 4,781 | 4,841 |
| Completion using correct sources | 4,580 | 4,700 | 4,794 |
| Recurrent completion | 4,612 | 4,712 | 4,801 |

This supports improving direct consumption rather than only shortening chains.
It does not prove lost information has been recovered: errors may cancel, and
the final model's actual-state false equal pairs rise to 1,541. All input modes
and error counts remain in the reports rather than reporting only the best one.

The unchanged bounded legal-partition projection applied to the final model gives
4,827 exact partitions, 1,038 false equal pairs and 1,037 missed pairs. Its covered
regions have no nontransitive output, but 435 of 5,148 unmarked comparable cases
are still wrong (8.45%). There are 306 explicit uncovered marks. The CPU checks
all comparable cases, not just marked ones. The ~76.6k checks/s recorded here
measure saved-label comparison only, not native proof replay.

## Costs and limits

Token storage and transition weights are unchanged. Raw readout width grows
768 -> 1,024; a selected readout plus random projection grows 197,633 -> 263,425
float weights (~33.3%). Each pair requires 256 extra feature floats, additional
products and 65,536 additional random-projection multiply-adds. Training gains
another example per retained class-pair query with direct training; inference
does not run both paths. Reported wall times include preparation/compilation and
are not GPU speedup claims. In the workload audit, features are still materialized
on CPU before GPU readout; the separate compiled feature test does not establish
end-to-end GPU feature throughput.

No new sources were captured. This tests extracting more useful features from
the current Cell token and better matching the direct-input distribution. Real
runtime matching retains fewer alternative witnesses than this observed corpus;
that distribution gap, generation-safe ownership scheduling, full ruleset
coverage and closed-loop CPU audit remain outstanding.

Tracked Bake branch remains 89714c74: eager joins that retain old source state
were rejected. Nothing here counts a prediction or extra feature as reclaimed
source storage or a committed mutation.

## Reproduce

Run select_eq_readout.py with the frozen class-history-neighborhood-input model
and report, rhs-training-expanded-20261114/manifest.json,
rhs-validation-expanded-20261114/manifest.json and held-out rhs-dot-product.json,
using --port-quadratics --reject-unstable-candidates. Add --direct-training for
the second fit. Then run audit_direct_source_readout.py and
audit_partition_readout.py against each frozen selected readout. All six reports
are committed; NPZ models and detailed marks remain under
/Volumes/Extreme SSD/eggfuse-artifacts/21ee. Nineteen related tests pass.
