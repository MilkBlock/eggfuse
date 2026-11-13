# Real multistage workload holdout

The preceding experiment trained only on the first 60% of one source schedule.
It contained no positive `context` examples. This experiment addresses that
coverage gap using complete source executions with different initial programs.
It does not mix adjacent bindings from one execution into train and test.

Before collecting labels, the corpus was fixed in `collect_multitrace.py`:

| Role | Frozen eggcc pass-3 input | Source Runs | Matched bindings |
|---|---|---:|---:|
| Train | sum-bits | 882 | 6,532 |
| Train | loopfact | 398 | 1,239 |
| Validation | gcd | 788 | 5,473 |
| Test | dot-product | 954 | 5,935 |

The captures come from the existing eggcc suite, whose provenance is documented
in `../eggcc-suite/README.md`. The direct Cell compiler is used without the old
marker/Bake catalog. Consequently sum-bits has fewer Runs/observed pairs than the
previous catalog-equipped trace. It is not an ablation on the same execution
trace. Every capture is checked against an ordinary execution of its compiled
program; native auditing also checks source Run controls and the final graph.
This is not a native egglog semantic certification.

## Frozen model and results

The alias-normalized role encoder, fixed random seed and 513-dimensional ridge
features are unchanged from the preceding experiment. No backpropagation is
used. Fit uses sum-bits and loopfact only. Class weight, regularization and
threshold are chosen on gcd validation F0.5. Selected values are 1, 1000 and 0.3.
Dot-product labels do not select those values. This round inspected dot-product
only after the architecture and fit procedure were fixed; future tuning must
use a new holdout instead of treating this inspected test as fresh again.

| Workload | Candidate pairs | Actual new Eq | TP | FP | FN | Precision | Recall |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits (train) | 16,585 | 518 | 472 | 134 | 46 | 77.89% | 91.12% |
| loopfact (train) | 2,435 | 42 | 41 | 0 | 1 | 100% | 97.62% |
| gcd (validation) | 12,620 | 343 | 285 | 48 | 58 | 85.59% | 83.09% |
| dot-product (test) | 14,356 | 159 | 144 | 82 | 15 | 63.72% | 90.57% |

All predictions come from actual Metal floating matrix/nonlinear execution.
The native CPU auditor confirms every outcome against its executing Graph and
agrees with these counts, including all errors. Therefore all four proposal
streams correctly fail the exact acceptance check. No GPU union is committed.
The test's 90.57% recall is **not** 90% overall completion correctness.

Only 212/14,356 test feature rows are byte-identical to a training feature row;
187/12,620 validation rows are identical. Sharing compiler roles across workloads
is deliberate. Root/message routing is isolated by source Run and workload;
there is no cross-workload runtime message propagation. Tests check this
isolation even when numeric port IDs are identical, and verify that changing
another workload's values/labels cannot change the target's encoded features.

The test has 40 false positives in `interval-analysis`, 17 in `type-analysis`,
and 25 elsewhere. All 15 misses are in `terms-helpers-helpers`. These are
post-evaluation diagnostics, not exceptions used to change the model or mask
outputs. A single held-out program does not establish broad generalization.

## CPU supervision and scope

The corpus has 19,179 matched Cells, 81,020 Eq port occurrences and 45,996
candidate pairs. CPU still provides exact matched inputs and pre-Run routing.
Labels are post-Run input-port Eq deltas, not saturation of arbitrary unseen
subgraphs. Scalar computation, new-node outputs and mutable effects are not
covered by this readout. The full intended GPU runtime remains incomplete.

On this single dev-build audit run, dot-product CPU execution with capture took
151.96 ms; capture/frame construction accounted for 10.55 ms of that time;
proposal comparison took an additional 3.12 ms. Raw per-workload timings are in
`multitrace-audit-results.json`. GPU cold execution and CPU dataset preparation
are recorded separately in `multitrace-ridge-results.json`. These are diagnostic
timings, not an end-to-end acceleration result. No CPU execution work is removed.

## Reproduction

`PYTHON` must have NumPy and Apple MLX. `CAPTURE` is the existing frozen eggcc
capture directory; `OUT` is a new experiment output directory. Generated full
traces, program artifacts and proposal streams remain untracked.

```sh
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false cargo build --locked -p eggfuse-cell-compiler --example emit_cell_source --example gpu_supervision_live_trace --example native_proof_audit
python3 benchmarks/eggcc-gpu-supervision/collect_multitrace.py CAPTURE OUT
$PYTHON benchmarks/eggcc-gpu-supervision/multitrace_ridge.py OUT/manifest.json OUT/results.json --proposals OUT/proposals
python3 benchmarks/eggcc-gpu-supervision/audit_multitrace.py OUT/manifest.json OUT/results.json OUT/proposals OUT/audit-summary.json
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p 'test_*ridge.py'
```

The audit driver requires agreement with independently computed native counts;
its success means the reported model errors are verified, not that predictions
passed. Source/program/trace hashes and the frozen split are stored in
`multitrace-manifest.json`. Recollection regenerates machine-local trace paths.
