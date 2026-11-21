# Store one or two fact entries directly in a speculative Cell

This experiment runs the complete Rust Cell CPU Pass 3 path. Before binding verification a frozen score vector estimates per-rule Cell demand. Within each Run the allocator preconstructs up to 8,192 private records for authenticated groups of candidate lanes. The source verifier publishes an accepted fresh Cell at the original event. Earlier grants, rejected proposals and reclaimed private records retain their private status. Identical input models, group permissions, ordered commits and physical IDs are required for every layout.

Only the ordered map in `Cell.facts` changes. Each entry occupies 64 bytes and stores the keyed native FactState, including its ordinary version and visibility metadata. One and two inline entries increase the Cell header from 96 bytes to 144 and 208 bytes. They use the same sorted keys and serde representation as the original Vec. The first fact beyond inline capacity spills safely into a heap allocation. The original parameter and result slot maps keep their backing.

| Publication mode | Eager Vec | Deferred Vec | Inline one / two |
|---|---|---|---|
| Staging off | Ordinary fact Vec | Same ordinary Vec | Native Cells with inline fact entries |
| Move | Reserve 1–4 fact entries for each forecast, then move the accepted header to the native store | Begin with an empty Vec and allocate on first write | Build the header and its fact storage together, then move the header |
| Resident | Reserve a separate fact Vec and construct the header in a fixed page | Keep the header in a fixed page and allocate facts on first write | Preconstruct headers and inline fact storage together on 64-slot pages and publish them in place |

Vacant capacity carries no fact and grants no authority. The audit records the actual fact-storage address after packing and before any model proposal or verification. It checks the final address after publication. An unallocated Vec is tracked separately. An inline address change at publication is counted as a move, even when its entire source state survives. A resident claim additionally checks the original header address and exercises old-Run native lookups. An unchanged inline address certifies the storage location at publication. Subsequent insertions may overflow it.

## Measurement

Both workloads are held out of the frozen forecast training. Run counts, ordered RHS inputs, effective writes, union events, Spine resumes, schedule and final exported state must match a separate default Cell CPU executable. The learned arms also compare winning single/multi parents, root and nested IDs, the complete physical allocation ledger and actual construction records. Each audit is a separate process. Timing uses a warmed process per layout, alternating rotated order for four full Pass 3 samples. The source timer surrounds the runtime execution. The resident request wall timer also charges graph setup, export, report creation, IPC and in-process deserialization. Fresh-process peak RSS uses macOS `/usr/bin/time -l`, three complete executions per arm and workload. Memory observations have different scopes: cumulative granted fact capacity counts each early reservation; terminal live heap bytes count fact buffers, including unused capacity; RSS includes the rest of the process.

## Held-out results

| Full Pass 3 inference, ms | CG | 3mm |
|---|---:|---:|
| vanilla | 340.07 | 865.08 |
| off-vec | 613.86 | 1,910.80 |
| off-inline1 | 623.66 | 1,885.21 |
| off-inline2 | 607.79 | 1,907.03 |
| move-vec | 654.15 | 1,957.51 |
| move-lazy | 643.74 | 1,967.66 |
| move-inline1 | 661.57 | 1,976.82 |
| move-inline2 | 665.88 | 1,982.49 |
| resident-vec | 646.52 | 1,942.36 |
| resident-lazy | 652.72 | 1,922.85 |
| resident-inline1 | 639.37 | 1,895.90 |
| resident-inline2 | 643.47 | 1,896.60 |

A resident one-entry layout replaces 97,293 CG and 232,796 3mm speculative fact-buffer allocations. Cumulative early heap capacity falls from 17,770,240 and 43,078,528 bytes to zero. During the most expensive Run the staged header-plus-fact capacity falls from 1,133,640 to 624,792 bytes on CG and from 2,601,152 to 1,376,256 bytes on 3mm. The deferred Vec also eliminates early allocations, with still smaller headers. Each of the 59,752 / 137,864 resident published Cells preserves its authentic inline fact address. Each moving inline Cell changes that address at publication. The source audits cover all 2,896 / 4,260 Runs and 131,371 / 294,917 RHS bindings.

One resident inline lane beats resident eager Vec on the median by 1.1% / 2.4%. It wins 2/4 CG pairs and 3/4 3mm pairs. Full warm-process request medians are 755.84 → 740.17 ms and 2,181.25 → 2,116.14 ms. The moving layout slows on both with the same inline capacity. The no-staging learned run using inline1 takes 623.66 / 1,885.21 ms. Preconstruction and named publication still cost time on these inputs even when the actual accepted header and first fact port stay in place.

| Final live ordinary graph, staging off | CG | 3mm |
|---|---:|---:|
| Cells / stored fact entries | 35,238 / 34,736 | 94,210 / 92,814 |
| Live fact heap buffers, Vec / one / two | 27,816 / 6,387 / 1,544 | 75,190 / 15,532 / 4,376 |
| Live header bytes plus fact heap capacity, Vec / one / two | 10,634,816 / 6,220,512 / 7,855,840 | 28,554,688 / 16,376,352 / 20,977,824 |

A second entry saves roughly 0.62 MB / 1.43 MB more terminal heap capacity while adding 2.26 MB / 6.03 MB to live headers alone. Resident pages also retain 40,721 / 74,367 holes. At one inline lane those holes occupy 6.84 MB / 12.49 MB of page slots through the final Run. Live header bytes omit hash table spare capacity, page holes and metadata, transitive state and allocator overhead. [Full paired source and placement receipts](results.json)

| Fresh-process peak RSS (MiB) | CG | 3mm |
|---|---:|---:|
| off-vec | 461.36 | 740.84 |
| off-inline1 | 460.38 | 740.73 |
| move-vec | 461.30 | 744.73 |
| move-lazy | 462.59 | 736.23 |
| move-inline1 | 461.14 | 740.69 |
| resident-vec | 468.80 | 753.38 |
| resident-lazy | 469.62 | 757.48 |
| resident-inline1 | 468.39 | 749.81 |
| resident-inline2 | 473.22 | 765.70 |

Changing resident Vec to one inline lane saves 0.41 MiB of full-process peak RSS on CG and 3.56 MiB on 3mm. Early fact-buffer allocations are a large and removable source of allocation calls. The wider headers, partially occupied pages and the rest of the engine limit how much that changes process memory. Resident inline2 increases peak RSS on both workloads. [All individual RSS samples](rss.json)

## Reproduction

Use the shared frozen program, plan and model bundles named in the pair-source profile loader and the allocator-matched default CPU binaries. Run native builds and studies through the repository FIFO. The checked-in text receipts suffice to verify the reported audits without rerunning inference.

```sh
d=benchmarks/pass3-cell-gpu/inline-fact-lanes
python "$d/build.py" "$EXP/inline-build"
python "$d/study.py" "$EXP" "$EXP/inline-build" "$EXP/inline-study"
python "$d/rss.py" "$EXP" "$EXP/inline-build" "$EXP/inline-rss"
python "$d/verify.py"
```
