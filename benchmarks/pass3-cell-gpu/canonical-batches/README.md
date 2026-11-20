# Canonical equality roots inside ordered Cell effects and rebuild

These experiments isolate parent-directory work on 3mm and Deriche in the complete, frozen standalone Rust Cell engine. The prior measured profile charged 287 / 530 ms to ordered effects, 98 / 160 ms to rebuild, and 73 / 148 ms to publication. It used two learned views, a two-column forward feasibility check, and the complete-generation contract on each source. Prior RHS lookup memoization and slot-projection experiments target different operations. [Complete original phase measurements](../prefix-transfer/phases.json)

The ordinary parent table is an FxHashMap from displaced representative to its new parent. It preserves commit order. A source Eq identity generally encodes its producing Cell in the high half and its slot in the low half; a large external identity still has full hash-table semantics. The sparse implementation already includes a per-Cell bit indicating that a parent might exist. We reproduce that bit as a control alongside the default store; the two new strategies are more precise.

* **Coarse.** A zero bit bypasses the parent map. A set bit consults the exact native parent map, including unrelated slots in the same Cell.
* **Direct.** An indexed Cell names a sparse record only if some slot displaced. Each record holds the most recently installed slot/parent, a bitmap of displaced low slots, and a flag for wider slots. A full slot match returns that immediate parent; a proved absent slot terminates the walk; ambiguous slots and Cells above the bound use the original map. The directory mirrors each actual parent insertion, including replacement of an earlier binding.
* **Memo.** A thread-local table caches 256 complete source roots. The full original equality ID and the current phase/union generation must match. Phase entry, a parent insert and clearing the store invalidate prior root answers. A unique stamp also prevents confusing diverging graph clones. A combined arm uses the direct directory on cache misses.
* **Visibility and physical identity.** All changes remain in the original ordered RHS, union and rebuild. An enqueued equality changes these results only when the native parent relation changes. Mutable table merge, nested set sorting/deduplication, publication and physical Cell creation are still performed. Search and export keep the original read behavior. There is no query-specific rule or substitution for an unknown parent.

The separate diagnostic marks the native source RHS and repair intervals. Per phase it counts source root calls, native parent-map probes (including the terminating probe), edges actually traversed, immediate-parent hits, absent-directory hits, complete memo hits, input IDs already canonical, walks of at least two and four edges and maximum walked depth. Memo hits do not walk an edge in the treatment. The source arm reveals the unmodified depth distribution. The exact audit independently recomputes each intercepted result along the ordinary parent relation and verifies every source Run's RHS, effective writes, union order, Spine resumes, final graph and original physical allocation provenance. Diagnostic validation and counters run outside paired timing.

## Root and rebuild measurements

| Workload / lookup | RHS hash probes | Repair hash probes | Ordered RHS ms | Repair ms | Full inference ms | Extra directory capacity, B |
|---|---:|---:|---:|---:|---:|---:|
| 3mm / source | 1,423,068 | 718,101 | 319.6 | 110.1 | 2129.9 | 0 |
| 3mm / coarse | 667,069 | 450,002 | 317.5 | 104.6 | 2127.8 | 65,536 |
| 3mm / direct | 495,290 | 208,302 | 316.9 | 105.7 | 2139.7 | 2,876,416 |
| 3mm / memo | 474,599 | 261,840 | 321.2 | 106.8 | 2139.8 | 0 |
| 3mm / combined | 143,971 | 77,940 | 307.6 | 104.9 | 2086.0 | 2,876,416 |
| deriche / source | 2,337,207 | 1,203,469 | 572.8 | 172.5 | 3861.8 | 0 |
| deriche / coarse | 1,140,570 | 768,743 | 570.0 | 171.5 | 3884.2 | 121,856 |
| deriche / direct | 730,018 | 287,609 | 574.9 | 169.0 | 3857.0 | 6,252,544 |
| deriche / memo | 832,861 | 436,734 | 577.8 | 168.4 | 3868.7 | 0 |
| deriche / combined | 250,289 | 108,115 | 573.9 | 173.7 | 3818.8 | 6,252,544 |

