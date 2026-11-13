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
