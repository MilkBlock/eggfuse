# Source-sharing relations and the direct-consumption error boundary

This opt-in experiment retains whether two bound input ports originate in the
same Cell instance. It is not an ownership certificate. Different sources can
share facts, and one source can still have live external readers.

For each continuation edge, Bake supplies the endpoint-neighborhood coefficient
c. With a source-sharing matrix A (upper triangle only), the added feature is
`tanh(sum(c * (A @ c)) / sqrt(max(number_of_pairs, 1)))`. Source IDs are used only
for exact connectivity; renaming them cannot change the floating output. This
adds 128 request floats without changing the 128-float Cell token or the four
existing message channels. The original random projection rows remain fixed.
No gradients or extra GPU control flow are introduced.

The operation runs in compiled Metal in both single-source Entry and multi-source
query/admission paths, selected with source_relations=True at compilation. It
consumes current witness sources and shares their lifecycle checks. No host
feature readback, new ownership authority, or change to stage advancement is
introduced. Default compilation remains unchanged. Runtime matching retains one
binding witness per input; the training trace includes provider alternatives.
Their distributions are not proven equal, and a trained whole-workload GPU
execution is not claimed by these mechanism tests.

## Controlled evidence

Same training/model-validation/test hashes as SOURCE_NEIGHBORHOOD.md; token
ridge alpha 1, Eq readout alpha .1 selected on validation. No policy is selected
using the test diagnostic. Held-out dot-product has 5550 linked complete samples
and 5454 comparable Eq partitions.

| Measure | Baseline | Source relations |
|---|---:|---:|
| Direct RMSE with correct sources | .04130498 | .03911998 |
| Recurrent RMSE | .04099524 | .03899386 |
| Validation macro exact partitions | .80708085 | .80654594 |
| Test exact partitions | 4404 | 4402 |
| Test false equal pairs | 613 | 636 |
| Test missed equal pairs | 1815 | 1827 |

This is **not** accepted as an overall semantic improvement. Inference weights
increase from 573568 to 622720 floats. Each compiled edge gains 128 float
coefficients, each request gains 128 floats, and the current dense relation
kernel uses O(E^2) connectivity plus O(128 E^2) floating work for E edges.
It is a functional test, not an efficiency claim. Large-degree groups need a
cheaper compiled reduction before promotion. Preparation and replay wall times
in the reports include compilation/upload and are not runtime speedup evidence.

## The stronger finding: audit the decoder separately

`audit_direct_source_readout.py` freezes both trained models and the selected
readout, verifies trace/model/readout hashes, and evaluates three inputs to the
same readout. All CPU/GPU numeric and threshold checks pass.

| Input to Eq readout | Baseline exact | Source relations exact |
|---|---:|---:|
| Encoded actual completed state | 4419 | 4419 |
| Predicted completion from correct source tokens | 4406 | 4410 |
| Recurrently predicted completion | 4404 | 4402 |

The actual-state readout already misclassifies 1035 of 5454 partitions. Baseline
rollout misclassifies 1050. Only 19 direct errors occur where the actual-state
readout was correct; recurrence introduces three errors where direct prediction
was correct and removes one. Relation features introduce eight recurrent errors
beyond direct and remove none. These sets are diagnostic, not an additive causal
decomposition: numerical prediction errors can also cancel readout errors.

Most observed partition errors therefore already exist at the representation /
Eq decoder boundary. This does not distinguish irreversible compression loss
from inadequate decoder features/training. That distinction must be tested before
adding more source features or attributing errors to long chains. Correct-state
inputs are audit labels only, never proposed as runtime inputs.

## Reproduce and limits

Use multi_entry_ridge.py as in SOURCE_NEIGHBORHOOD.md, replacing
--source-neighborhood with --source-relations, then run select_eq_readout.py with
the same expanded validation. Run audit_direct_source_readout.py with positional
trace, model, model_report, weights, selection_report, output paths. Committed
JSON reports retain hashes and all chosen policies; models and error marks are
on the external artifact volume. There is no native Eggcc correctness or full
ownership-transfer claim. 126 related tests pass, including both compiled device
admission paths, connectivity relabeling, permutation invariance and masking.

The tracked Bake branch remains 55f5fd9a: derive route wiring from ordinary Cell
definitions and share producer operands, rather than persisting duplicated route
annotations. These optional coefficients derive from the same definitions; their
additional storage is charged above, not presented as a storage saving.