In the original lookup, **all 1,423,068 RHS root calls on 3mm and 2,337,207 on Deriche already had a canonical input**. No path-compression scheme can remove an edge traversed by these calls. The repair walks followed 191,618 / 320,734 links for 176,315 / 296,609 nonroot inputs. Even perfect path compression reducing each nonroot to one edge would remove only 15,303 / 24,125 of the 718,101 / 1,203,469 source map probes in repair, or 2.13% / 2.00%. These probe counts cover walks through value::root; direct calls to Parents::contains_key, such as a pre-check in normal subscription construction, sit outside this denominator.

The combined treatment removed most original probes. It saved 17 ms across the measured RHS and repair medians on 3mm, while both fixed phases became marginally slower on Deriche. The memo alone consumes another 6,144 bytes per participating thread. Four warmed observations per timing arm include the original CPU graph, source validation, ordered effects and complete rebuild. The independent unmodified learned executor took 2,157.2 / 3,877.9 ms; the independent vanilla reference took 934.6 / 1,619.8 ms. [Full counters, physical allocations, component timings and API round trips](roots.json)

A separate 10-second stack sample of the exact signed runtime with all treatments off found 605 / 639 identifiable ordered-effect and 351 / 280 repair samples (3mm / Deriche). Within ordered effects, tree operations under Graph::subscribe_edges accounted for 128 / 121 samples, versus 48 / 25 under named canonical value/root routines. During rebuild, tree operations under Graph::union accounted for 104 / 80 and under Graph::subscribe_edges for 49 / 35, versus 41 / 20 under named canonical routines. The nearest identifiable native routine is used as caller; optimized code may inline root/slot work. Unidentifiable executor code and outside-inference samples stay separate. [Native sample categories, top symbols and source callers](samples.json)

## Active-frame and subscription controls

The second matrix moves the existing sparse backend's generation lifetime into the ordinary backend. At entry to an ordered RHS it records the generation used for its rule matches. Only the currently executing Cell frame can read a marked, materialized Eq value verbatim. The mask is compiled per rule from its declared input slots, excluding redefined slots. A separate arm additionally marks copies of proven slots and destinations of constructor calls. Every applied union clears permission immediately; returning from the RHS clears the frame identity. Unproved slots, sets, externally held frames, parent references and indices outside the compact mask use their original canonicalization. The independent audit recomputes the unoptimized root on every direct read.

The third matrix addresses the sampled Graph::subscribe_edges path. It builds the ordinary source using the existing sparse collection algorithm for **forward** dependencies alone. Canonical classes are collected in an inline three-ID vector, sorted and deduplicated. For an update the native algorithm computes the difference with the previous list, removes vacated subscriptions and inserts new reverse dependencies. The reverse index remains an ordered BTreeSet with the original union/repair traversal. The control uses the ordinary per-row BTreeSet and original update implementation. The interventions share the same program, ordered signed roots, allocator, table representation and neural checkpoint.

Both workloads now have measured fixed-phase and full-pass results in this single binary-paired matrix:

