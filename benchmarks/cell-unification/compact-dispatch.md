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

## Contiguous dispatch rows

The next iteration inspects the executed catalog's remaining 576-row directory:
only 38 pivot slots exist, yet each row retains a two-word slice descriptor.
`DispatchRows` now stores a single contiguous slot array and row offsets.
Empty rows repeat an offset; pivot holes remain explicit. Lookup reads adjacent
offsets and takes the existing row slice, preserving constant-time indexed
access and unique-root enumeration. There is no expansion cache or extra
per-instance state, and no new cross-Run takeover. The extra offset read remains
part of dispatch; compression alone does not prove a speedup.

Against `c8914225`, row directory bytes fall from 9,216 to 4,616; slot bytes
remain 304. The counted dispatch structures total **4,920 versus 9,520 bytes**,
a 48.3% reduction (4,600 bytes). Relative to the earlier 26,160-byte layout,
the same counted scope is down 81.2%. Scope exclusions above still apply;
the Switch header itself gains two machine words (16 bytes on this target) and is excluded in both
censuses. Accounting for that header increase, the net reduction is 4,584 bytes.
Individual row allocations are replaced by one slots allocation, but no
allocator-event count or latency benefit is claimed.

Three runtime tests and the same 15 compiler tests pass. Tests cover consecutive
empty rows, interior holes, out-of-range rules including usize::MAX, leaf zero,
root priority and replay. The expanded catalog and contracts, all normalized
work and 1,428 ordered Run signatures, final-state hash and semantic acceptance
remain unchanged. `compact-dispatch-rows-check.json` records this comparison.
Use the reproduction command above with `--baseline-commit c8914225`; this
baseline has its own census, so no reporting patch is needed.
