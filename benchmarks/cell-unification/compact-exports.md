# Compact retained Cell export interfaces

The last executed catalog contains three exporting rules and six result slots.
Against current branch `d75aed32`, the runtime nevertheless retains a Vec for
every one of 582 rules plus excess capacity in the three slot arrays. These are
the authoritative interfaces consumed by Cell effect slots and stage publication,
not a new forecast-only registry.

Use the existing contiguous dispatch-row representation generically for export
Sites too. Trim trailing empty export rows after result ports are compiled;
missing rule lookup still returns an empty slice. Slot order, binary-search
results and ResultPort rule/slot identities do not change. All internal empty
rows remain directly indexed. Empty catalogs allocate neither row nor slot
arrays. No runtime reconstruction, new instance bindings, consumer lists or
query assumptions are introduced.

This removes storage redundancy proven by the completed compiler layout; it
does not discharge additional work at a source Run switch. Existing visibility,
retirement, returned-fact validation and history retention remain live. No extra
cross-stage takeover or RHS saved-operation credit is claimed.

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| Rule directory | 13,968 | 1,160 |
| Site arrays including capacity | 384 | 96 |
| Counted arrays | 14,352 | 1,256 |

Array storage falls 91.2%, saving 13,096 bytes. The enclosing Switch gains one
machine word (8 bytes here), so the net representation saving including that
header change is **13,088 bytes**. Excludes allocator rounding, unrelated switch
state and JSON artifacts. This is a loaded standalone Cell CPU measurement, not
whole-process RSS or a native egglog runtime memory measurement. No speed test
was run; adjacent offset reads remain part of the access cost.

Validation: 14 result-handoff runtime tests and 15 compiler tests
(state_inheritance, closed_aliases, query_receipts) pass. Tests cover empty and
missing rules, full-width absent indices, exact slot order and lookup, clone
lifetime, existing dispatch behavior and inherited frame retention. Expanded
catalog/contracts, all exported interfaces and all other census values agree.
All normalized work and 1,428 ordered Run signatures and final state agree;
the reviewed native semantic acceptance is `pass`.

For the baseline census, apply `export-storage-probe.patch` to `d75aed32` and
use the current `inspect_cell_catalog` example, built with
`--features iterative-bake,sparse-cells,view-ports`. The patch only reports
storage. Inspect the same frozen program on both revisions. Run the ordinary
release runtime with `--local-congruence`, then the documented
`choice_diagnosis.py` semantic gate. Check the saved artifacts with:

```sh
python3 benchmarks/cell-unification/check_catalog_paths.py --mode exports \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

OUTPUT_ROOT contains baseline/candidate execution directories and
semantic-acceptance.json. `compact-exports-check.json` records results and
program, binary, inspection and probe hashes.
