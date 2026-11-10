# Prediction storage ledger and next compression target

At `da4261b3`, reconstruct both inspectors from the same frozen sum-bits program.
The new ledger reconciles shared node-array counts across capture, transition
and completion reports, then charges that array once. The old rule-demand
census is a subset of the all-owner table-list census and is also not additive.
The script reconstructs all unique table lists from the expanded plan, checks
sorted uniqueness and table-ID bounds, and verifies owner, value and payload
counts against the runtime census. It rejects source mismatch, inconsistent
shared-array accounting and duplicate table IDs.

Selected standalone Cell CPU catalog structures total **19,592 bytes**:

| Structure | Bytes |
| --- | ---: |
| Catalog paths | 5,864 |
| Switch dispatch | 4,920 |
| Export interfaces | 1,256 |
| State array, counted once | 4,680 |
| Shared capture programs | 208 |
| Shared transition programs | 1,112 |
| Shared completion programs | 1,552 |

The separately derived optional completion plan has a **189,376-byte counted
subtotal**: all-owner table lists 156,136, repair matrices 30,760 and scope masks
2,480. Do not describe the optional plan's subtotal as memory used by ordinary
runs that never construct it. These are selected retained structures, not total
memory or RSS; omitted indexes, initial-state arrays, slot layouts, pure RHS
plans, merge metadata, headers and allocator rounding are listed in the JSON.

This changes the next optimization priority. The 771 unique obligation lists
contain 13,557 native-word IDs (108,456 payload bytes). Only 94 lists are longer
than a seven-word bitmap, yet their payload is 95,296 bytes. With a 401-table
universe, one fixed bitmap needs 56 payload bytes. A sparse-list/dense-bitmap
choice has an **18,424-byte payload estimate**, 90,032 fewer than the current
ID payload. This is not an implemented saving: variant descriptors, ownership,
interning and iteration cost still need accounting. It is not a latency model.

The next candidate should expose sorted iteration and membership directly,
retain sparse lists for small sets, and avoid materializing usize arrays at
every consumer. Interner keys must compare semantic table membership; query
snapshot reads, RHS-only obligations, source Run ordering, unknown/opaque
fallbacks and all conservative union/merge dependencies must remain distinct
and exact. No later-stage permission follows merely from a smaller set encoding.
Revalidate expanded plan, closure matrix/singleton scopes and existing execution
contracts. Measure retained bytes and any newly added iterator, conversion or
storage work before interpreting the candidate as an improvement.

No runtime implementation or scheduling changed in this ledger commit. No
speed campaign or new takeover is claimed; existing semantic results are not
rerun for this read-only audit. Current inspectors compile/run successfully.
The ledger reproduces its census, and three malformed-input checks reject
inconsistent overlaps, duplicate table IDs and mismatched source digests.

Reproduce with the current `inspect_cell_catalog` and
`inspect_completion_storage` examples, using
`--features iterative-bake,sparse-cells,view-ports`, then:

```sh
python3 benchmarks/cell-unification/prediction_storage_ledger.py \
  --catalog CATALOG.json --completion PLAN.json --program PROGRAM.json \
  --output LEDGER.json
```

`prediction-storage-ledger.json` records current components, the explicitly
hypothetical payload estimate and input hashes. The frozen program is
`out/cell-slot-inheritance/compact-final/program.json`.
