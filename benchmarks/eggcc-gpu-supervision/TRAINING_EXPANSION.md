# More real training inputs: token benefit and readout regression separate

This experiment expands the original **training partition** from three to ten
Eggcc workloads. It changes neither the validation workload (euler) nor the test
workload (dot-product). No test observations enter fitting. The full Cell-token
model is refit using the existing class-balanced encoding and four role channels,
with closed-form ridge and no backpropagation. Observed routes are replayed on
GPU; autonomous matching, ownership and saturation remain unimplemented.

## Capture and reuse

Selection remains based on original partition, status, binding count and saved
CPU reference time, without using accuracy or test template coverage. The ten
smallest complete training cases below 4,000 bindings qualify. The three existing
captures are reused only after checking source manifest, binary fingerprint,
partition, program identity and trace/link hashes. New captures use the exact
same debug binary, with per-Run graph equality, final graph equality and Run
control-count equality checks. Runtime source is unchanged in this experiment.

| Case | RHS applications | Reused |
|---|---:|---|
| fitsinside | 1,031 | yes |
| loopfact | 1,239 | yes |
| recfact | 1,487 | yes |
| birthday | 1,678 | no |
| pascals-row | 2,439 | no |
| euclid | 2,767 | no |
| binary-fmt | 2,852 | no |
| dead-branch | 3,012 | no |
| sum-check | 3,320 | no |
| sum-sq-diff | 3,809 | no |
| Total | 23,634 | |

All ten pass reference audits. Their reference execution times range from 0.039
to 0.119 seconds; expensive per-Run graph exports/checks are separate capture
costs, not performance measurements. There are 23,056 complete usable state
instances; missing slot observations remain excluded. Linked consumers increase
from 2,327 to 14,719, cross-ruleset consumers from 292 to 1,710, and cases needing
multiple observed providers from 1,004 to 6,001. All 32,283 requested constructor
results in eligible windows are available. These are observed potential links,
not unique ownership or proof that a provider caused the match.

## Coverage is not accuracy

Unique `(template,state)` training examples increase from 416 to 1,153. The
training dictionary now covers 4,357 test instances instead of 3,855; unknown
template instances fall from 508 to 318, unseen states in known templates from
1,190 to 878. It recovers 3,995/4,357 covered states. That denominator and set
of states changed: comparing this directly to 3,666/3,855 does not isolate a
model improvement. All 5,553 complete test instances remain in the token audit.

The fixed-population Eq audit still has 5,454 comparable cases, 77,684 slot pairs
and 34,240 learned class queries. Refit both token model and boundary decoder:

| Metric | Three training workloads | Ten training workloads |
|---|---:|---:|
| Exact local Eq partitions | 4,438 | 4,368 |
| False Eq pairs | 962 | 888 |
| Missed Eq pairs | 1,727 | 1,874 |
| Recall beyond static facts | 47.19% | 42.69% |
| False Eq pairs after closure | 2,150 | 1,055 |
| Marked comparable instances | 1,016 | 1,086 |

Coverage improved, but exact partitions and recall regressed. Template subsets
also change membership, so subset rates are not directly paired comparisons.
The new token-model alpha is 0.1 (previously 10); decoder alpha is 1 (previously
100), both selected on the same validation workload. Decoder validation MSE
improves from 0.02214 to 0.01490 while test exact partitions decline. MSE and
thresholded partition correctness are different objectives; validation workload
coverage is also limited. These observations do not identify the sole cause.

## Frozen cross audit isolates the two fitted components

`audit_training_expansion.py` verifies model/decoder/trace fingerprints and
requires identical token encodings and decoder feature maps. It crosses the two
already-fitted models with the two decoders without any refitting or changed
threshold. GPU output is checked numerically against CPU matrix multiplication.
Every combination is audited on the same full test population.

| Token model | Decoder | Exact partitions | False Eq pairs | Missed Eq pairs |
|---|---|---:|---:|---:|
| Original | Original | 4,438 | 962 | 1,727 |
| Expanded | Original | 4,510 | 887 | 1,706 |
| Original | Expanded | 4,335 | 766 | 1,985 |
| Expanded | Expanded | 4,368 | 888 | 1,874 |

With the original decoder fixed, additional token-model training helps these
three metrics. The refitted decoder loses more true equalities. Oracle tokens
also show the decoder regression: 4,512 exact partitions with the original
readout versus 4,360 with the expanded readout. Therefore the jointly retrained
result must not be used to conclude that larger token-model training itself
caused the exact-partition regression.

The cross audit is diagnostic, **not test-set model selection**. The apparent
best exact-partition combination still has 887 false Eq pairs and 2,485 after
closure. None can authorize unions. A further experiment should broaden the
original validation partition and evaluate regularization/selection against
false-merge and complete-partition objectives, while keeping test data held out.

## Costs, checks and reproduction

Whole-model preparation is 4.940 s and fitting 0.576 s. State/model widths and
routing structure are unchanged. Expanded Eq readout takes 0.304 s for CPU
feature encoding, 0.0084 s for GPU matrix readout plus transfers, and 0.175 s for
CPU audit/mark writing. These are diagnostic timings, not end-to-end speedups.
CPU/GPU audits pass and no boundary threshold disagreements occur. Native
semantic acceptance is not claimed. The related suite passes 100 tests.

```sh
python3 benchmarks/eggcc-gpu-supervision/collect_rhs_training.py \
  "$ROOT/observed-corpus-20261113/manifest.json" \
  target/debug/examples/capture_rhs_results \
  "$ROOT/rhs-training-expanded-20261114" \
  --max-cases 10 --max-bindings 4000 \
  --reuse "$ROOT/rhs-training-20261114/manifest.json"
```

Use `CLASS_BALANCED_TOKENS.md`'s three commands with the expanded training
manifest and fresh `class-balanced-expanded*` output names; keep validation,
test, encoding and channels unchanged. Cross the frozen artifacts with:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_training_expansion.py \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/training-expansion-cross.json" \
  --variant original "$ROOT/class-balanced.npz" "$ROOT/class-balanced.json" \
    "$ROOT/class-balanced-eq.npz" "$ROOT/class-balanced-eq.json" \
  --variant expanded "$ROOT/class-balanced-expanded.npz" \
    "$ROOT/class-balanced-expanded.json" "$ROOT/class-balanced-expanded-eq.npz" \
    "$ROOT/class-balanced-expanded-eq.json"
```

Committed reports are `rhs-training-expanded-results.json`,
`class-balanced-expanded{,-dynamics,-eq}-results.json` and
`training-expansion-cross-results.json`. Binary/raw artifacts remain on the SSD.
