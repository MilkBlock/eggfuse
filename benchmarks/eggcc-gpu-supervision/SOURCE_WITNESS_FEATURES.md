# Preserve port interfaces when training source consumption

The target remains GPU-owned Cell-token generation, repeated Runs until no new
semantic information, then the original next ruleset/stage. This change does not
replace that controller with an observed schedule. The experiments below use
observed wiring to diagnose its floating model; they are not autonomous Eggcc
acceptance or ownership proofs.

## Actual mismatch and change

`device_join_transition.compile_transition` selects an input's first query atom
and compiles source-role coefficients for its view records. `proposals` obtains
the actual selected witness record, source row and generation on device. There
is one selected source per required Eq input port. Live-source inference checks
visibility, settlement, generation and dirty-token status.

The trace-training path previously pooled every observed alternative for each
input port. A group with N alternatives divided each edge by sqrt(N), then the
whole input divided by sqrt(total edges). These are not the same inputs as the
selected-witness path, especially when alternative groups have different sizes
or source Cells carry different local contexts.

`dataset` now retains the input slot, source export slot, source template and
alternative count alongside each existing training edge. The probe uses this
interface to select first/last/mixed observed alternatives per input, undo the
old alternative-count factor, preserve each port even when it shares a source,
and recompute causal depths. Numeric IDs never become float features. Existing
role coefficients and four message channels are reused.

The validation population has 27,386 instances, 26,637 complete captured states
and 26,142 states with Eq queries. 15,316 instances have an ambiguous source
choice. Selecting one source per port changes 156,972 edge references to 78,773.
These are input references, not committed graph mutations or saved runtime work.

This is offline capture metadata, not a new runtime fact/source directory. It
adds four metadata integers per training edge conceptually (Python dictionaries
have additional unmeasured overhead). There are no additional inference columns,
model matrix dimensions, GPU dispatches or lifecycle records.

## Validation, including a rejected apparent improvement

All variants use closed-form ridge and fixed random features, no backpropagation.
The augmentation fits the original training view plus a mixed first/last view,
using the same completion labels. It does not fit on validation or test labels.
Validation selects ridge alpha; the frozen Eq decoder is unchanged. No test
partition was consulted. Historical observations and independently selected
ports are not necessarily jointly realizable, currently visible query witnesses.

`source-witness-validation.json` compares two refits on the expanded validation
partition. Both select alpha=100 by token error. In single-first direct inputs,
augmentation improves token RMSE .02194661 -> .02160591 and exact Eq partitions
22,899 -> 23,006. This is not sufficient to adopt the model.

`source-witness-frozen-audit.json` therefore compares the actual resident model
(alpha=1, selected on its original validation manifest) with that candidate:

| Single-first inputs | Resident | Augmented alpha=100 |
|---|---:|---:|
| Direct exact partitions / 26,142 | 22,923 | 23,006 |
| Direct false Eq pair predictions | 7,060 | 5,240 |
| Direct missed Eq pairs | 5,405 | 5,341 |
| Direct false pairs after transitive closure | 9,566 | 14,275 |
| Rollout exact partitions / 26,142 | 22,969 | 23,073 |
| Rollout false pairs after transitive closure | 9,677 | 14,355 |

The candidate reduces false pair predictions but increases their consequences
under transitive closure. Reject it as a runtime replacement. Counts refer to
predicted Eq pairs, not actual union operations or native graph mutations.

`source-witness-alpha1.json` fixes the numerical alpha at 1 for both fits. Its
baseline reproduces the resident's exact-partition and pair-error counts. The
augmentation has 22,987 exact direct partitions, 7,863 false pair predictions and
9,715 false pairs after closure for single-first inputs. It also fails to improve
all necessary criteria. Keeping alpha fixed does not preserve the effective
per-example penalty when augmentation doubles the training rows.

Neither experimental model is installed as the runtime default. These findings
support retaining port interfaces and testing source choice, but do not prove
that this augmentation improves safe completion. The next data step needs
jointly selected actual GPU witness records and current visibility evidence;
independent historical port choices cannot substitute for those observations.

## Checks and costs

31 focused tests pass, including existing GPU matching and matched takeover,
source normalization against compiled Metal live-source inference, repeated
shared-source ports, independence from completion labels, invalid metadata, and
training-only normalization. GPU floating readout differences were below 2e-6
in the numerical experiment. This is not the native sum-bits semantic contract.

The frozen audit's CPU Eq validation takes about 4.9–5.2 seconds per policy for
both direct and rollout outputs (53,274 complete-state checks combined), including
readout-feature materialization and partition checks. This excludes training,
trace preparation, GPU replay and full native graph verification; it is not a
claim about end-to-end CPU supervision throughput. Exact error counts remain
necessary even when mean token error improves.

Bake reference 6b86e7db is still the latest inspected cell-parallel-admission
commit. Its completed-source routing uses the existing source record and retains
fallback addressing. This experiment adds no runtime directory and makes no
ownership inference from a selected source or common physical owner.

## Reproduce

From this directory, use the experiment Python environment:

```
python -m unittest test_source_witness_probe test_multi_entry_ridge test_device_ridge_transition test_device_join_transition test_device_matched_takeover
python source_witness_probe.py TRAIN_MANIFEST VALIDATION_MANIFEST MODEL.npz REPORT.json --decoder DECODER.npz --decoder-report DECODER_REPORT.json
# Repeat with --alpha 1 to isolate the fixed-numerical-alpha case.
python audit_witness_models.py VALIDATION_MANIFEST DECODER.npz DECODER_REPORT.json AUDIT.json --model resident RESIDENT.npz RESIDENT_REPORT.json --model augmented MODEL.npz REPORT.json
```

Model binaries remain under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/`:
`source-witness-augmented.npz` and `source-witness-augmented-alpha1.npz`.
Committed JSON reports record their hashes and the input manifest hashes.
