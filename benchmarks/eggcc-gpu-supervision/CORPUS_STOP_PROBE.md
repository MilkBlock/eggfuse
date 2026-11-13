# Repeated Cell completion and learned stopping

This tests a necessary condition for GPU saturation: applying the same fixed
binding to its already-completed local Cell must not keep generating information.
It is not a test of full successor discovery, every rule in a ruleset, source
stage order or global saturation.

## Probe

`corpus_repeat_probe.py` loads the saved corpus model. For all 850 distinct test
inputs, the exact conditional teacher first verifies that reapplying the same
rule/binding to its completed body adds no information. All 850 pass that local
idempotence check. Original boundary handles remain stable through the quotient.

There are two distinct device experiments:

* Oracle diagnostic: supply the true completed state once and ask the same request.
  Every positive emission is wrong under the local contract.
* Free recurrence: start from the original input and issue the same request for
  four rounds. Each round reads the previous predicted body and boundary channels.
  No intermediate CPU readback, teacher refill, forced stop or duplicate filter is
  applied. The final candidate is selected inside the same Metal function.

Request roles and wiring remain those of the original successful binding. Static
index arrays and dense weights implement the compiled port projection; runtime
state supplies the values. There is no GPU-side graph search. Tests verify that
the projection actually reads changed channels and equals the initial projection.

NumPy independently evaluates the learned recurrence. The probe retains fixed
absolute/relative tolerances of 0.002/0.004 and reports failures without loosening
them. Final GPU candidate selection is independently checked with f64 distances.
A numerical failure writes the report and exits 1; exit 0 alone does not establish
semantic correctness or saturation.

## The original corpus model fails the stopping requirement

The model that achieved 817/850 first-step strict successes falsely emits on
748/850 oracle-completed states. Free-run emissions by round are 778, 748, 656,
591. Only 154/850 finish both at the exact catalog target and stopped. Final body
RMSE reaches 188.84, including large initialization Cells.

The baseline also fails the numerical tolerance at one of 28,968,000 state
coordinates. There are no emission disagreements or f64 decoder disagreements,
but this remains a failed numerical check, not a passing run. Large state drift
makes recurrent numerical behavior more fragile; this does not identify all
semantic errors as floating-point errors.

The earlier principal negative example was *no request*. That is not equivalent
to *a valid request whose effects are already complete*.

## Completed-state controls, still without backpropagation

`corpus_cell_ridge.py --completion-controls` adds the latter examples for each
partition. The same rule/binding is checked against the exact completed body;
only a proven no-new-information result can become a negative label. The model
input uses that completed state, the original nonzero request/role code and the
attachment recomputed from its current channels. Its target is the same state
and no emission. No artificial completed bit or forced stopping rule is supplied.

Workload partitions remain intact. Test completed states are evaluation controls,
not training examples. Training remains a closed-form ridge solve, with the
regularizer selected on the validation partition including its completed-state
controls. This changes the validation objective; it is not a comparison at an
identical regularization hyperparameter. Selected alpha changes from 0.1 to 1.0.

| Metric, 850 test inputs | Previous model | Completed-state controls |
|---|---:|---:|
| First-step strict exact target and emission decision | 817 | 711 |
| Oracle-completed false emissions | 748 | 42 |
| Round 1 / 2 / 3 / 4 free emissions | 778 / 748 / 656 / 591 | 733 / 81 / 23 / 12 |
| Final exact catalog target | 271 | 732 |
| Exact target and stopped at round 4 | 154 | 724 |
| Initially novel but never emitted | 8 | 56 |
| Numerical recurrence check | fail (1 coordinate) | pass |

The new recurrence has no emission disagreements, no out-of-tolerance coordinates
and no f64 decoder disagreements. It still leaves 12 active final requests and
misses required completions. Its stronger stopping behavior comes with reduced
first-step accuracy. Neither model is a reliable GPU saturation runtime, and the
new option remains an experiment rather than replacing the prior model by fiat.

Counts include uncovered-family diagnostics as in the corpus experiment; they
are not ownership authorizations. Candidate catalogs still contain held-out
structures. Exact target selection plus local stopping does not prove physical
constructor identities, global novelty, visibility, cross-stage legality or
completion of other rules.

## Reproduction

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_cell_ridge.py MANIFEST FIT.json --completion-controls --model-output MODEL.npz
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST MODEL.npz PROBE.json --rounds 4
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_corpus_repeat_probe test_corpus_cell_ridge
```

Run the probe on the earlier saved model for the baseline; expect exit 1 for its
reported numerical failure. `corpus-stop-results.json` stores both probes and the
new fit. The generated model remains on the external SSD under
`models/corpus-ridge-stop-controls.npz`; metadata and artifact hashes are in the
fit result. There is no native executor change in this work.
