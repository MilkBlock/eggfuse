# Enumerated interfaces in the actual GPU token loop

`collect_enumerated_gpu.py NATIVE MODEL SYNTHETIC_HEAD OUTPUT [--resume]`
reads the native collection manifest and visits every audited terminating input.
It validates archived source documents, then executes the selected-family GPU
loop with the existing synthetic-only ridge head and predicted-source feedback.
It captures actual matches, slot-owner releases and generated-source consumers,
and invokes the independent CPU labeling/audit path. The original native
manifest determines membership; no output accuracy filter chooses examples.

The 20 growing cases are excluded from this *terminating execution* collection.
Boundary Eq certificates for 16 of those cases are not whole-state execution
labels, and are not silently mixed into training. This is a standalone three-rule
GPU prototype, not full Eggcc or GPU-authorized Eq effects. Exact matching,
constructor and ownership checks remain authoritative. No gradient descent.

Each case is processed in temporary local storage and archived with a checksum;
resume verifies source/model/head identities and prior archives. Timeouts or
failed audits remain explicit. The manifest is written atomically. The label
report and training metadata have distinct filenames. A guard in the labeler
rejects coincident paths before any artifact is read/written; a regression test
covers it. In the initial batch, 71 metadata files were regenerated after a path
collision. All labeled arrays were checked equal before/after, and old archives
were retained; GPU execution was not repeated.

`unpack_enumerated_gpu.py CAPTURES OUTPUT` validates archive hashes, source replay,
label hashes and synthetic training provenance before materializing self-contained
NPZ/JSON training pairs. Incomplete collections are rejected unless explicitly
requested with `--allow-partial`; the output manifest records that limitation.
The source manifest is hashed from the same bytes that were parsed, so a live
collector cannot change the unpacked snapshot's recorded identity.

## Completed collection and fixed-alpha fit

All 487 terminating boundary inputs passed the GPU execution and independent
label audit: 2,404 samples, 597 generated-source consumers, 1,997 released owner
rows. Accepted witness pairs include 473 repeated logical sources and 11 pairs
of distinct logical sources sharing one physical owner. These are workload
counts, not ridge accuracy or full Eggcc acceptance.

The enumeration-only fit uses all 487 entries, alpha 10, no backpropagation,
and the same feature basis and explicitly identified synthetic feedback parent.
No examples were selected by validation score. The three heads observe 2/2,
7/15 and 7/15 possible compiled output states (formerly 2/2, 5/15, 5/15).
Training exact partitions are 2,300/2,404; GPU/CPU numerical parity passes.

Recurring development validation, using exact source states:

| Case | Old head exact | Enumeration head exact | Old false merges | New false merges |
|---|---:|---:|---:|---:|
| GCD | 25/41 | 13/41 | 67 | 228 |
| LCM | 80/99 | 22/99 | 33 | 661 |

Direct-input exact partitions fall from 17/26 to 2/26 and 60/78 to 2/78.
Generated-source groups are 8/15 to 11/15 and 20/21 to 20/21. This does not
establish predicted-feedback rollout improvement. The new head is NOT promoted.
Full counts and report hashes are in `enumerated-ridge-results.json`.
GCD/LCM are development evaluations, not untouched holdouts.

Artifacts are under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/enumerated-gpu-v1`:
verified case archives, manifest, classifier weights/report, fit log, and exact
argument vector `fit-argv.json`. Materialized training inputs are reproducible
with `unpack_enumerated_gpu.py`; the recorded temporary paths are not required
permanent artifacts. Binary artifacts are not committed.

The failure does not establish that more synthetic data is harmful. It shows
that this completed-producer, fully supported two-Cell domain and existing
features are insufficient. Missing-input enumeration, multi-producer identity,
and interaction closure remain separate coverage obligations. The 20 growing
inputs remain excluded from full-execution training; boundary-only proofs are
not whole-state labels.
