# Work-weighted ceiling for choosing existing Cell blocks

On the two previously accepted Metal Pass 3 traces, perfect coverage by the available entry blocks captures little residual DFS. Eliminating clean repair inspections offers a much larger opportunity, **conditional on supplying the affected-row directory**. The notification experiment pays for that directory on the device and reaches the clean-row bound on both traces. All arms preserve input epochs, boundary reads, ordinal RHS, writes, cursor priority, external publication, collisions and the final graph. No learned policy was trained. [Work counters and credits by leaf and shape](results.json) · [Resident timing samples](timing.json)

## Which catalogs apply

Sum-bits has 32 entry leaves and a 65-state iterative switch including its initial state. Its archived CPU trace applies 413 composed units among 1,428 applied units. The actual terminal programs reuse RHS evidence; none supplies a certified direct query receipt. The CPU evidence includes 252 reused lets, 155 sets and 155 no-op unions. These do not imply permission to skip a future Run, effective write, or unmatched join. The full GPU trace has 2,098 Spine resumes.

The archived dot-product program has **zero native catalog leaves and no iterative switch**. Its native block-selection ceiling is zero. We separately transfer 30 of the 32 sum-bits leaves after checking exact typed rule equality (including its effects), table schemas and dot-product's own complete-key stage-entry certificates. All dot-product entry figures below are for that transfer. It has 1,835 GPU resumes.

Both program artifacts have an independently checked repair schema catalog covering 241 tables and 178 shapes. Scope is scalar constructor fields. Functions and container keys keep ordinary repair. Historical single-position owner variants tied to a different artifact are excluded: for example the older sum-bits study at commit `f253e513` had 3,034 resumes and a different program digest. Its 459 single-position opportunities among 1,779 dirty facts cannot be added to this replay's physical row count.

## Fixed source schedule

| Operation count over the full workload | sum-bits | dot-product |
| --- | ---: | ---: |
| Baseline residual DFS iterations, including backtracking | 13,146,825 | 15,044,873 |
| Avoidable DFS iterations owned by existing certified entry blocks | **2,605 (0.0198%)** | **2,119 (0.0141%)** |
| Baseline Spine seed row visits | 76,812 | 59,593 |
| Ideal ceiling on seed visits avoidable with an exact eligible-anchor directory | 51,395 | 40,001 |
| Seed visits actually saved with a maintained cursor list | 23,789 | 19,666 |
| Baseline repair row inspections | 392,115 | 314,234 |
| Out-of-catalog inspections that must remain | 105,082 | 88,741 |
| Affected in-catalog inspections retained, including key changes | 2,803 (1,286 key) | 1,147 (513 key) |
| Clean in-catalog inspections avoidable with affected-row notification | **284,230 (72.5%)** | **224,346 (71.4%)** |
| Actual inspections with notification | 107,885 | 89,888 |
| Remaining source Runs / device source-kernel calls | 1,428 / 4,284 | 1,535 / 4,605 |
| Source-kernel calls saved by choosing these templates | **0** | **0** |

**Entry ceiling.** A free selector claims a residual branch at the earliest occurrence of a qualifying catalog pivot with a live published anchor at the correct watermark. The independently executing Spine route still checks the whole suffix, including port lookups. The tally arm propagates the earliest eligible owner down the baseline DFS and prices every suppressed iteration exactly once. The selected arm physically cuts those branches. Its measured difference must equal the sum of the per-leaf credits. Separate seed credit assigns one unit per visited seed; the ceiling retains every live eligible seed. The implemented per-table/shard list invalidates by a conservative refresh epoch, so it still checks stale or retired rows and the stopping boundary. It pays 5,611 / 4,696 cursor refreshes and 33,856 / 25,152 list-head probes. For example sum-bits rule 137 saves 199 DFS steps and 3,988 seed visits. They are different costs. [Replay and eligibility tests](replay.py)

