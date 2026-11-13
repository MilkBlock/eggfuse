# Select Unit ownership from actual cross-stage continuation demand

The all-eligible Unit conversion increased Graph memory. A successful typing proof
is not a reason to pay for ownership on every table. This experiment selects only
Unit tables used as Entries by the four-frame closure catalog learned from the
last actual execution: CellSpineView11, CellSpineView8 and CellSpineView9 (IDs 139,
168,169). All other tables retain their previous storage.

## Compiler changes

`specialize_unit_facts_selected` requires sorted, unique table IDs and redoes the
all-writer eligibility proof for each selected table. The source validator derives
the exact changed core from that selection. Selection cannot authorize an initial
membership, deletion, mutable read, constructor or other ineligible table.

`bake_unit_closures` exports selected Unit Entry table IDs from the same checked
query-atom mapping as its selected fragments. No new runtime observation is needed
for this selection. `relower_entry_values` accepts the table list and optionally
migrates a previously learned ownership catalog. Root implementations and Entry
indices are remapped through templates and query atoms. Each migrated fragment is
checked using the same typed substitutions as normal Plan derivation. Unknown
wiring is discarded and ordinary residual execution remains available.

Here root splitting produced 257 candidate fragments; 234 had valid substitutions,
all within the existing 256-fragment budget. No budget increase was necessary.
The migration has a deterministic prefix-first cap for larger cases. Original
ranking credit is removed after migration: it is not a measurement of new code.
The existing 6,325 ordinary routes and 32 iterative joins are retained.

## Observed storage

Actual standalone Cell runtime on sum-bits, requested allocation bytes, not RSS:

| Measure | Accepted baseline | Selected Unit + learned catalog |
|---|---:|---:|
| Graph teardown heap | 2,617,317 | 2,502,270 |
| Retained Program heap | 117,318,509 | 119,610,132 |
| Execution/takeover process peak | 125,400,997 | 127,612,142 |

Graph improves by 115,047 bytes (4.40%). Graph plus Program regresses by 2,176,576
bytes. The accepted baseline therefore stays unchanged. This is not the 30%
target, a speedup, or proof that internal facts no longer need materialization.

The largest Graph changes are function storage -120,032 bytes and reverse-use
storage -39,932 bytes, charged against new component/boundary/stable-field costs.
Most Program growth is retained artifact JSON (+2,462,011 bytes), not newly
executed runtime state. Its cost is nevertheless included. The facts remain
observable; do not call these records logically deleted facts.

## Checks and reproduction

Eight specialization tests pass, including selective/empty conversion, rejection
of invalid selections, unchanged snapshots for an unselected table, and invalid
fragment roots/source positions. Final state equals the saved accepted export.
All 1,428 Run comparisons pass for graph, ordered RHS and logical writes; the
original saved baseline checks also match. The exact candidate final export equals
the reviewed legacy export, and the existing choice-diagnosis semantic gate passes
using those saved exports (`selected-unit-semantic.json`). The separate results
file records the full Run audit and all memory deltas.

```
# Build with local target, CARGO_INCREMENTAL=0, features:
# iterative-bake,sparse-cells,storage-metrics
bake_unit_closures UNIT_OWNED_PROGRAM SAVED_PROFILE SELECTION_DIRECTORY
relower_entry_values BASELINE CANDIDATE --unit-ownership \
  --unit-tables=SELECTION_DIRECTORY/frames4/unit-tables.json \
  --ownership-catalog=SELECTION_DIRECTORY/frames4/program.json
runtime_storage_peak CANDIDATE HEAP.json inherited-owners --port-domains-only
audit_matched_handoffs BASELINE CANDIDATE SAVED_CHECKS AUDIT.json
python3 benchmarks/cell-structural-compression/summarize_selected_unit.py \
  out/cell-structural-compression \
  benchmarks/cell-structural-compression/selected-unit-results.json
```

The optional control keeps the same three selected tables but migrates only the
baseline catalog (omit `--ownership-catalog`). This separates representation
selection from learning additional cross-stage fragments. It is a storage control,
not a second semantic admission or timing campaign.

Control result: selected tables with the old catalog use 2,521,494 Graph bytes.
Table selection contributes 95,823 bytes of reduction; the learned catalog adds
19,224 bytes. These disjoint differences sum to the reported 115,047 bytes.
The control's final export matches; no full Run audit is claimed for the control.
