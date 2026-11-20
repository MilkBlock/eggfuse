# Deferred Cell compute requests on a resident Rust graph

A multi-parent token contains sealed typed parent references and the compiler supplies its deterministic verification suffix. At a source rule occurrence, the CPU proposer seals all independent choices before examining the suffix. The transaction buffer admits up to its width in original proposal order. Eligible suffixes contain only unique table reads and the supported pure integer operations and comparison guards. Inside each microbatch the verifier evaluates the first instruction for all surviving lanes before advancing them together. Each lane retains its own checked source receipts, eligibility epoch and root recipe. A failing predicate cancels that lane's remaining requests.

A positive or negative lookup can serve several lanes at the same instruction if they have identical integer or e-class operands. The table, result type and primitive program are fixed by that instruction. Learned parent addresses can optionally share one source-row decode in the same batch. This retains the per-lane table, arity, literal and unified-variable checks. The batch borrows one immutable graph and drains at the end of the current rule occurrence even when it is underfilled. Later writes, min merges, unions, rebuilds and consumer Runs use the original executor and order. Mutable float interning and unsupported functions keep the existing verifier. Each instance retains independent provenance, even when two different addresses refer to the same e-class.

The immediate control is the real CPU proposer with one shared-score row, checked slots and packed tied projections with incremental frame maintenance. Width one controls for changing the verifier loop. Width eight isolates deferral. Additional arms share suffix results, optionally share parent decodes and compare width 32; the table-only arm keeps arithmetic local. A separate streaming control keeps exactly the same eight-packet cache and parent sharing but executes each lane as soon as it arrives. It must perform the same reads and compute the same values as the delayed eight-packet version. This identifies any independent benefit from waiting. Both providers disable residual search. All the cost of building the local queues, checking the source and committing the actual graph is charged to resident inference. A separate instrumented run times collection from the first checked lane to drain and the flush body. These totals are outside the benchmark samples; interpreting collection as a blocked CPU would overstate its cost since other parents are being checked at that time.

Full audit hashes the input parent addresses, Run, epoch, watermark and typed operands as well as every exact result, including absent rows and failed scalar guards. Each source instruction has its own ordered digest so changing the interleaving between instructions can preserve its logical sequence. Every arm must match the original immediate verifier.

## Complete resident Pass 3 measurements

Medians in milliseconds from six rotating forward/reverse timed blocks per workload/seed after warm-up. The default CPU is a separately built original executable. In *stream* and *defer* the cache scope and budget are identical, including parent-address sharing. The deferred arm executes a wave of the same operation over multiple lanes.

| Workload / seed | Vanilla | Immediate | Stream / 8 | Defer / 8 | Defer / 32 | Avoided parent reads / table reads / primitive evaluations at width 8 |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits/1703 | 21.73 | 38.98 | 38.50 | 38.94 | 38.88 | 4,331 / 498 / 2,031 |
| sum-bits/1709 | 21.60 | 38.60 | 38.83 | 39.49 | 38.49 | 4,428 / 530 / 2,046 |
| dot-product/1703 | 19.42 | 41.21 | 42.19 | 42.97 | 40.99 | 15,192 / 7,742 / 1,955 |
| dot-product/1709 | 19.59 | 42.21 | 41.41 | 41.92 | 42.63 | 13,790 / 7,792 / 1,959 |
| jacobi-1d/1703 | 112.60 | 313.56 | 317.54 | 315.86 | 316.34 | 188,118 / 31,645 / 16,859 |
| jacobi-1d/1709 | 116.45 | 338.24 | 340.15 | 329.51 | 332.36 | 257,718 / 30,833 / 16,944 |

The broad deferred policy saves source reads on every case. Wall time at width eight moves in opposite directions across workloads/seeds relative to immediate execution. In an independently instrumented Jacobi/1703 execution, the width-eight flush bodies together took 11.85 ms. The 13.81 ms spent from first ready lane to flush also includes useful work collecting other parents. These intervals are descriptive and are not a portable speed limit. The raw neural proposal stream, positive and negative typed request receipts, physical ID attribution and all ordered source endpoints match.

Reproduce from the repo root with the frozen bundles and vanilla executable prepared using compact-recipes and the tied signatures from baked-port-codes. Use a fresh directory for each output.

```sh
python benchmarks/pass3-cell-gpu/request-transactions/build.py "$EXP/txn"
python benchmarks/pass3-cell-gpu/request-transactions/measure.py "$EXP/txn/session" "$EXP/vanilla" "$EXP/bundles" "$EXP/lookup" "$EXP/txn-six" --seeds 1703 1709
python benchmarks/pass3-cell-gpu/request-transactions/verify.py "$EXP/txn-six/results.json"
```

## Opportunity in min-merged numeric effects

Offline replay of the earlier numeric-projection trace supplies a separate bound for the write side. Eligible contiguous, same-rule, same-Run occurrences with an actual argument receipt are grouped. At width eight, 51/118 sum-bits and 112/201 dot-product issued numeric computations repeat identical inputs; only 3 and 10 write keys repeat. These cohorts come from 291/928 captured numeric outcomes within 7,265/6,704 source RHS, respectively. Among eligible Concat size receipts there are zero repeated arithmetic inputs (9/8 receipts). The two seeds agree on these counts. Each hypothetical reuse retains all ordered writes and individually checks the source candidate, previous visible value and new visible value. These are opportunity counts from a frozen GPU trace; online CPU timing above must be measured independently.

```sh
python benchmarks/pass3-cell-gpu/request-transactions/min_replay.py "$EXP/numeric-projection-study" "$EXP/min-transactions.json"
```

## Larger holdout and peak resident memory

On conjugate-gradient/1703 with the same policy and allocator, immediate was 1,452.40 ms and delayed width eight with full sharing was 1,434.51 ms (faster in four of six paired blocks). The equal-budget streaming arm took 1,474.39 ms, width 32 took 1,453.13 ms, and true vanilla took 364.73 ms. Width eight eliminated 898,495 parent decodes, 49,418 table reads and 41,726 scalar evaluations. This is a single-seed larger holdout. All original source and certificate identities, positive and negative requests and physical ownership were verified independently. [Raw measurements](conjugate.json)

Fresh subprocess peak RSS uses Darwin's maximum resident set size and includes program load, inference and export; the OS page cache was not purged. Values below are three-run medians in MiB. Fresh wall measurements include the different report sizes returned by each backend. [Per-process samples](footprint.json)

| Input | Vanilla | Immediate | Stream / 8 | Defer / 8 | Defer / 32 |
|---|---:|---:|---:|---:|---:|
| sum-bits | 285.42 | 277.12 | 277.30 | 277.27 | 277.27 |
| dot-product | 308.64 | 300.84 | 300.92 | 300.84 | 300.91 |
| jacobi-1d | 353.41 | 381.38 | 381.50 | 381.45 | 381.53 |

The high-water mark includes more than the local request buffers. There is no measured material peak-RSS saving from changing the batch size on these inputs.
