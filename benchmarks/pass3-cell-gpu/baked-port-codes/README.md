# Offline specialization of the learned port projection

The multi-parent CPU proposer reads sixteen binary features per view and emits ten query bits and ten key bits. Bake evaluates the trained Rust scoring function once on every possible input. All instances then share one 262,216-byte immutable table per checkpoint. Its header binds both the weight digest and the payload digest. An independently mutated header or payload was rejected. The table contains no source rows or expected winners.

The table arm still performs the source-ordered neural shortlist. The column arm retains computed codes for the lifetime of the indexed source version. The packed arm requires radius zero and concatenates the view signatures in one bucket key. It proposes **all** matching bucket addresses, including collisions. Rust still checks the original parent tuple, exact suffix and visible version and issues actual root and child recipes. This experiment measures a research overlay executing real Pass 3 in the Rust Cell runtime.

## Complete resident inference

Seed 1703, one tied Q/K view, radius zero. The tied Q/K projection shares 160 scalar coefficients. This count applies only to that head. The other policy heads still run. Timings are medians of eight interleaved executions in ms after warm-up, including proposal generation, exact checking and actual source execution. Initial file I/O, table construction, audit and final graph export are outside this timer. The vanilla binary uses the original default-feature Rust executor with the same allocator and input.

| Workload | Vanilla | Dense learned projections | Same projections from table | Table + direct signature bucket |
|---|---:|---:|---:|---:|
| sum-bits | 21.5 | 68.6 | 62.8 | 58.3 |
| dot-product | 18.7 | 66.7 | 62.9 | 55.7 |
| jacobi-1d | 111.7 | 574.8 | 548.6 | 481.8 |
| conjugate-gradient | 369.2 | 2868.8 | 2729.7 | 2445.7 |

Separate six-way controls cover asymmetric three-view radius-two and tied one-view radius-zero policies, seeds 1703 and 1709. Changing weights, view count or radius can change the proposal stream. Within each family, the table implementations preserve raw proposal and physical identities. Every tested arm reproduced ordered RHS, effective writes, Spine, union, schedule and final graph. Checkpoint loading and 65,536-entry Bake timings are recorded separately. The two larger workloads were frozen in the compact recipe study before observing their results.

A separate matched three-view run uses the same tied checkpoint with three salted inputs and compares dense scoring, table-backed scoring and packed zero-radius lookups. On conjugate-gradient, the three-view times were 2,536.9 / 2,348.1 / 2,094.6 ms against vanilla 360.5 ms. The other packed medians were 58.5 / 55.0 / 461.9 ms on sum-bits, dot-product and Jacobi. One-view and three-view measurements come from separate sessions. The within-family source and candidate identity checks run independently.

## Reproduction

First prepare the frozen workload bundles and original vanilla programs using the adjacent compact-recipes study. Set EXP to a writable experiment root. Run from the EggFuse worktree with Python and NumPy available. Choose fresh output directories.

```sh
python benchmarks/pass3-cell-gpu/baked-port-codes/build.py "$EXP/baked"
python benchmarks/pass3-cell-gpu/baked-port-codes/measure.py "$EXP/baked" "$EXP/vanilla" "$EXP/bundles" "$EXP/lookup"
python benchmarks/pass3-cell-gpu/baked-port-codes/measure.py "$EXP/baked" "$EXP/vanilla" "$EXP/bundles" "$EXP/packed" --packed --seeds 1703 --cases sum-bits dot-product jacobi-1d conjugate-gradient
python benchmarks/pass3-cell-gpu/baked-port-codes/measure.py "$EXP/baked" "$EXP/vanilla" "$EXP/bundles" "$EXP/three" --packed --packed-views 3 --seeds 1703 --cases sum-bits dot-product jacobi-1d conjugate-gradient
python benchmarks/pass3-cell-gpu/baked-port-codes/check_results.py
```