**Repair ceiling.** Merely predicting a variant after encountering a dirty row saves **zero discovery scans** in the current global scanner. The oracle is allowed to skip only clean rows of supported shapes and must still inspect each affected row, do exact whole-key collision checks, perform forwarding and notify external readers. A second run builds real reverse-incidence bitmaps on GPU as constructors arrive. Each union notifies subscribers to its losing root and propagates their memberships to the survivor. The scanner visits dirty and out-of-catalog rows in original physical order, checking for additional notifications after every collision. On these traces it reaches the counted ceiling exactly. The additional directory reserves 33,943,552 / 33,959,936 bytes. The device performs 10,122 / 8,546 registration operations, 94,578 / 49,420 notification-word inspections, and 132,431 / 106,368 scan-mask tests. A skipped row is not a free operation.

**Submissions.** Only 35 of 527 nonempty sum-bits Runs and 38 of 546 dot-product Runs have every winning binding supplied by a catalog route. These are necessary candidate counts for moving *all* positive work of such a Run; they do not certify absent residual obligations. The catalog does not contain a whole-Run closure/visibility certificate. The three named source kernels and one PyTorch clear stay in place each scheduled iteration in this replay. The fixed online budget issues 2,048 iterations including trailing no-ops. Here “submission” counts source kernel launches, not a guessed number of Metal command buffers. Independently, the existing generic 16-Run batching experiment can issue 128 batch launches at the same budget; its earlier timings were 25.78 / 34.55 seconds. This is a separate change in execution granularity and earns no template-selection credit.

## End-to-end check and the learning objective

| Uninstrumented resident Pass 3, median of six interleaved orders | sum-bits | dot-product |
| --- | ---: | ---: |
| Normal split executor | 895.77 ms | 934.98 ms |
| Choose all eligible blocks and maintain cursor lists | 918.53 ms | 966.05 ms |
| Also register and deliver affected-row notifications | **604.99 ms (1.48×)** | **715.13 ms (1.31×)** |

The added registration and notification work occurs during inference. Setup and restoring the original resident tensors are outside this timing. Work counting and per-leaf attribution are off. Separately, every instrumented replay is checked against the original Cell CPU trace at **all 1,428 / 1,535 source boundaries**. These are standalone Cell measurements on M3 Max. The numbers are conditional on these inputs, catalogs, traversal and observation boundaries; they are not an upper bound for a new scheduler or a different Bake library.

For a future selector, store a credit vector per eligible instance (disjoint avoided DFS steps, seed visits, repair-row inspections; retained reads, notifications, and dispatches). Within each work class, weighted coverage is the sum of the **actual avoidable work selected** divided by the sum available to the oracle. Across classes, use calibrated marginal times and subtract validation, model and notification costs before forming a scalar score. Do not sum DFS visits and repair inspections as though each took the same time. For example, repair shape 20 accounts for 26,368 avoidable sum-bits row visits, while shape 56 accounts for 19,018 on dot-product. These results favor improving how repair discovers subscribers before investing in a policy trained on leaf-hit frequency.

```sh
ws=/Volumes/EggFuseWorkspace
base="$ws/experiments/pass3-atlas-integration-20261120"
weights="$ws/experiments/rotary-axes-20261119/packed-1703/final.pt"
~/.local/bin/eggfuse-job submit --kind compute -- "$ws/bin/run-eggfuse" python benchmarks/pass3-cell-gpu/block-ceiling/replay.py "$base" "$weights" "$ws/experiments/NEW-block-ceiling"
~/.local/bin/eggfuse-job submit --kind compute -- "$ws/bin/run-eggfuse" python benchmarks/pass3-cell-gpu/block-ceiling/timing.py "$base" "$weights" "$ws/experiments/NEW-block-timing"
~/.local/bin/eggfuse-job submit --kind compute -- "$ws/bin/run-eggfuse" python benchmarks/pass3-cell-gpu/block-ceiling/native.py "$base" "$weights" "$ws/experiments/NEW-native-acceptance"
```
