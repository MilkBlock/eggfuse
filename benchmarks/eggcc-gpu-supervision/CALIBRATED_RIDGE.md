# Improving Eq precision without backpropagation

This experiment keeps the real full sum-bits matched Cell inputs and the existing
chronological Run split (60% train, 20% validation, 20% test). It uses Metal dense
floating messages, tanh and a learned ridge readout. CPU remains the verifier.
No rule effects are committed by the GPU.

The previous model weighted positive examples 20 times and selected for F2.
That encouraged excessive Eq proposals. The new search selects class weight,
regularization and threshold on validation F0.5. Training-only standardization
is folded into the ridge readout, adding no inference normalization pass.

The structural variant represents slots using shared operation/argument roles,
not random rule-ID identities. Shared-root message sums are degree-normalized.
Pair features include sums, absolute differences and products of floating endpoint
states, followed by a fixed dense nonlinear projection. Copy operations are
resolved as template aliases; thus copied and direct union inputs share semantic
roles. This is static compiler information, not a runtime equality oracle.
Both message projections and nonlinear projections remain fixed; ridge uses a
closed-form solve, with no backpropagation.

## Measured correctness

Counts are TP / FP / FN. All rows use actual Metal inference. The selected alias
variant also passed through the native auditor, which independently read the
executing Graph and agreed with every saved observer outcome.

| Representation / selection | Train | Validation | Test diagnostic | All |
|---|---:|---:|---:|---:|
| Previous context + F2 | 197 / 3532 / 0 | 201 / 1754 / 114 | 6 / 617 / 0 | 404 / 5903 / 114 |
| Same features, recalibrated | 176 / 75 / 21 | 78 / 140 / 237 | 6 / 29 / 0 | 260 / 244 / 258 |
| Typed roles + pair interactions | 178 / 0 / 19 | 15 / 0 / 300 | 6 / 0 / 0 | 199 / 0 / 319 |
| Alias-normalized roles + pair interactions | 195 / 14 / 2 | 55 / 1 / 260 | 6 / 10 / 0 | 256 / 25 / 262 |

The alias variant is selected by validation F0.5, not by test results. Validation
precision is 98.21%, but recall is only 17.46%. Test precision is 37.5%, despite
recalling all six positives. **This is not 90% completion accuracy**. Total
accuracy would be misleading because most candidate pairs stay unequal.

The test partition has been inspected during development, including earlier
experiments. It is now a diagnostic, not a fresh independent holdout. No claim of
workload generalization follows from its six positives or the zero-FP variant.
A new workload/family holdout is required before claiming generalization.

A coverage diagnosis explains much of the gap: 298/315 validation positives
belong to rules with no positive training example. Of these, 297 are `context`
relations. Changing the split to scatter neighboring bindings across train and
test would conceal this weakness. The next step is genuinely different Cell
entries/traces that cover full ruleset stages, retaining a fresh holdout.

## Reproduction and costs

```sh
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p 'test_*ridge.py'
$PYTHON benchmarks/eggcc-gpu-supervision/calibrated_ridge.py TRACE RESULTS --proposals PROPOSALS
target/debug/examples/native_proof_audit PROGRAM AUDIT_RESULTS PROPOSALS
python3 benchmarks/eggcc-gpu-supervision/native_audit_report.py TRACE AUDIT_RESULTS SUMMARY
```

Native auditing exits 1 for these imperfect predictions; this is the expected
rejection, not a passing semantic acceptance. Detailed results are recorded in
`calibrated-ridge-results.json` and `calibrated-audit-results.json`.
Timings are cold experiment diagnostics only. CPU prepares matched inputs and
exact pre-Run routing, GPU performs floating inference, CPU compares all candidate
pairs. This change removes no CPU query, RHS or repair work. Fixed compiler
layouts are shared; there is no added per-producer consumer dependency list.
