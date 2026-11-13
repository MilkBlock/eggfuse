# Dictionary-free boundary readout: partial coverage, not safe union authority

The frozen whole-Cell model still predicts 128-float Cell tokens and feeds them
to subsequent Cells. `token_eq_readout.py` adds a **separate audit decoder** for
the local typed Eq partition. It does not replace the inference model with an
Eq-only predictor, create constructors or scalar results, discover matches, or
apply any proposed union.

The experiment removes the training-state dictionary from this boundary task.
It shows partial recovery on unseen states, but not sufficient correctness for
a runtime takeover. Even oracle tokens leave many equalities undecoded, so
rollout drift alone cannot explain the failure.

## Inputs, fitting and exact facts

For every complete captured Cell, the template determines all unordered pairs
of Eq slots with the same sort. Reflexive pairs and cross-sort pairs do not
become learned queries. Pair features use the Cell token, fixed template request,
symmetric sum/difference/product of port-role vectors, and token/role products.
A fixed positional code distinguishes static template slots with otherwise
identical roles. Physical graph IDs never enter the features.

A 512-column raw feature vector plus 256 fixed random tanh columns and a constant
feeds a scalar ridge score. Training uses deduplicated `(template, captured
state)` rows from the original training split; validation selects alpha from the
existing four-value grid. Threshold stays 0.5. No gradients/backpropagation or
test-label fitting occur. Original model and trace hashes are verified.

The optional `--static-equalities` plan compiles transitive equalities from
copy and explicit union effects **after successful RHS completion**. It does
not assume those effects have happened before the Cell executes. Every such
claim is checked against captured post-Run identities; disagreement aborts the
experiment. Static equalities bypass learned readout. Other constructor
congruence or mutable-read relationships are not silently treated as proved.

On test data, this removes 5,064 of 77,684 pair queries from learning. The fixed
plan is separate from the model's target dictionary and applies to new templates
as well. Training learned queries fall from 13,056 to 12,465. Static masks are
computed from template instructions, never from test equality labels.

## Results on predicted Cell tokens

| Subset with comparable Eq pairs | Instances | Learned decoder only | With completed-effect proofs | Static-facts-only baseline |
|---|---:|---:|---:|---:|
| Seen state | 3,769 | 2,557 | 2,533 | 2,455 |
| New state, known template | 1,177 | 848 | **877** | 830 |
| New template | 508 | 75 | 220 | **271** |
| Total | 5,454 | 3,480 | **3,630** | 3,556 |

A success means every queried local Eq membership matches the captured
reference. It is **not** a full Cell-state or native-graph success: scalar values,
external identities, visibility and lifetime remain unverified. Another 99
complete captures have no comparable pairs and are not counted as successes;
382 incomplete captures remain outside the readout.

With completed-effect proofs, predicted tokens produce 336 false-positive Eq
pairs and miss 2,901 true pairs. Raw scores are not transitively closed in 260
instances. Closing proposed equalities would increase false-positive pairs to
547, so closure cannot be treated as a harmless repair. Negative scores are
absence of a proposed equality, not native inequality facts.

The decoder recovers only **11.28% of the remaining true equalities** beyond
static proofs. Exact-partition counts alone would hide this weak recall. Of the
5,454 checkable instances, 1,824 (33.44%) are marked for Eq mismatch. Relative to
static facts alone it fixes 132 instances and damages 58; on new templates it
has zero complete-partition wins and 51 losses. Thus this learned decoder must
not authorize new unions, even where its confidence score looks high.

Oracle tokens plus static facts recover 3,678 partitions versus 3,630 from
predicted tokens. Oracle recall beyond static facts is also only about 11.1%.
This implicates the current encoding/readout combination, without proving that
the representation has an information-theoretic impossibility.

## CPU supervision, marks and costs

CPU capture supplies the audit reference. Optional JSONL marks identify source
Run, binding ordinal, rule, token index and every wrong slot pair, distinguishing
false merges and missed equalities. The final run writes 3,600 marks across the
oracle and predicted-token audits; 1,824 belong to predicted tokens. Marks
explicitly set `union_authorized: false`. They are diagnostic records, not a
connected native correction engine. Scalar/external-identity validation remains
required even when no Eq mark is emitted.

CPU/GPU readout checks pass with no threshold disagreements. Boundary feature
encoding is currently on CPU; only the ridge readout matrix runs on GPU. In the
final predicted-token diagnostic, feature encoding costs 0.391 s, GPU readout
plus transfers 0.025 s, and CPU partition audit **including JSONL mark writing**
0.166 s. This is not a fast verifier or an end-to-end speedup. The simpler raw
readout's separate costs are preserved in its report. No result is described as
a committed graph mutation or native semantic acceptance.

