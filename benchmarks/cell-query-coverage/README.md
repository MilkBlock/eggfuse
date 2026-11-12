# Mixed Cell Entry coverage completes with the rule

This checkpoint measures work in the actual standalone Cell CPU, not native
egglog performance. The control is `1cd06be0`, using unchanged frozen programs,
catalogs, release features and four workers. This is implementation four since
the last full timing campaign. **The earlier 9.86% sum-bits / 4.31% Raytrace
four-worker regression has not been shown to be fixed.** These work runs are
not timing samples.

## Opportunity and compiler facts

The preceding Raytrace execution still selected 1,131,289 residual Entry
addresses on the source thread for rules with live cross-stage continuations.
Workers ran their queries, but source enumeration and Sieve filtering preceded
that handoff. The apparent dependency was the exact accepted residual count:
it determines whether the Cell completely covers this rule's matching.

Inspection of the existing compiled switch and legacy reducer separates this
dependency. The selected block, PC, history and query receipts do not depend on
complete/partial coverage. Coverage affects later origin ownership, winner
assembly and training credit. Therefore a scheduled Cell may execute its query
while coverage is pending, provided the exact flag is resolved before selecting
winners or applying effects. Across Runs, the same compiled block, actual result
slots and Shared Entry projections continue at the original visibility boundary.
This uses the last catalog's executed queries; it does not add a new catalog,
runtime fact graph, copy of bindings or producer/consumer subscription lists.

## Connected path and live obligations

An active rule's expansion pivot can now transfer its whole immutable Entry
range when that pivot cannot have an owned Cursor. Existing reverse/shared
traversals and incompatible audit paths retain their previous implementation.
The compiler's existing expansion plan and sealed canonical read view remain
mandatory. Other pivots of the same rule can still use genuine owned Cursors.

The worker enumerates the original range, filters each Entry and continues its
exact query in the same task. Its completion reports the number accepted by
Sieve, including Entries later rejected by delta ownership, joins or guards.
Successful answer count is not a substitute for this coverage evidence.

The existing residual output owner holds one pending coverage summary. Source
residuals and worker acceptances contribute to that summary. The final task
containing this rule resolves coverage in the original retained Cursors before
releasing winner selection; unrelated rules can still run. A range can have
no remaining tasks despite coarse nonempty admission. Such a rule resolves at
its already-ready path, or when its remaining point tasks finish. An all-rejected
residual does not create an empty residual merge job.

Source ordinals, stable winner preference, earliest errors, actual witnesses,
retirement, union-enabled matches, mutable values and Run visibility are retained.
RHS effects still follow their authoritative ordered path. This does not remove
the final Run read fence, shared constructor adoption or ordinary repair.

## Grain and costs

Raw ranges include many cheap Sieve rejections that the old selected range never
enqueued. The first complete work run treated them like full queries: Raytrace
task chunks rose from 78,130 to 181,734 and cumulative event capacity from
202,589,000 to 318,887,744 bytes. That implementation was not retained.

The final scheduling estimate groups eight raw mixed-range rows per query unit,
both when forming chunks and when deciding whether to enter the pool. The
observed range admits roughly one row in eight. This is a bounded scheduling
heuristic, not a compiler proof or a timing-derived optimal ratio. Queries still
execute exactly if all rows pass; dense and different workloads may need a
different grain. No extra filter pass, worker pool or acceptance shortcut is
introduced. Small fragments continue sharing the existing frame/event.

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Source-selected residual addresses | 1,131,289 | 77,685 |
| Mixed raw Entries enumerated/filtered together on worker path | 0 | 8,004,747 |
| Those Entries accepted by Sieve | 0 | 1,053,604 |
| All query chunks / frame borrows | 78,130 | 77,621 |
| Residual query pool calls | 3,009 | 2,895 |
| Residual merge tasks | 29,909 | 29,909 |
| Answer buffer growth/allocation events | 196,365 | 189,499 |
| Event capacity, cumulative bytes | 202,589,000 | 211,929,984 |
| Range descriptor capacity, cumulative bytes | 19,190,304 | 29,665,024 |
| Range fragment capacity, cumulative bytes | 7,726,176 | 9,571,104 |
| Residual answer capacity, cumulative bytes | 303,684,864 | 302,383,200 |
| Column layout preparations | 42,473 | 60,391 |
| Global lookups | 4,027,756 | 4,027,756 |

Total necessary Sieve probes/rejections, including per-rule counts, are exact.
Their worker counters increase because checks move from source to workers;
these are not extra logical filters. The source no longer writes the 1,053,604
accepted addresses, and the range workers borrow the original Entry rows.

New costs remain explicit. There are 45,860 coverage summary entries, 18,804
rule resolutions and 42,899 retained Cursor visits. Of those rules, 5,693 finish
with no accepted residual; three resolve without any remaining task. Earlier
activation calls prepare columns even for ranges that later reject everything.
The fixed expansion/output plan capacity grows 264,000 to 273,312 bytes.
Coverage summaries spill 875,904 cumulative bytes to the heap; their inline
storage is already charged in event capacity. Cumulative capacities are not
allocator traffic or peak memory. Frame counts do not measure utilization.

sum-bits removes 1,362 of 1,381 source-selected addresses. Query tasks increase
888 to 920, event capacity 9,419,616 to 10,065,856 bytes, and column preparations
2,342 to 3,002. Residual pool calls remain 70, merge tasks remain 1,870, answer
capacity remains 1,270,920 bytes, and global lookups remain 14,012. This remaining
small-workload cost is a reason to require the periodic timing gate, not claim
success from the moved Entry count.

All attempts remain under `out/cell-query-coverage`: `initial/` records the first
empty-range assertion failure; `uncoalesced/` records the excessive task version;
`raw-pool-weight/` coalesces tasks but still enters the pool based on raw row
count. The latter has 3,427 / 86 residual pool calls on Raytrace / sum-bits.
The checker validates every complete attempt's exports and records its costs;
these are implementation work runs, not repeated timing selection.

## Validation and reproduction

163 runtime tests and 87 relevant integration tests pass; 20 forced hash/Bloom
collision tests also pass. The new fixture distinguishes rejected ranges from
accepted-but-unsuccessful queries and retires a published Entry before its
consumer Run. It compares full intermediate graph snapshots and ordered matches.
Existing mixed-route fixtures additionally compare actual effect and continuation
origin digests with one, two and four workers. All-feature, sparse-only and
legacy builds pass, as do the README compile/run/single-repeat bench commands.

Frozen sum-bits / Raytrace final exports, all 1,428 / 16,883 ordered Run summaries,
logical effects, query steps, coverage/fallback decisions and Sieve counts equal
the control. Run summaries do not replace intermediate graph checks. The unchanged
native sum-bits acceptance is `pass`, linked by the CPU export hash. Raytrace
remains exact differential validation; its native proof contract is not extended.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

Frozen runtime/program paths and hashes are in the manifest. Use fresh output
directories for compile/run smoke commands:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-query-coverage/semantic-acceptance.json
python3 benchmarks/cell-query-coverage/check.py out/cell-selected-entries out/cell-query-coverage benchmarks/cell-query-coverage/results.json
cargo cell-compile --case sum-bits --output out/cell-query-coverage/readme-program
cargo cell-run --program out/cell-query-coverage/readme-program/program.json --output out/cell-query-coverage/readme-run
cargo cell-bench --program out/cell-query-coverage/readme-program/program.json --repeat 1
```
