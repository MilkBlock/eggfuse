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
