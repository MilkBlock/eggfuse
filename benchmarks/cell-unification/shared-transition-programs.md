# Shared completed transition programs

The last executed sum-bits catalog contains 65 states, 23 nonempty transition
rows and 83 logical transition edges. Including the empty row, only 11 rows
are distinct. Against `bd421908`, these rows still retain separate Vecs and
unused capacity after Bake has completed suffix/failure expansion.

Freeze and intern the final sorted rows using the same exact-slice helper as
capture programs. Compare full edge triples: RHS operation, leaf and target
state. No edge identity, order, failure state or restart fallback changes.
The compiler pool is dropped after states acquire shared ownership; runtime
advance keeps the same lookup and initial-state fallback. No new per-instance
metadata, consumer lists, expansion cache or dispatch lookup is introduced.
Catalog cloning/dropping maintains Rc ownership, not individual transitions.

This uses the last executed catalog to identify redundant representation,
not to infer new equality or source-Run permissions. Cross-stage capture
validity, visibility, source ordering, retention and mandatory queries remain
live. No additional Run-boundary work or RHS/repair obligation is discharged.

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| State array | 8,320 | 7,800 |
| Transition array payloads, including capacity | 3,264 | 936 |
| Shared transition ownership headers | 0 | 176 |
| Counted total | 11,584 | 8,912 |

The counted scope saves 2,672 bytes (23.1%). The 936-byte shared payload holds
39 physical edges, expressing the same 83 logical edges. Header estimates use
two native words per Rc owner; 11 owners include the shared empty row. Counts
exclude allocator rounding and other node-owned arrays. The state array overlaps
the earlier capture census; do not add those totals. The checker verifies both
censuses report the same state bytes and charges this change once. Capture
payloads, capture owners and all other censuses remain unchanged.

Validation: 16 runtime result-handoff tests and 15 compiler tests
(state_inheritance, closed_aliases, query_receipts) pass. A new test checks
sharing requires exact operation, leaf and target identities and verifies
successful transitions plus default restart fallback after the pool is gone.
Complete expanded Entries, contracts and explicit capture port identities agree.
All normalized work counters, 1,428 ordered Run signatures and final-state hash
agree; reviewed native semantic acceptance passes. These are standalone Cell
CPU results, not a native egglog runtime optimization. No speed test was run.

Apply the reporting-only `transition-storage-probe.patch` to `bd421908` for the
baseline census, using the current `inspect_cell_catalog` example with features
`iterative-bake,sparse-cells,view-ports`. Inspect the same frozen program on both
revisions. Run the ordinary release runtime with `--local-congruence`, then the
reviewed `choice_diagnosis.py` gate. Compare saved artifacts with:

```sh
python3 benchmarks/cell-unification/check_catalog_paths.py --mode transitions \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

OUTPUT_ROOT contains baseline/candidate execution directories and
semantic-acceptance.json. `shared-transitions-check.json` records comparison
results and hashes of program, binary, inspection and baseline-probe inputs.
