# Shared completed capture programs

The last executed sum-bits catalog has 65 states; 13 nonempty capture programs
refer to only three distinct final rule/slot/source lists. Against `a183c982`,
each state retains a mutable Vec even after Bake has finished deriving ports.
The node array also retains capacity for 128 states. This is an opportunity to
compress actual cross-stage metadata without another prediction registry.

The builder still derives donor ports, retention depths and inherited layouts
using mutable arrays. Only after final port assignment and layout compilation
are capture arrays frozen and interned. The key is the full Capture value:
Site plus actual ResultPort rule and slot. Site serialization alone is not a
safe sharing key because it intentionally omits lowered ports. One shared empty
array handles states without captures. The compile-local pool is discarded.
The final node array is an exact-length boxed slice; node IDs remain unchanged.

Existing publication, source Run order, history frames, retirement/generation
checks and actual returned-fact validation remain live. This change shares
immutable capture instructions, not instance results. It adds no bindings,
consumer lists, runtime lookup or decoding, and removes no logical RHS/repair
obligation. Rc ownership is maintained when catalogs are cloned or dropped,
not per capture. It does not claim new cross-Run takeover or saved operations.

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| State array, including capacity | 17,408 | 8,320 |
| Capture array payloads, including capacity | 1,440 | 144 |
| Shared capture ownership headers | 0 | 64 |
| Counted total | 18,848 | 8,528 |

The counted scope saves 10,320 bytes (54.8%). The Switch's node-array handle
also shrinks by 8 bytes, giving a net representation reduction of 10,328 bytes.
Counts assume two native words per Rc owner; excludes allocator rounding,
other node-owned arrays and unrelated switch storage. This measures the loaded
standalone Cell CPU catalog, not whole-process RSS or native egglog performance.
No speed campaign was run.

Validation: 15 result-handoff runtime tests and 15 compiler tests
(state_inheritance, closed_aliases, query_receipts). The new sharing test checks
that identical sources with different rule or slot identities do not alias,
that identical lists and empty lists do share, and that arrays survive disposal
of the compile pool and another owner. Full expanded Entries/contracts and
explicit (Site, rule, slot) capture programs agree. Other storage censuses agree.
All normalized work and 1,428 ordered Run signatures, final state and reviewed
native semantic acceptance agree (`pass`).

Reproduce the baseline census by applying `capture-storage-probe.patch` to
`a183c982` and using the current `inspect_cell_catalog` example with features
`iterative-bake,sparse-cells,view-ports`. The probe is reporting-only. Inspect
the same frozen program on both revisions and run the ordinary release kernel
with `--local-congruence`, followed by `choice_diagnosis.py`. Compare saved
artifacts with:

```sh
python3 benchmarks/cell-unification/check_catalog_paths.py --mode captures \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

OUTPUT_ROOT contains baseline/candidate execution directories and
semantic-acceptance.json. `shared-captures-check.json` records these checks and
hashes of the program, binaries, inspections and baseline probe.
