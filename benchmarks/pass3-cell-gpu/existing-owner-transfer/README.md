# A transfer between two preexisting completed Cell owners

An earlier experiment measured an integral parent growing in place and avoiding creation of a child owner. Here the source store has already allocated both owners and published all their member IDs before the proposed transfer. The isolated build reuses the existing sparse Cell store at revision `f62704246fef80e13b4c1afb43f827e9a9da1761`. Its native `Cells::extend_completed` moves the slots and fact states of a whole set of existing owners into one destination. For the intervention to count, it must report exactly zero newly added frames and one consumed old owner.

The stock admission scans ordinary source records for candidate components and then explicitly skips a group whose members have all transitioned to completed storage. The census checks every live compiler-proven component at each source Run instead. Its seven columns count component visits, visits with at least two members, wholly ordinary transferable groups, wholly completed groups, groups spanning at least two old owners, groups spanning exactly two, and groups covering all frames in both owners. Counts accumulate visits, including unchanged components across Runs.

The split arms provide a controlled alternative to the stock physical layout. At a settled Run boundary the native store partitions an eligible compiler-composed shape into two genuinely allocated owners, with separate arrays and stable member addresses. At the next eligible boundary an independent observer locates live external graph rows that use the members' output e-classes. The two owners and all component members must still be present. Keep, merge, stale-epoch and partial-member controls share that same initial graph and execute the same source schedule. The normal merge applies under an exclusive mutable graph borrow only after checking all source frames. The issuing policy is an experiment control; no neural issuer credit is assigned.

Each recorded decision includes the two old owner IDs, destination, source shape and member templates, member birth epochs, current Run epoch, old/new source references and their versions, external readers and slot positions, retired owner IDs, physical accounting before/after, and allocation deltas inside the actual native move. The owner directory can retain an empty header slot. Live owner count, released vector entries, retained bytes and net allocator bytes are separate reward labels. Allocator measurements are requested heap bytes and charge copies and temporary allocations; source process RSS is a different measurement.

The source runs verify ordered RHS inputs, effective writes, actual Spine resumes and committed union pairs against the independently frozen CPU ledger and compare the final graph object. A second, explicitly perturbed branch injects a union between two unequal same-sort local ports, invokes canonical repair and compares the new external reader states and repaired full graph with the keep arm. It stops at that repair so the extra equality is outside the unmodified source result.

## Native interventions

The frozen input programs contain no ownership-fragment catalog. Across 2,695,109 component visits on dot-product and 2,219,731 on stable-argmax, all components were singletons. We ran a separate source-training pass using the original compiler's ownership-fragment profiler, retaining 203 and 240 checked templates. This is within-workload Bake for an intervention, so it provides no evidence of cross-family selection. On stock pooling with these catalogs the two workloads visited 278,811 and 219,754 components that touched exactly two existing owners, but **none covered every member in both backing allocations**. The unpooled stock control also exposed no admissible pair. Seeding two whole owners without pooling unrelated siblings produces the following controlled real-engine outcomes. [Original-input census](unbaked-census.json) · [Census and exact action labels](results.json)

| Source | Run of split → merge | Old owner 0 / old owner 1 | New owner | External readers | Allocation requested / freed | Net live bytes saved | Temporary peak above pre-merge |
|---|---:|---|---:|---:|---:|---:|---:|
| four-stage fixture | 4 → 5 | {1,3} / {5,7} | 0 | 1 | 744 / 520 B | −224 B | 576 B |
| dot-product | 19 → 20 | {275,298} / {314} | 0 | 3 | 528 / 652 B | +124 B | 304 B |
| stable-argmax | 19 → 20 | {253,276} / {299} | 0 | 11 | 456 / 552 B | +96 B | 304 B |

All three moves actually relinquished owner 1's backing allocation and moved its existing fact-state and slot payload. The store reused owner 0. Each move reduced its total number of live owners by one, added zero new sources, freed zero owner-vector slots and freed zero logical source descriptors. Both real workloads moved five slot values and four live fact states. The early local increase in allocator high-water mark is charged even when terminal bytes decrease. No per-merge latency or whole-pass speedup is inferred from this structural diagnostic.

Dot-product's member birth generations are 17, 18 and 19. Source template shape 423 is rechecked at epoch 20; every old port reference, row version and external reader matches immediately after the move. The stale control presents epoch 19 and the partial group offers only {298,314}, leaving 275 behind in owner 0. Both fail before moving data. For stable-argmax shape 455 rejects {276,299}, preserving 253. After the positive actions the unmodified source schedules perform another 593 / 1,191 committed unions. Reading the original addresses across 1,516 / 1,130 remaining boundaries produces the same sequence as retaining both owners. [Full instance evidence with parent addresses and before/after layouts](examples.json)

The small fixture additionally unions an actual local port in each former owner: source 1, op 0, column 1 and source 5, op 1, column 0. Both are sort E. Graph repair produces identical roots, external reader fields and graph export with or without the owner transfer. In each real instance, both possible non-redundant cross-owner TypeList equalities are rejected in both arms. They would make TypeList-length conflict without a merge expression. Each trial runs in a separate process. Sharing storage does not establish new semantic equality.

### Converting these results to training samples

At a settled source boundary, a proposed action would seal the source Run/epoch, compiler shape, two owner handles and the full set of member references with versions. The verifier would check physical ownership, completeness and outstanding external readers, then return the actual destination, consumed owner, surviving source identities, allocation/free deltas and peak cost. A keep action on the same source state supplies the counterfactual. The saved positive and rejected records provide such *physical* supervision. To claim neural credit an integrated implementation must also carry an authenticated issuing token serial and commit its action in the same execution. These labels contain no neural issuer, and ordinary future children avoided at allocation never qualify as an existing-owner transfer.

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/existing-owner-transfer
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/online-storage-20261120" "$e/NEW-old-pair-build"
corpus="$e/repair-bake-families-20261120"
python "$d/study.py" "$e/NEW-old-pair-build/engine" "$corpus" "$e/NEW-old-pair-census" --census-only
python "$d/catalogs.py" "$e/NEW-old-pair-build" "$corpus" "$e/NEW-old-pair-catalogs"
python "$d/study.py" "$e/NEW-old-pair-build/engine" "$corpus" "$e/NEW-old-pair-study" --catalogs "$e/NEW-old-pair-catalogs" --cases fixture dot-product stable-argmax
python "$d/labels.py" "$e/NEW-old-pair-study" "$d"
python "$d/verify.py"
```
