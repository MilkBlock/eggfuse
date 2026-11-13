# Capture the actual GPU-selected joint Cell witness

The intended execution remains repeated GPU Runs producing semantic Cell tokens,
followed by the original next stage at a fixed point. Capture is an opt-in training
observer on that path, not an alternative replay schedule or ownership registry.

## What is captured

`device_join_transition.proposals(..., capture=True)` retains the query result
already used by inference. It does not rematch or select historical alternatives:

- The complete joint binding, per-atom witness row/record and logical generation.
- Consumer input ports, actual source export ports and source template IDs.
- The exact source tokens, role coefficients, routes, seed and input features
  consumed by ridge, plus the provisional predicted token.
- Source visibility/settlement, logical generation, projected source fields and
  physical owner epoch/generation at the instant of matching.

Admission attaches its actual accepted mask. The Run controller preserves only
its existing stage semantics and records whether this was the query-start tick.
Disabled stages, wait ticks and HALT computations cannot become executed samples.
All captured tensors stay on device until the fixed launch sequence finishes.
The ordinary path has capture disabled and adds no resident state columns.

The CPU audit independently enumerates the chosen source Cell's original query
and completed constructor facts. It checks the selected record, overwritten
fields, shared-variable consistency across the entire join, input provenance,
source lifecycle, and physical owner generations. It does not treat individually
available source ports as a joint match. This is a snapshot soundness check, not
an exhaustive query proof or authorization to reuse the source in a future Run.

`floating_inputs` reconstructs the saved floating feature row from the actual
source messages. Consumer RHS labels never participate in this reconstruction.
Integer addresses select metadata; they are not converted to floating embeddings.

## Actual data and independent labels

The four real type-analysis rules 534–537 run on a snapshot with derived
PureType/PureTypeList facts removed. The device performs its own matching,
completion and physical-owner transfer until saturation. CPU closure runs only
afterward. It independently determines constructor terms and completed slot
values, then encodes the target with the shared template role definition.

Only newly admitted, completed Cells produce training rows. The export contains
`features`, `targets`, `predicted_tokens`, original rule IDs, and the captured
witness tensors. The `targets` are CPU-derived completion labels, not the ridge
prediction or an unverified copy of the GPU completion token. Their agreement
with completed GPU state is separately checked.

`device-match-corpus.json` records two cases with the original corpus partitions:

| Workload | Partition | New Cell samples | Samples consuming generated Cells | Relocated witness observations |
|---|---|---:|---:|---:|
| fitsinside | train | 7 | 4 | 31 |
| euler | validation | 5 | 2 | 23 |

Relocated observations count query-time witnesses whose physical row differs
from the logical Cell row; they are not unique transfers or saved operations.
The separate dot-product capture is labeled **test**, never included in this
training corpus. It has 7 samples and exact per-Run growth `[3, 2, 2, 0]`, with
9 owner rows released. All three captures pass independent closure and witness
checks. Data come from real programs, but this is only one selected four-rule
family and modified final-snapshot initialization, not full Eggcc execution.

A corpus manifest is mandatory for export. Membership must be unique, the
compiler Program fingerprint must match, and the original recipe must be equal.
The compiler fingerprint is distinct from the serialized JSON file hash; both
manifest/file provenance and raw trace hashes are retained. No backpropagation
or model fitting is performed by these collectors. Twelve train/validation
samples are not evidence of an accuracy improvement.

## Ownership methodology and noninterference

The latest inspected Bake commit is `81188496`: learn from execution after actual
completed-source takeover and prefix retirement, rather than a passive execution
with different intermediate ownership shapes. It explicitly preserves source
IDs, visibility, settled boundaries and checked append transitions.

The GPU observer likewise does not disable transfer. A regression runs the same
two-stage GPU fixture, including union, owner reclamation and subsequent matching,
with capture off/on. Logical/physical state, allocation IDs, Run ordering, token
counts and released rows agree (float tensors within numerical tolerance).
Every recorded joint witness passes the independent decoder. Existing ownership
and query/effect checks remain authoritative; observing a source does not create
an executable transition or authorize transfer.

39 related tests passed, including corrupt shared bindings, source generations,
physical generations, export ports, witness records and corpus provenance.
The native sum-bits semantic contract is not claimed: native code is unchanged.

## Costs and remaining work

This observer is intentionally diagnostic. With capacity 32 and 24 launch ticks,
about 17 MB of logical padded capture arrays are retained per case; filtering to
actual query starts plus training rows exports about 2.9 MB before compression.
These byte counts are sums of tensor sizes, not process RSS or unique allocator
bytes. Inactive padding and repeated matches remain in diagnostic tensors.

CPU witness audit, feature/target reconstruction and archive preparation take
about 0.02 seconds per tested case, excluding compression/file writes and the
separately reported CPU closure check. GPU times include compilation/upload and
observation; they are not production throughput or evidence of speedup.

Further work needs more real Cell families, original initialization and Run
snapshots, cross-ruleset data, mutable/scalar coverage and training selected by
exact semantic outcomes. The current completion kernel still establishes facts
with exact operations and refreshes completed tokens; this does not demonstrate
that ridge alone performs sound autonomous completion.

## Reproduce

Use the experiment Python environment from this directory:

```
python -m unittest test_device_match_capture test_device_query_join test_device_input_features test_device_ridge_transition test_device_join_transition test_device_matched_takeover test_device_scheduled_runtime test_reference_cell_closure test_device_snapshot_import
python collect_device_match_corpus.py TRAIN_MANIFEST VALIDATION_MANIFEST CORPUS_MANIFEST MODEL.npz ARTIFACT_DIRECTORY REPORT.json
python audit_type_family.py RHS_TRACE MODEL.npz REPORT.json --capture CAPTURE.npz --corpus-manifest CORPUS_MANIFEST
```

Binary captures and recipe sidecars are under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/device-match-corpus/`; reproducible
sources and text reports are committed, binary arrays are not.
