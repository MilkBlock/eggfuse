# Whole-Cell targets from real multi-entry inputs

The earlier completion experiments enumerated symbolic template transitions. They
did not establish coverage of a template's different actual input Eq partitions
and scalars. `observed_cell_targets.py` uses the saved full sum-bits native Cell
trace as the input source instead. It does not rerun benchmarks or modify the
executor. `boundary_cell_ridge.py` accepts its explicit bindings and runs the same
learned GPU recurrence, including newly generated boundary ports.

## Input and proof contract

Only pre-Run audited Eq roots and observed scalar values enter inputs. Physical
roots are renamed to local typed equivalence classes. Different actual partitions
remain different; renaming actual IDs does not change the sample. i64, bool and
String values are preserved as typed literal symbols. Unsupported scalar sorts,
mutable/primitive premises and unsupported effects are marked rather than
silently interpreted. Scalar arithmetic is not newly implemented here.

Each complete constructor query is instantiated from an actual successful
binding. The existing bounded constructor/union teacher derives a local completion
conditional on those facts. These labels are **not** the complete observed runtime
constructor graph. In particular, a constructor absent from this local source may
already exist elsewhere: local novelty does not establish global novelty, actual
allocation, global saturation, or committed mutations. The CPU still performed
all original matching and execution. Future GPU discovery of these inputs is
not implemented by this collector.

Post-Run Eq identities enter only an independent check: every newly derived
input-port equality must hold after native execution. The check does not require
local completion to derive all equalities introduced elsewhere in the Run. It
cannot certify output constructors, visibility or ownership. Changing the after
labels leaves model inputs and teacher targets unchanged; a test verifies this.

Deduplication is by rule and normalized actual input. Observation counts preserve
frequency, but training weights each unique input state equally. All states for
a rule stay together under the existing modulo-five family split. This remains
one inspected workload, not a fresh workload holdout.

## Captured coverage and GPU results

From 6,532 successful input bindings, 4,591 are supported, yielding 311 unique
states for 148 rules. Seventy-three rules have multiple states, at most 12 each.
Marked bindings: 1,016 non-constructor premises, 638 unsupported Unit input cases,
212 mutable set effects and 75 subsume effects. The sum equals total observed
bindings. The equality check covers 166 derived input pairs, with zero violations;
this is the limited contract above, not final-state semantic acceptance.

The test partition has 156 requests including identity controls and 76 locally
novel targets. The model emits 70 proposals, with one false emission and seven
misses. These are not correct-completion counts. Body RMSE is 0.15331 versus
0.16574 for keeping the source unchanged. New-output channel RMSE is 0.13798
versus 0.15389 for keeping those channels zero.

Twenty-one chains from five test rule families use newly generated first-step
ports in the second step. Twenty emit at each step. Final body RMSE is 0.33244.
Intermediate body and boundary predictions remain on Metal without CPU readback
or teacher replacement. This confirms numerical execution of the generated-state
path, not reliable semantic completion. These samples differ from previous
catalog experiments, so their metrics are not paired speed/accuracy comparisons.

The representation still has 1,728 floats per Cell and expensive dense request
projections. No speedup claim is made. The next requirement remains an expressive,
efficient recurrent representation that distinguishes actual input/result states;
these results do not justify ownership retirement or deployment as the runtime.

## Reproduction

```sh
python3 benchmarks/eggcc-gpu-supervision/observed_cell_targets.py PROGRAM TRACE TARGETS
$PYTHON benchmarks/eggcc-gpu-supervision/boundary_cell_ridge.py PROGRAM TARGETS RESULTS --generated-boundaries
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_observed_cell_targets.py
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_boundary_cell_ridge.py
```

`TRACE` is the saved `gpu_supervision_live_trace --relations` capture with its
program fingerprint and native reference/control checks. The committed
`observed-boundary-results.json` records capture counts, fingerprints and model
results; large reproducible input and target data remain under ignored `out/`.
This is a standalone prototype, not the native sum-bits acceptance validator.

## Second-step diagnosis and continuation training

A separate oracle-input diagnostic supplies the *correct* first completion to
second-step inference. This diagnostic is intentionally distinct from the
free-running GPU recurrence: it does not replace or repair the actual predicted
state. It helps separate second-transition difficulty from error introduced by
using the first prediction. It is not a runtime solution.

