# Saved native-version comparison

Completed 288 / 288 attempted inputs; full corpus: 288.

| Inputs | Native 2.0 (s) | Native 3.0 (s) | 2.0 / 3.0 |
|---|---:|---:|---:|
| 1 | 30.295 | 22.490 | 1.347 |
| 2 | 63.017 | 44.925 | 1.403 |
| 3 | 47.548 | 30.391 | 1.565 |
| all | 140.860 | 97.805 | 1.440 |

Three-pass workload geometric mean (2.0 / 3.0): **1.040**. 3.0 is faster on 49 / 96 workload totals.
Small differences are observations, not claims of statistical significance.

| Workload | Pass | Native 2.0 (ms) | Native 3.0 (ms) | 2.0 / 3.0 |
|---|---:|---:|---:|---:|
| bril/core/sum-bits.bril | 3 | 40.686 | 50.633 | 0.804 |
| raytrace/raytrace.rs | 3 | 23643.008 | 11263.352 | 2.099 |
| bril/core/sum-bits.bril | 1 | 25.926 | 33.100 | 0.783 |
| raytrace/raytrace.rs | 1 | 4547.346 | 2804.408 | 1.621 |
| bril/core/sum-bits.bril | 2 | 12.458 | 18.950 | 0.657 |
| raytrace/raytrace.rs | 2 | 12604.992 | 7517.125 | 1.677 |

For these 288 inputs, the unchanged native-2.0 binary's total is 1.004 times the earlier campaign total. Earlier Cell inference was 53.789 s. Current 3.0 / earlier Cell is 1.818; **this crosses campaigns and is not a paired 3.0/Cell measurement**.

Timing success does not certify final-state or extracted-program equivalence. See README.md for version, allocator and timing boundaries.
