# Let completed sources own their routing address

The last audited catalog had 2,177 completed sources represented in both the
source directory and the ownership directory, plus ten routing-only sources.
The records served different responsibilities, but did not require independent
source-ID lookup tables and record arenas.

With `sparse-cells,storage-metrics`, ownership routing now lives in the existing
completed source record. Constructor reads, native Eq routing, local conditions,
query guards, composition and boundary classes resolve it through the existing
source directory. The former ownership `Frames` directory is empty in this
representation. No extra Cell facts, binding copies or consumer lists are added.

Ordinary sources and retired-but-addressable sources use a fallback route map.
Transfer moves a route into the source record and removes the fallback entry.
Restoration or source-storage retirement moves it back if native addressing is
still live. Component retirement removes it from whichever representation owns
it. This preserves old source IDs and FactRefs, independent epochs/depths, and
all existing physical slice locations. Source-capacity reclamation also releases
excess fallback buckets after transfer.

Other build configurations keep the original directory. Their immutable route
reader does not borrow non-Sync ordinary Cell storage. A no-default-features
check also exposed and fixed the earlier prefix-compaction guard referring to
the sparse-only `active_rhs` field unconditionally.

## Actual standalone runtime measurement

The Program is the already audited 108-extension catalog. The control is its
saved measurement; the candidate uses the same Program, flags and workload.
This is requested-heap accounting of the standalone Cell runtime, not native
upstream egglog, RSS or timing.

| Quantity | Before | After |
| --- | ---: | ---: |
| Graph bytes | 1,386,283 | 1,297,491 |
| Ownership routing directory bytes | 163,584 | 0 |
| Additional bytes in Cells | — | 74,792 |
| Completed source record width | 48 | 80 |
| Routes in completed records | 0 | 2,177 |
| Fallback routes remaining | — | 10 |
| Resident Program bytes | 107,599,014 | 107,599,014 |
| Execution/takeover process heap peak | 113,563,300 | 113,470,380 |
| Maximum extra takeover allocation | 11,376 | 19,568 |

Net Graph savings are **88,792 bytes (6.4%)**. The old source record now carries
routing fields, so its width grows. This is charged along with the fallback
map, rather than treating the deleted directory's entire size as savings.
Savings include eliminating the separate directory and its spare arena
capacity; they do not imply that all routing information disappeared.

Physical layouts, source slices, owners, lifecycles, ownership inventory, query
work, Run sequence and final exported state are exactly unchanged. No facts or
logical source instances are removed by this step. Graph memory is about 32.61%
of the historical 3,979,373-byte working-tree observation, still 103,680 bytes
above the 30% threshold. That historical denominator is not an isolated
immutable baseline binary. Saturated RHS skipping remains unfinished.

## Checks

Job 369 passes the no-default-features check, all 216 runtime library tests and
all 68 ownership integration tests. The extended source-storage fixture proves
that transfer empties fallback routes, in-place routing updates do not recreate
them, swap removal preserves another source's route, restoration preserves
native source identity, and routing can outlive source storage. Existing tests
cover union, deletion, reconstruction, inherited slices and stable source ports.
Job 370 passes all 882 Run graphs and ordered audits, matching the saved control
checks, and passes all four reviewed native final-state comparisons. Job 371
enables parallel publication, Cell absorption and view ports: all 68 ownership,
19 compiler and 13 witness-source tests pass. Exact hashes and statuses are
recorded in `source-routing.json`. No speedup is claimed.

Frozen binaries and complete reports are under `out/cell-source-routing`.
Rebuild the two storage examples with
`iterative-bake,sparse-cells,storage-metrics` under the shared compute queue:

```sh
runtime_storage_peak PROGRAM MEMORY inherited-owners --port-domains-only --cell-fields --retired-prefixes --state-output STATE
runtime_storage_comparison PROGRAM CHECKS --completed-owners --retired-prefixes
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_BUNDLE SEMANTIC_REPORT
```