On the same 21 chains, baseline oracle-input body RMSE is 0.18093, versus 0.33244
when consuming the predicted first state. Keeping the correct first state unchanged
has RMSE 0.19622. Both transition generalization and recurrence errors remain.
Of the 21 second requests, 13 use rule types represented in base training; there
are four distinct second-rule types overall. These counts do not establish that
their completed-state input distributions appeared in training.

`--train-successors` adds completed-state examples without gradient descent.
Only originating training families are eligible; the second rule must also appear
among training consumers. Validation/test originating families and unseen second
rules are not used as training augmentations. Candidates use the same exact local
teacher, starting from observed inputs, not native full-graph completion labels.
Each added transition also gets a no-request identity control. The collector
selects at most the first 64 admissible training transitions, one per source row;
39 are found for this workload, spanning eight second-rule types. The original
family split and test-chain selection remain unchanged. Ridge is still fitted
by closed-form solves with regularization selected on the base validation set.

| Paired metric, same 21 chains | Baseline | Added continuations |
|---|---:|---:|
| Free-running body RMSE | 0.33244 | 0.29770 |
| Oracle-input second-step body RMSE | 0.18093 | 0.16139 |
| Free-running live-boundary RMSE | 0.19262 | 0.18472 |
| First emissions | 20 | 20 |
| Second emissions | 20 | 18 |

The reduced RMSE does not prove higher semantic accuracy, especially as second
emissions decrease. There is no exact final-completion decoder for these chains.
It shows only that completed-state training examples improve this numerical
comparison; the large recurrence gap remains. No runtime takeover, ownership
transfer, speedup or source-stage legality is established. The existing expensive
boundary representation remains unchanged.

Run the earlier model command with `--generated-boundaries --train-successors`.
Omit `--train-successors` for the paired baseline. Both commands now include the
separate oracle-input diagnostic. `successor-training-results.json` retains both
runs and their common target fingerprint. Fifteen boundary/input tests pass, and
both GPU runs match independent NumPy execution of their learned recurrence.

## Decode the final Cell, rather than infer success from RMSE

`--audit-chains` adds a finite-catalog decoder **inside the compiled Metal
rollout**, after the second prediction. It does not read back or replace the
intermediate state. Each chain's dictionary contains the unchanged first
completion and all supported local completions enumerated from that first state,
across all rule types, not just the requested second rule. Identity remains a
candidate. Each candidate must preserve all first-completion facts under its
explicit quotient. Candidate keys retain the exact body and boundary quotient
map; distinct keys are not merged merely because their floating codes coincide.

Body and live boundary squared distances are each normalized by their width;
padding does not affect selection. The GPU selects a candidate using the actual
predicted body and boundary vector. Exact target labels do not enter that
selection. CPU f64 distance checks independently validate GPU choices and reject
near ties. The test covers alternative completions, ambiguity, omitted emissions
and padded-candidate exclusion.

On the same 21 chains there are only 2–16 candidates per chain. Three unsupported
rule matches remain excluded; no matching enumeration hit its limit. Thus this
is a small **known conditional Bake catalog**, not arbitrary-state decoding or
full-ruleset coverage. The catalog includes held-out structures, as in earlier
decoding tests. It is constructed offline around the correct symbolic first
completion, which does not itself prove the actual first prediction was correct.
The decoder is not a proof of activation, physical identity, source Run ordering,
visibility, global novelty or ownership retirement. Exact-key differences may
also conservatively reject alpha-equivalent alternatives.

| Final selection | Baseline | Added continuation training |
|---|---:|---:|
| Exact recorded target | 16 | 15 |
| Different target | 4 | 3 |
| No final emission | 1 | 3 |
| Ambiguous emitted selection | 0 | 0 |

This reverses the optimistic reading of the RMSE comparison: reducing latent
error did not improve exact target completion in this paired check. Continuation
training remains an optional experiment, not the default. Even the baseline's
16/21 result is conditional catalog selection, not a general semantic accuracy
claim. Wrong-target and missing-output rates remain unacceptable for unsupervised
ownership takeover.

Reproduce both earlier commands with `--audit-chains`. The paired results and
per-chain candidate/coverage counts are in `chain-candidate-audit-results.json`.
Nineteen related tests pass. Both Metal recurrences retain their NumPy numerical
checks; final selection additionally passes independent f64 distance checks.