| Workload | Treatment | Ordered RHS ms | Repair ms | Full inference ms | Resident API ms |
|---|---|---:|---:|---:|---:|
| 3mm | vanilla | — | — | 892.50 | 1128.45 |
| 3mm | ordinary tree | 312.41 | 104.74 | 2098.41 | 2345.08 |
| 3mm | tree + source inputs | 310.49 | 108.15 | 2140.58 | 2407.32 |
| 3mm | tree + derived slots | 303.14 | 105.79 | 2128.99 | 2400.81 |
| 3mm | tree + derived slots + direct directory | 308.66 | 105.88 | 2127.09 | 2391.37 |
| 3mm | compact forward | 310.76 | 100.29 | 2105.97 | 2350.41 |
| 3mm | compact + slots | 302.22 | 98.17 | 2099.96 | 2359.13 |
| 3mm | compact + slots + directory/memo | 300.97 | 98.54 | 2089.22 | 2343.33 |
| deriche | vanilla | — | — | 1564.51 | 1885.90 |
| deriche | ordinary tree | 581.57 | 171.54 | 3920.27 | 4247.70 |
| deriche | tree + source inputs | 566.97 | 168.50 | 3886.37 | 4237.57 |
| deriche | tree + derived slots | 552.23 | 166.87 | 3804.62 | 4150.86 |
| deriche | tree + derived slots + direct directory | 562.17 | 173.04 | 3854.85 | 4185.07 |
| deriche | compact forward | 555.26 | 156.03 | 3747.02 | 4079.21 |
| deriche | compact + slots | 539.41 | 155.05 | 3688.36 | 4032.62 |
| deriche | compact + slots + directory/memo | 530.32 | 152.50 | 3645.41 | 3976.64 |

The two masks together permit 1,196,239 direct Eq reads on 3mm and 1,962,751 on Deriche. Exactly 1,023,930 / 1,713,634 were original rule inputs and 172,309 / 249,117 came from compiled copies/constructor results. This removes 84% of the previously counted RHS root calls in the ordinary tree path. The static layout occupies 27,936 bytes per program; the runtime keeps one mask for its current source frame.

The compact representation retained exactly 321,407 / 446,700 reverse edges while discarding 29,904 / 49,880 empty forward headers. Reverse insert attempts fell from 476,962 to 409,947 and from 726,595 to 608,405. The original tree additionally paid 413,119 / 615,272 direct parent-presence probes on RHS fields and 70,228 / 128,119 during repair. The compact path instead canonicalizes each collected Eq directly. Two fresh-process RSS measurements per layout gave median peaks of 742.75 → 730.90 MiB and 878.97 → 869.58 MiB. RSS includes setup and complete final export.

On Deriche the combined arm reduced ordered RHS plus repair by about 70 ms and total inference by 275 ms, with all four individual paired elapsed times lower. Search also decreased by 193 ms in that matrix although these changes do not reduce its candidate stream. The sample does not isolate a causal explanation for that timing change. On 3mm its fixed phases saved about 18 ms and two of four total times were lower. All learned arms allocated exactly 229,880 / 452,913 new physical Cells with the same per-RHS allocations and source identities. The measured end-to-end gains do not establish superiority over native vanilla on either program. [Complete paired raw timings, fresh-process RSS, signed winners and subscription inventories](frame-forward.json)

## Reproduction

Use fresh directories for both builds and reports. The first build is the original root-only experiment. The paired builder compiles the separate ordinary forward-tree and compact-forward executables, validates the current-frame union invalidation test in the native release crate and checks that the upstream source manifests agree. The signed family, complete generation, original schedules and physical Cell evidence are identical across each pair. Reproducing on another machine requires a new timing study; the stack sampler uses macOS sample.

```sh
d=benchmarks/pass3-cell-gpu/canonical-batches
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-roots" --roots-only
python "$d/study.py" "$e/NEW-roots/session" "$e" "$e/NEW-root-study"
python "$d/sample.py" "$e/NEW-roots/session" "$e" "$e/NEW-root-samples"
python "$d/summarize_samples.py" "$e/NEW-root-samples" "$e/NEW-root-samples/categories.json"
python "$d/paired.py" "$e" "$e/NEW-forward-pair" "$e/NEW-frame-forward-study"
python "$d/verify.py"
```

The native lifecycle regression includes low and wide slots, large source IDs, overwritten parents, diverging cloned graphs, a live union against a frozen read epoch, thaw and clear. The second regression checks an ordinary source frame before and after a real union and after the original RHS boundary. [Pinned sources, program digests and executable hashes](manifest.json)
