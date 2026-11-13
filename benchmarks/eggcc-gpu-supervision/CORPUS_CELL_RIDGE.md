# Ridge over known Cell families and actual multi-entry inputs

This is a standalone GPU proposal experiment using the expanded observed eggcc
corpus. It predicts the whole local body and its boundary channels, then selects
a known candidate on Metal. It does not replace the CPU runtime, discover live
matches, prove global novelty or run rulesets to saturation.

## Dataset and fitting

The collector's whole-workload train/validation/test partitions remain unchanged.
Within each partition, identical (compiler family, normalized source, binding)
inputs are deduplicated and observation counts retained. The same input may
legitimately occur in training and test workloads; overlap is reported separately,
not hidden or described as unseen-state generalization. There are 3,466 unique
partition inputs: 1,880 train, 736 validation and 850 test.

Each real input gets one synthetic no-request identity control. Controls do not
count as actual observation frequencies. Training gives each distinct input equal
weight rather than allowing frequent matches to dominate. Training and validation
are separated by workload. The regularizer is selected only using validation
loss; no backpropagation is used.

Cell states contain a 64-float body plus persistent original/generated boundary
channels. Initial encodings and their request attachments are prepared once on
CPU. The attachment calculation is numerically checked against the earlier dense
Bake projection without allocating a large projection per input. CPU matching
still supplies the input instances. This experiment does not yet exercise the
new model on repeated successor-generated inputs.

Features retain the original body, request, their interactions and boundary
attachment. In the positional variant, an additional 64-column role encoding is
appended; it does **not** overwrite the original request. Fixed nonlinear features
and closed-form multi-output ridge predict the whole state residual and emission
score. Body, boundary and emission losses receive group normalization so padded
boundary dimensions do not simply drown the emission objective.

## Output checking and scope

The candidate catalog contains 3,939 known states from 296 compiler families,
including held-out symbolic structures. Selection is scoped only by family, not
the desired output. GPU floating distance evaluation and argmin select the
candidate in the same call as inference. CPU f64 distance checks validate all
selections and identify near ties. Metal and NumPy learned-state outputs are also
compared. This is finite-catalog decoding, not open-ended semantic decoding.

A strict success requires the exact recorded body, quotient map and layout, plus
the correct local emission decision. Exact state alone is insufficient: a false
emission can prevent saturation. Alpha-equivalent alternative representations
are conservatively distinct. The labels still come from conditional local
constructor/union completion, not full native constructor outputs. In particular,
locally new information may already exist elsewhere in the egraph.

## Paired results

| Test population | Original features: strict success | Added position columns: strict success |
|---|---:|---:|
| All 850 distinct inputs (including uncovered-family diagnostics) | 801 | 817 |
| 833 inputs in training-covered families | 788 | 802 |
| 711 exact inputs already seen in training | 693 | 705 |
| 122 new inputs in a covered family | 95 | 97 |
| 17 inputs in uncovered families, diagnostic only | 13 | 15 |

The covered-family strict result is 802/833 (96.28%). Seen-input performance is
705/711; new-input performance is only 97/122. Uncovered families require CPU
fallback regardless of a favorable diagnostic prediction. Even covered families
still have errors, so this does not authorize ownership retirement.

Among all 779 locally novel test requests, the positional variant emits the exact
target for 753, emits a wrong target for 18 and misses 8. It also falsely emits on
7 locally non-novel inputs. The improvement is concentrated in already seen
inputs; novel-target success on *new* covered-family inputs decreases from 91 to
88 while fewer false no-op emissions improve their combined metric slightly.
This mixed behavior should not be hidden by an aggregate percentage.

The earlier integration that replaced the request with a mixed positional code
had only 780/850 exact final states, versus 814/850 without that replacement.
Adding features without discarding existing information matters. The new
concatenated variant has 822/850 exact final states and 817/850 strict successes.

## Costs and remaining work

The prototype's global padded state has **34,080 floats per Cell**, because a few
large initialization rules have huge output interfaces. This is unacceptable as
a production batch layout. The dense candidate matrix and readout also have
substantial costs. No speedup is claimed; the numerical result is evidence about
finite-family learning only. Grouping compatible layouts and preserving the
boundary interface without global padding remain necessary.

More importantly, the result does not test repeated inference, recovery from
prediction drift, reliable stopping, cross-stage visibility or actual ownership
transfer. Those cannot be inferred from this first-transition success rate.
The saved model is intended to make those next experiments reproducible, rather
than retraining from scratch each turn.

## Reproduction and artifacts

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_cell_ridge.py MANIFEST BASELINE.json --no-positioned-roles
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_cell_ridge.py MANIFEST POSITIONAL.json --model-output MODEL.npz
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_corpus_cell_ridge
```

MODEL.npz stores numerical projection/readout weights and candidate vectors;
MODEL.json.gz stores family and exact candidate metadata with the manifest
fingerprint. These generated binaries remain on the external SSD, outside Git.
The experiment outputs and hashes are recorded in `corpus-cell-ridge-results.json`.
Use the manifest at the external corpus path in `OBSERVED_CORPUS.md`.
