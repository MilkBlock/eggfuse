# Bake-local numerical hints for learned Cell stopping

This is a standalone Metal/MLX prototype on the existing 850 distinct real eggcc
held-out local inputs. It does not change the native executor or establish
ruleset saturation, ownership transfer, visibility or committed mutations.

## Change

Freeze the original positional-role model's random projection, full state
readout and candidate dictionary. Fit only a separate emission head by closed-form
ridge, with initial, proven completed and no-request controls. No backpropagation.
Train/validation/test workload partitions remain unchanged; alpha is selected on
validation (1.0 in both head-only variants).

Bake supplies static masks for reserved output ports and direct union operand
pairs. Eight numerical columns describe output count, output-channel energy/RMS,
bounded energy, direct union count and current operand-channel difference energy.
These are computed from the current GPU state. Copy aliases are followed; union
operands requiring fresh effect results are deliberately excluded. No new reverse
consumer lists, runtime graph lookup or intermediate CPU correction is introduced.

Output positions come from the existing supported finite completion layout. This
is not a general compiler for unknown dynamic output interfaces. A nonzero vector
is not an existence proof, and equal vectors do not prove Eq. The features only
inform the learned emission score; they never independently authorize a skip or
retirement. Static wiring is prepared on the CPU before the experiment.

## Paired evidence

Both variants preserve every original model array exactly (`numpy.array_equal`
for `w`, `coef`, `prototypes`, `prototype_families`). Only `stop_coef` is added.
The no-hints control trains the same head with the eight extra columns zeroed.
The probe still computes those columns, whose fitted coefficients are zero; this
is an accuracy ablation, not a timing comparison.

| Test metric | Head only, no hints | Head plus Bake hints |
|---|---:|---:|
| Initial required emissions missed / 779 | 56 | 11 |
| Initial false emissions / 71 no-op inputs | 10 | 0 |
| False emissions on true completed states / 850 | 42 | 2 |
| Free emissions, rounds 1–4 | 733 / 35 / 5 / 0 | 768 / 7 / 7 / 7 |
| Final exact catalog target / 850 | 765 | 818 |
| Final exact catalog target **and stopped** / 850 | 765 | 815 |
| Final body RMSE | 8.3050 | 86.1956 |
| Fixed-tolerance NumPy recurrence audit | pass | pass |
| f64 final decoder disagreements | 0 | 0 |

The hints improve local completion/stop decisions, but seven requests still emit
repeatedly and numerical state drift becomes worse. The nearest-candidate metric
can hide large continuous error; 815/850 is not proof of stable latent execution.
The seven active requests account for 99.9998% of total body squared error;
median per-input RMSE is 0.06466 while the maximum is 2505.86. Three active
requests still decode to the exact catalog target despite this drift.
Freezing state coefficients does not preserve the earlier first-step strict score:
changing emission decisions also changes whether that state update executes.

The four recurrent rounds run on the GPU without intermediate CPU readback or
teacher refill. The true-completed-state diagnostic is separate. This repeats
one fixed proven binding, not changing successor requests. The candidate catalog
contains held-out structures, and counts include uncovered-family diagnostics.
The globally padded 34,080-float state remains inefficient. No throughput or native
speedup claim follows from this experiment.

## Reproduce

With the corpus and positional-role model from `CORPUS_CELL_RIDGE.md`:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/fit_bake_stop_head.py MANIFEST BASE.npz HINTS.npz HINTS_FIT.json
$PYTHON benchmarks/eggcc-gpu-supervision/fit_bake_stop_head.py MANIFEST BASE.npz CONTROL.npz CONTROL_FIT.json --no-bake-hints
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST HINTS.npz HINTS_PROBE.json
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST CONTROL.npz CONTROL_PROBE.json
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_bake_stop_features test_corpus_repeat_probe test_corpus_cell_ridge test_observed_corpus test_observed_cell_targets test_boundary_cell_ridge test_chain_completion_audit
```

`bake-stop-results.json` preserves the fits, probes and immutable-array checks.
Large model artifacts remain on the external SSD. The probe additionally records
identities and error magnitudes for final active requests, to guide the next
training/feature investigation without silently adding a forced stop.

## Why the seven requests remain active

`audit_stop_failures.py` reconstructs their original input, true completed state
and one predicted update. It checks model/manifest fingerprints against the GPU
probe and only diagnoses held-out failures; it does not add them to training.

All seven have oracle-completed emission scores below 0.5, but scores above 0.5
on their own first prediction. Three conservative template families have no
training inputs. The four covered families have 2, 2, 2 and 6 distinct training
inputs; one failing input exactly matches a training input. Thus this failure is
not explained solely by previously unseen templates or insufficient stop labels
on true completed states.

Two failures are large initialization bodies (118 and 238 construct effects).
Four are direct union/copy effects: their true completed operand difference energy
is zero, but the predicted channels retain difference energy between 0.0067 and
0.0761. The remaining failure has construct/set/copy effects. These observations
locate a distribution gap; they do not isolate which numerical feature causes
each decision.

The next training experiment should use predictions from **training inputs only**
as inputs to a correction target, while preserving independent workload holdouts.
It must not simply label every predicted state as stopped: an inaccurate state
can still require correction. Evaluate state correction and learned emission
separately, and retain free GPU recurrence without teacher refill. This remains
necessary groundwork for changing successor requests, not a substitute for it.

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_stop_failures.py MANIFEST HINTS.npz HINTS_PROBE.json FAILURE_AUDIT.json
```

`stop-failure-audit-results.json` stores compact evidence with effect counts; the
full audit on the external SSD retains the corresponding effect instructions.
