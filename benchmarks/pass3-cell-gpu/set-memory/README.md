# Set values in the Metal Cell executor

The pure GPU executor runs the memory regression from eggcc's `optimizations/memory.rs::load_after_write`. The source generator renders its actual AST, uses the frozen eggcc declarations, and expands the three default schedules followed by the test's six memory iterations. Native egglog passes the original check that printing the loaded value is equivalent to printing 2. The standard compiler schedule uses `mem-simple`. The upstream memory test explicitly appends `memory-helpers` and `memory`. The test source revision is `ae80f82a403c1209fb084b115ee89470c7e66d0e`. [Generator](source.py) · [Counts, endpoint hashes and timing samples](results.json)

## What ran

| Input | Runs | memory-helpers Runs / RHS bindings | GPU RHS bindings | Effective function writes | Spine resumes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original memory test with the three preceding passes | 835 | 4 / 4 | 382 | 111 | 120 |
| Same program plus explicit set consumers | 835 | 4 / 12 | 390 | 114 | 121 |
| Memory phase alone | 39 | 9 / 5 | 111 | 19 | 41 |
| Memory phase plus explicit set consumers | 39 | 9 / 13 | 119 | 22 | 42 |

The original test really fires memory rules but creates no `ExprSet` value. In the upstream memory rules the example producer for `CellHasValues` is commented out. For the paired input, four observer terms seed singleton sets of the test's own expressions and request insert, union and intersection. The original set rules then execute **one insert, two intersections, two unions and three lengths** in both observed schedules. These are actual primitive calls, including repeated rule application; the source control is unchanged. The two input populations have separate results.

## Representation, union and length

An Eq-element set occupies one 63-bit membership mask. Its device dictionary retains the original class handle at each slot. A second array maps each slot to the current canonical bit. Upon an effective union, the GPU redirects slots in the merged class to one bit. Reads normalize masks, cardinality uses population count, and intersection/union operate on normalized masks. Dirty detection follows the original element handles through union epochs. Rows containing a changed set enter ordinary key collision handling, index publication and reevaluation at the original Run. Ordered RHS compares set values lexicographically by their sorted class representatives; the physical bit numbering does not define ordering. All table probing, set algebra, equality updates and scheduling run on Metal. [Device primitives and repair](../executor.metal)

This ABI supports sets of equality-sort elements and at most **63 distinct allocated element slots over a run of the executor**. It supports runtime construction as well as imported sets. Exhaustion or an unsupported signature fails explicitly. The dynamic 64-member control completes on CPU and stops on GPU with capacity fault 20 before declaring success. Slot reuse after union and arbitrary nested containers require a different storage format.

Two independent experiments distinguish the cardinality of a current value from a previously published scalar:

* The dynamic fixture constructs two expressions on GPU and builds a two-element set using empty, insert, set-of and union. For the **same function key and physical row**, Run 2 first writes size 2. Run 3 unifies the two expressions. Run 4 reads the canonical singleton and commits the effective update **2 → 1** under the declared minimum merge. Run 5 makes no further write. The two writes, three Spine resumes and final graph agree with Rust. [Dynamic fixture](dynamic.egg)
* The upstream `ExprSet-length` uses `:no-merge`. Observing the old size at a separate key and first publishing `ExprSet-length` after the union yields 1. If the same upstream key already holds 2, the later attempted write of 1 is a conflict. The Rust and Metal negative controls both finish three Runs and fail on the fourth. [Union fixture](union.egg)

## Time charged to set maintenance

| M3 Max, same-process resident | Full inference median | Estimated union-dependent Set maintenance | Share |
| --- | ---: | ---: | ---: |
| Original upstream workload | 40.12 ms | 6.94 µs | 0.017% |
| Full workload with set consumers | 41.17 ms | 40.11 µs | 0.097% |
| Observed memory phase alone | 4.46 ms | 14.29 µs | 0.320% |
| Imported set, followed by member union | 0.374 ms | 2.36 µs | 0.632% |
| Device-created set and same-key size update | 0.425 ms | 2.59 µs | 0.610% |

These are **paired amplification estimates**, not isolated hardware timestamp intervals. Alias-map maintenance at a union, mask normalization, and checking set-valued columns for dirty members execute at their actual call sites. We compare 2,049 executions with one execution plus 2,048 volatile control iterations on the same device state and divide the paired difference by 2,048. Each arm also runs at 513 repetitions, ten interleaved samples each. The full observed workload gives 41.61 µs at 513 and 40.11 µs at 2,049. The original workload still checks an empty dictionary on effective unions. Repeating an already redirected slot exercises its recheck; it does not re-create the original first write. The numerator excludes ordinary RHS dispatch, base bitwise arithmetic, generic repair, and index publication. The wall-time difference between the two workloads includes extra facts, searches, writes and continuations and measures a different quantity. [Timing driver](timing.py)

## Reproduce

```sh
ws=/Volumes/EggFuseWorkspace
~/.local/bin/eggfuse-job submit --kind compute -- "$ws/bin/run-eggfuse" env PYTORCH_ENABLE_MPS_FALLBACK=0 python benchmarks/pass3-cell-gpu/set-memory/reproduce.py "$ws/experiments/NEW-set-study" "$ws/experiments/rotary-axes-20261119/packed-1703/final.pt" "$ws/experiments/pass3-atlas-integration-20261120/ports-1703.pt"
```

The positive cases check the source Run schedule, ordered RHS, ordered effective writes, actual Spine witnesses, class roots and the full final typed graph. The original, fully observed and both union controls also rerun export from an isolated directory with only the device manifest, compiled arrays, export schema and two frozen reader weights. Rust observers and post-execution class-name alignment never supply an online binding, set member or repair.
