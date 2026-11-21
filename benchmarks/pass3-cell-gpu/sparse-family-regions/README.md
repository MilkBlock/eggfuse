# Sparse public span postings for compound learned signatures

> **Metric clarification.** Sparse postings change how the sender finds occupied keys and how much receiver work a region triggers. Ratios per signed family packet and per charged prototype are transport and work diagnostics. The groups provide no explicit-parent FEPT measurement. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

The previous compound sender never walked the Cartesian product of left span prototypes and right slices. For each 32-row left interval it formed the occupied learned keys, performed a right-histogram lookup per key, tested the maximum epochs, then determined the sizes of the surviving right windows. This repeated an absence or a stale cutoff for many spans sharing the same key.

The new sender inverts the left marginal by full learned prototype. Each posting records a span, its multiplicity and its maximum row epoch. Within a key, postings are sorted by that epoch. The sender intersects the smaller of the two *global* occupied-key dictionaries with the other. A key absent from the right excludes all its left spans in one step. For a shared key, if the right maximum is stale, a lower-bound search selects the eligible suffix of left-span postings. The sender places survivors back into their original span and sorts the few active learned keys there. Both implementations then call the **same** packetizer. The full order, length prefixes and bytes of its generated packet stream are hashed in the detailed audit.

The cached left directory requires the same public source role, span size, exact table generation, union generation and compound-projection identity. Its 8 MiB budget includes posting vector capacities and map entry-capacity estimates. Map control bytes, allocator padding, temporaries and the receiver indexes are excluded from that accounting; complete native timings include them. The current right marginal already contains immutable prototype cardinalities and maximum epochs in both arms. Materializing right-row address lists for the sender would be redundant. Actual ordered right membership is independently reconstructed by the receiver.

**Definitions for both arms.** The emitted-packet denominator charges all remaining singleton and explicit multi-parent roots, every emitted family (including later rejects) and all selected child packets. The logical strict denominator additionally charges one for each absent or fully stale *span/prototype* in the abstract model. The executed-negative denominator instead additionally charges every actual hash miss or accepted-key cutoff that returned no live region. A negative return may cover one span or many. Full query-work counts all lookups, maximum-epoch tests and binary-search predicate calls, including successful ones. The expanded accounting separately includes left directory construction key updates and original right histogram input rows. These are heterogeneous event counts. The frozen baked Q/K encoder still chooses the same signatures; the sparse selector is deterministic and never invokes an additional learned policy.

## Native results

| Program | Metric | Per-span histogram probes | Indexed span postings |
|---|---|---:|---:|
| sum-bits | Occupied-key lookups | 65,176 | 40,666 |
| | Hash misses / no-fresh-region returns | 29,167 / 31,615 | 6,567 / 29,873 |
| | All query predicates, including binary-search steps | 101,185 | 106,978 |
| | Left rows indexed / right histogram build rows | 77,106 / 46,934 | 32,065 / 46,934 |
| | Origins per logical-strict / executed-negative charged unit | 0.038383 / 0.038383 | 0.038383 / 0.058798 |
| | Resident inference median | 42.31 ms | 42.59 ms |
| 3mm | Occupied-key lookups | 3,655,283 | 2,141,809 |
| | Hash misses / no-fresh-region returns | 1,349,668 / 2,104,269 | 303,480 / 1,668,238 |
| | All query predicates, including binary-search steps | 5,960,898 | 6,008,567 |
| | Left rows indexed / right histogram build rows | 3,997,135 / 4,507,187 | 1,764,805 / 4,507,187 |
| | Origins per logical-strict / executed-negative charged unit | 0.023905 / 0.023905 | 0.023905 / 0.038706 |
| | Resident inference median | 2,485.85 ms | 2,547.10 ms |

**Actual neural work and signed packets were identical.** On 3mm the family sender made 5,332,979 frozen model-port lookups in each arm (60,981 on sum-bits). These are calls to the baked multi-view encoder table. No online weight multiplication or separate learned negative-region classifier ran. The full deterministic stream was 40,264 family packets / 3,973,660 bytes on 3mm, and 1,542 packets / 131,716 bytes on sum-bits. The length-delimited SHA-256 of every actual packet was identical in order. Including all other emitted roots and selected children, external packet yield remained 0.219480 / 0.288517 on 3mm / sum-bits. Both arms retain every unsuccessful emitted action in that denominator.

On 3mm, 1,108 immutable left dictionaries were built and 4,222 reused. Across builds they stored 1,586,056 span records, with 4,659,008 peak estimated payload bytes. The receiver saw exactly the original 201,346 nonempty candidate regions. The indexed method paid 2,028,429 binary-search comparisons, 152,422 multispan posting sorts across index construction and 18,013 per-span list sorts while restoring canonical issue order. The control's B-tree comparisons, sort internals and map control bytes have no per-comparison charge in the table. Including emitted packets, all measured query predicates, left construction input rows and right histogram input rows gives 14,887,391 / 12,702,730 counted events on 3mm and 234,552 / 195,304 on sum-bits. The operation types have different costs.

A single diagnostic 3mm pass measured 363.56 / 354.16 ms in the sender and 676.36 / 733.89 ms in the receiver for per-span / indexed. Four fresh-graph resident timing pairs, rotated after warmup, favored the indexed arm in one pair. The tested change reduces repeated deterministic hash work; it does not establish fewer neural choices or a full-inference speedup. Source parity includes every Run's RHS, writes, Spine and union, actual root and child identities, exact expanded multi-parent stream, ordered constructor births and final graph. Both arm ledgers match the independently archived compound experiment. The sparse receiver also rejected the altered arithmetic signature on both workloads. [Full samples, packet digest and all work counters](results.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/sparse-family-regions
python "$d/build.py" "$EXP/sparse-family-build"
python "$d/study.py" "$EXP" "$EXP/sparse-family-build/session" "$EXP/sparse-family-study"
python "$d/verify.py"
```