## Reproduce

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/token_eq_readout.py \
  "$ROOT/rhs-training-20261114/manifest.json" \
  "$ROOT/rhs-validation-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/port-channels4-factored.npz" "$ROOT/port-channels4-factored.json" \
  "$ROOT/token-eq-readout-static.npz" "$ROOT/token-eq-readout-static.json" \
  --static-equalities --marks "$ROOT/token-eq-readout-static-marks.jsonl"
```

Omit the two optional flags and use fresh output paths for the raw readout.
Models, raw captures and marks remain on the external SSD; reports contain their
fingerprints. Six tests cover typed pairs, false-merge/closure accounting,
non-vacuous success, completed copy/union proofs, static-query elimination and
slot feature distinction. The related suite passes 94 tests.

## Static-class queries (`--quotient`)

This optional experiment requires `--static-equalities`. Bake-like template
preparation contracts the proved copy/union components and creates one learned
query per same-sort pair of components. Its descriptor is the mean of the
members' positioned role vectors; the ridge features otherwise stay unchanged.
Training counts a component pair once, instead of weighting it by its number of
slot-pair aliases. No captured dynamic equality determines the components.
An explicit expansion map restores **all original slot-pair scores** for audit;
within-component scores are statically true. Captured labels must agree within
each component pair or the experiment aborts. The map is shared by template.

The frozen whole-Cell model, observed provider routing, train/validation/test
split, 0.5 threshold and complete-capture eligibility remain unchanged. This
changes both descriptors and example weighting, so it does not isolate which
one causes the accuracy change. It is a standalone boundary probe, not an
integrated GPU runtime improvement or a newly authorized union path.

| Predicted-token diagnostic | Static slot-pair decoder | Static-class decoder |
|---|---:|---:|
| Learned queries | 72,620 | 34,240 |
| Original audited pairs | 77,684 | 77,684 |
| Exact partitions / 5,454 | 3,630 | 4,287 |
| New state, known template / 1,177 | 877 | 966 |
| New template / 508 | 220 | 200 |
| Recall beyond static proofs | 11.28% | 37.68% |
| False Eq pairs | 336 | 789 |
| Missed Eq pairs | 2,901 | 2,038 |
| Nontransitive instances | 260 | 49 |
| False Eq pairs after closure | 547 | 2,052 |
| CPU-marked fraction | 33.44% | 21.40% |

Oracle-token exact partitions increase from 3,678 to 4,267, but oracle false
Eq pairs also increase from 162 to 453. This is a recall/precision tradeoff,
**not** an unqualified correctness improvement. Predicted new-template cases
have 583 false pairs and no complete-partition wins over static facts alone;
71 previously correct partitions become wrong. Do not enable this decoder as
union authority. Alias expansion can amplify a single wrong class prediction;
retaining full slot-pair accounting exposes that cost.

Training queries fall from 12,465 to 4,568, validation queries from 28,545 to
8,302. Counts of unique training/validation states remain 416/364. Alpha remains
100, selected on validation. The two validation MSEs average different query
populations and are not directly comparable.

The measured preparation of test nodes, layouts and audit labels costs 0.975 s.
Retained quotient-plan arrays for templates represented in the audit occupy
8,929,680 bytes, additional to the existing slot-pair layouts; Python object
and allocator overhead are excluded. The CPU boundary feature matrix occupies
210,644,480 bytes. This prototype still materializes it before GPU readout.
Predicted-token feature encoding takes 0.305 s, GPU readout plus transfers
0.0137 s, and CPU audit including mark writing 0.177 s. These are single-run
diagnostics, not an end-to-end speed claim. CPU/GPU scores pass tolerance checks
with zero threshold disagreements. There are 2,354 JSONL marks across oracle
and predicted audits; 1,167 are for predicted tokens.

Reproduce with the command above, adding `--quotient` and changing all three
output paths from `token-eq-readout-static` to `token-eq-readout-quotient`.
`token-eq-readout-quotient-results.json` records hashes and measurements. Eight
local tests (96 in the related suite) include typed class separation, complete
expansion, rejection of inconsistent labels and fully static/empty queries.
The option remains off by default. The main next representation question is
how much alias multiplicity should also be removed from the **whole-Cell token
encoder**, rather than only its boundary decoder, while preserving the dynamic
relations that subsequent Cells need.
