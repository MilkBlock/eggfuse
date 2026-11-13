# Direct-source neighborhood feature experiment

This is observed-wiring, floating Cell replay on Metal, not an autonomous Eggcc
GPU runtime. No backpropagation, identity-to-float encoding, or executor changes.
Current exact runtime mechanisms do not establish complete Eggcc saturation.

## Hypothesis and representation

Existing four-channel messages condition source tokens on endpoint roles. Add a
128-float request context from the two-round baked neighborhoods of the source
and consumer ports: concatenated tanh(sum) and tanh(difference), normalized over
actual provider alternatives. Neighborhoods include ordinary query/effect operand
positions and literal operands. They read templates, not consumer output labels.
The source/consumer connection still comes from observed wiring; its autonomous
discovery and lifetime proof are not claimed by this experiment.

Retain all original input and token features, and insert new random projection
rows without resampling the baseline projection. Token width remains 128, raw
input width grows 1408 to 1536. Inference weights grow 573568 to 622720 floats
(+8.57%); each prepared request has 128 additional floats. The prototype computes
and pools static connection vectors during preparation; a runtime would need to
share those vectors by compiled connection and charge dynamic selection/gather.
It has not been wired into the device Entry feature compiler or promoted as its
model. Model metadata records the variant; Eq replay tools consume that metadata.

## Controlled result: improvement in RMSE is not semantic improvement

Same expanded training manifest and original model-validation manifest as the
saved neighborhood-input baseline. Model hyperparameters use validation only.
Existing expanded Eq validation independently selects the readout, without test
selection. Both choose ridge alpha 1 for token prediction and alpha .1 for the
partition readout. Test is held-out dot-product, 5935 captured applications,
5553 complete states, 5550 linked states, 5454 with comparable Eq pairs.

| Measure | Baseline | Added source context |
|---|---:|---:|
| Direct linked RMSE, correct source tokens | .04130498 | .04047332 |
| Linked RMSE, predicted source tokens | .04099524 | .04009779 |
| Validation macro exact Eq rate | .80708085 | .80652078 |
| Test exact Eq partitions | 4404 | 4388 |
| Test false equal pairs | 613 | 700 |
| Test missed equal pairs | 1815 | 1854 |

CPU/GPU numerical audits pass, including Eq threshold agreement. The feature is
**not accepted as an accuracy improvement**. Pooling static neighborhoods still
loses relational information; these results motivate testing relation-preserving
features, but do not prove a particular replacement will work. The target remains
GPU-generated Cell tokens until a proven fixed point, then the next source stage.
No stage advancement is authorized by these predictions.

A preliminary run used expanded model validation and resampled the larger random
projection. On that separate setup direct linked RMSE worsened .03107912 to
.03145545. Those models are not compared to the controlled baseline above and
remain external artifacts. No favorable-only accuracy claim is made.

## Reproduction

Use multi_entry_ridge.py with the same positional inputs as the neighborhood-input
baseline and append --channels 4 --encoding class-history-neighborhood-input
--source-neighborhood. Train: rhs-training-expanded-20261114/manifest.json;
model validation: rhs-validation-20261114/manifest.json; corpus and test trace:
observed-corpus-20261113/{manifest.json,rhs-dot-product.json}. Artifacts reside
under /Volumes/Extreme SSD/eggfuse-artifacts/21ee.

Then run select_eq_readout.py with rhs-validation-expanded-20261114/manifest.json,
the frozen model and report, --marks OUTPUT.jsonl --reject-unstable-candidates.
Committed result JSON records exact input/model hashes, all selected policies and
numeric checks. Models and detailed marks remain external. Tests cover preserved
baseline projection, absent-source zero context, and no consumer-outcome leakage.
