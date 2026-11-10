# Shared lowered completion programs

The last executed catalog contains 65 states but only six distinct fully
lowered completion programs, including the empty program. Against `08dd9ac6`,
each node retained an inline Terminal with two Vec descriptors and duplicated
read arrays. These are the executable query/RHS reuse descriptors; no parallel
prediction or instance fact graph is added.

Intern complete Terminal values after result ports have been assigned. Equality
includes Reuse/QueryReuse fields, their actual lowered ResultPorts, and the
completion flag. Serialized certificates deliberately omit ports and cannot be
used as the interning key. The compiler pool disappears after nodes acquire
shared ownership. Runtime program access borrows the shared object directly.

There is one necessary later compiler mutation: after portable certificate
validation, complete_cells derives the completion flag using static_skip proofs.
Preserve its position and per-state rule. Only when the flag changes, copy the
shared object before mutation; then re-intern equal final programs. This prevents
one state's lowering from changing another state's certificate or a cloned
catalog. No mutable program sharing or copy-on-write occurs during execution.

This removes duplicate immutable descriptions, not logical query, publication
or repair work at Run switches. Original source order, visibility, retirement,
history retention, returned-fact checks and all unproven work remain live.
There is no new per-instance metadata, dispatch lookup or decompression.

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| State array | 7,800 | 4,680 |
| Shared Terminal objects and ownership headers | 0 | 432 |
| Reuse/query read arrays including capacity | 2,016 | 1,120 |
| Counted total | 9,816 | 6,232 |

This saves 3,584 bytes (36.5%). Shared owners include Terminal itself and an
estimated two-word Rc header; inline baseline Terminals are already in the state
array. Excludes allocator rounding and unrelated arrays. State-array accounting
overlaps the capture and transition censuses, so totals must not be added. The
checker reconciles all three views and charges that array only once. Other
payloads and ownership counts remain unchanged. This measures the loaded
standalone Cell CPU catalog, not native egglog memory or process RSS. No speed
campaign was run.

Validation: 17 runtime result-handoff tests and 15 compiler tests
(state_inheritance, closed_aliases, query_receipts) pass. The new test verifies
identical programs share, serialized-identical programs with different lowered
ports do not share, and completion-flag mutation preserves other owners.
Full expanded contracts/Entries, lowered query and RHS ports, 1,428 ordered Run
signatures, normalized work and final-state hash agree. The reviewed native
semantic acceptance passes.

Apply reporting-only `completion-storage-probe.patch` to `08dd9ac6` for the
baseline census and use the current `inspect_cell_catalog` example with features
`iterative-bake,sparse-cells,view-ports`. Inspect the same frozen program on both
revisions. Run the ordinary release runtime with `--local-congruence`, followed
by `choice_diagnosis.py`. Compare saved artifacts with:

```sh
python3 benchmarks/cell-unification/check_catalog_paths.py --mode completion \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

OUTPUT_ROOT contains baseline/candidate execution directories and
semantic-acceptance.json. `shared-completion-check.json` records results and
hashes of program, binaries, inspections and baseline probe.
