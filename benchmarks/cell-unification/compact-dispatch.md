# Compact result-switch dispatch

The last executed sum-bits catalog has 64 units but only 38 pivot positions.
The current-branch switch still retained 582 optional root entries (all absent),
Vec capacity for each pivot row, and a duplicate Entry-to-leaf BTreeMap.
No new iteration evidence or source-block takeover is needed to remove these
representation costs: leaf IDs, original Run boundaries, state contracts,
receipt validity and retirement checks remain authoritative and unchanged.
No cross-Run query or publication work is discharged by this change.

The switch now uses boxed exact-length arrays of nullable NonZeroUsize IDs
(encoded as leaf + 1), drops trailing empty rule/root rows, and replays paths
through the same indexed dispatch used at runtime. It no longer retains its
own duplicate leaf map. Catalog's separate compilation index remains live.
No per-instance metadata or consumer list is added.

Against `9e0bac8a`, on the actual loaded standalone Cell CPU sum-bits catalog:

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| Rule row directory | 13,968 | 9,216 |
| Pivot arrays, including capacity | 1,856 | 304 |
| Root array | 9,312 | 0 |
| Duplicate map entry payloads | 1,024 | 0 |
| Total counted | 26,160 | 9,520 |

This saves 16,640 bytes (63.6%) in these structures. It excludes BTree node
slack/links, allocator rounding, the switch header and other switch data;
it is neither total runtime memory nor an RSS measurement. The remaining
rule directory is still mostly empty; this change retains direct indexing.

Validation: 15 compiler tests (state_inheritance, closed_aliases, query_receipts)
and one focused runtime dispatch test pass. The latter checks missing rows,
leaf zero, full-width encoding, root precedence, supply requirements and replay.
Expanded Entries, state contracts and existing path storage match exactly.
All normalized work counters and 1,428 ordered Run signatures match, as does
final-state SHA. The native comparison's reviewed semantic contract passes.
No timing campaign or native egglog runtime speedup is claimed.

Reproduce the before census by applying `dispatch-storage-probe.patch` to
`9e0bac8a` (reporting only) and using the current `inspect_cell_catalog` example.
Build the example with `--features iterative-bake,sparse-cells,view-ports`.
For both revisions, pass the frozen program
`out/cell-slot-inheritance/compact-final/program.json` and a census output path.
Run the ordinary release runtime with `--local-congruence`, then the documented
`choice_diagnosis.py` semantic gate. Verify saved outputs with:

```sh
python3 benchmarks/cell-unification/check_catalog_paths.py --mode dispatch \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

OUTPUT_ROOT contains baseline/candidate runtime directories and
semantic-acceptance.json. The committed `compact-dispatch-check.json` records
source baseline, program and binary hashes and the comparison results.
