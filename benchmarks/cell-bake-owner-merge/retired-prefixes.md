# Retire exhausted suffixes into existing compiled prefixes

The last selected catalog's actual execution retained 107 ownership frame
descriptors after their source records were gone. All were trailing suffixes.
This is duplicate runtime state, but absence of a source record alone does not
prove that its native Eq address or later-stage transitions can be removed.

The compiler now derives a directory of existing, address-identical prefix
shapes. Ports must form the same contiguous symbol prefix; origins and static
signal instructions must match. It also checks the complete reachable append
language: every transition anchored in a surviving frame must still have a
corresponding transition, recursively through subsequent stages. It creates no
new shape, marker relation, fact graph, binding copy or consumer list.

An explicit `--retired-prefixes` experiment switches to this existing shape at a
settled Run boundary. Removed source records must be absent, and retained
symbols must not resolve to native addresses in removed frames. Surviving
source IDs, frame ordinals, symbols, facts and slots remain in place. Only the
dead suffix's ownership directory entries, symbol bindings and boundary
registrations are removed. Future valid appends can complete the prefix again.
Active execution, pending repair, frozen components and exploratory catalog
tracing reject this takeover. Production execution does not enable it by
default.

## Actual runtime evidence

Job 349 uses the same binary and selected 256-path Program for both lanes.
This measures the standalone Cell runtime, not upstream native egglog or RSS.

| Quantity | Control | Prefix retirement |
| --- | ---: | ---: |
| Graph requested heap | 1,405,919 | 1,392,459 |
| Resident Program requested heap | 107,450,586 | 107,450,586 |
| Execution/takeover process heap peak | 113,434,884 | 113,421,646 |
| Final components | 1,584 | 1,558 |
| Final ownership frame descriptors | 2,284 | 2,182 |
| Final symbol slots | 8,273 | 7,978 |
| Final bound symbols | 6,887 | 6,643 |
| Successful compiled appends | 786 | 820 |

There are 129 suffix retirements during execution, removing 336 symbol slots.
These cumulative counts differ from final inventory deltas because some
prefixes complete again. Remaining domain signal visits decline from 162,335
to 157,705. Live facts and exported logical state are preserved, not eliminated.

The Graph saving is 13,460 bytes (0.96%). The compiled prefix directory adds
4,136 resident Program bytes relative to the preceding binary; both lanes in
this experiment pay that cost. Current Graph memory is 34.99% of the historical
3,979,373-byte working-tree observation, still 198,648 bytes above the 30% goal.
The historical denominator is not an isolated immutable baseline binary.

The experiment performs **1,074,658 component scans** to obtain these savings.
This is not an accepted speed optimization. The next trigger should use existing
source retirement events and source-to-component addressing; `retire_empty`
already knows which source it actually removed. Safe application must still
wait for settled publication and repair, rather than mutate a frozen component
or recreate per-producer consumer subscriptions. Neither this feature nor its
smaller representation proves that an RHS effect can be skipped.

## Validation and reproduction

Job 345 passes all 68 ownership integration tests. The new regression covers
suffix deletion, an external mutable function holding its result, nontrivial
union and completing the prefix again, checking exports, snapshots and binding
audits. Job 349 also passes the compiler test rejecting a prefix that loses a
second-stage append, then checks all 882 Run graphs and ordered execution
audits. Those checks exactly match the previous selected catalog's saved checks.
Job 351 passes the reviewed native sum-bits final-state semantic contract using
saved native exports; no exclusions or proof rules changed.

Build the examples with `iterative-bake,sparse-cells,storage-metrics` under the
shared compute queue. Frozen binaries and detailed artifacts are in
`out/cell-retired-prefixes`; hashes and counter deltas are in
`retired-prefixes.json`.

```sh
runtime_storage_peak PROGRAM CONTROL inherited-owners --port-domains-only --cell-fields --state-output CONTROL_STATE
runtime_storage_peak PROGRAM CANDIDATE inherited-owners --port-domains-only --cell-fields --retired-prefixes --state-output CANDIDATE_STATE
runtime_storage_comparison PROGRAM CHECKS --completed-owners --retired-prefixes
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_BUNDLE SEMANTIC_REPORT
```
