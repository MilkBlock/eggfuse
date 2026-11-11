# Parallel Cell Entry filters: real coverage, insufficient heavy work

Control source: `50316626`. Apple M3 Max, 16 logical CPUs. This is the
**standalone Cell CPU**, not native egglog. The goal of keeping workers busy
is **not achieved**. The implementation remains opt-in and disabled by default.

## Opportunity and actual takeover

The preceding full-Raytrace execution recorded 10,916,139 Sieve probes on the
coordinator. The compiled Cell query already supplies each Entry's complete
ordered necessary conditions. Those conditions and the current fingerprint
directory are immutable during source-Run matching. This is enough to move
filter evaluation into the existing query-worker pool without creating another
query representation, fact graph, index or producer subscription.

`parallel-entry-filters` plus `--parallel-entry-filters --query-workers N`
enables the path. At least two workers are required. Only global completion and
raw delta batches are admitted, after existing reverse/selection paths decline.
The runtime borrows only the plain fingerprint map and shared summaries; the
graph's `Rc` owners and lazy column caches never cross threads. Missing keys
pass to the exact matcher exactly as before. A stale source index declines the
parallel route. Fingerprint/Bloom membership still does not prove a full match.

The ordered delta witnesses become one temporary vector of `(witness, keep)`.
Workers evaluate the same guards, stop at the same first rejection, and write
disjoint flags. Ordered compaction retains the original source order. The
coordinator **omits the original per-row Sieve checks** for these candidates;
it does not repeat them after joining. Guard counters are merged once. Exact
query evaluation, delta ownership, visibility, winner selection, RHS and repair
retain their authority. No logical match is called a committed mutation.

There is no cross-Run block switch in this change: mutable reads from a later
Run cannot be pulled into this snapshot. Existing instances/Entries retain the
cross-stage data. The new work is scheduling existing template conditions, not
an expanded Ripsat completion proof or new Bake credit.

## Complete Raytrace results

The same normal release binary uses
`cell-absorption,view-ports,storage-metrics,parallel-entry-filters`. Absorption,
repair ports and Entry publication are enabled in every lane. No allocation
instrumentation or `CELL_CPU_PROFILE` is enabled. Each lane has one warmup and
three interleaved independent processes. All samples, including a 14.62-second
point4 outlier, are retained. Background system/application activity was
present; no specific cause is established for that outlier.

| Configuration | Median inference | Individual measured inference seconds |
|---|---:|---|
| Serial | 5.652 s | 7.595, 5.652, 5.617 |
| Existing point queries, 4 workers | 5.757 s | 14.618, 5.675, 5.757 |
| Point queries + filters, 4 workers | 5.756 s | 5.793, 5.699, 5.756 |
| Point queries + filters, 8 workers | 6.245 s | 6.245, 6.430, 6.229 |

Four-worker activation does not establish a speedup: the paired ratio is
0.9999 with bootstrap interval [0.3963, 1.0042]. Eight versus four workers has
a paired ratio of 1.0821 [1.0780, 1.1283] in these samples. This is also **not
pure thread scaling**: admission requires more than
`workers * max(query_grain, 256)` rows, so eight workers admit fewer batches.

Four-worker filters execute 5,606,010 probes over 5,589,338 Entry witnesses in
2,390 batches / 23,039 chunks; 619,113 candidates remain. Eight-worker filters
execute 3,782,495 probes in 1,153 batches. Total ordinary Sieve probes and
rejections remain exact across configurations; work moved, it was not removed.

For the first measured four-worker run, preparation takes 0.0191 s, pool calls
0.0647 s, and compaction 0.0058 s. These are included in normal inference time.
Warmup task-body wall residence summed across workers is about 0.10 s; it is
not CPU time. Millions of these probes therefore represent a small portion of
the remaining work. Candidate capacities sum to 202,063,872 bytes; peak single
candidate-buffer capacity is 786,432 bytes. These are payload-capacity measures,
not allocator totals/RSS. Chunk-result records and pool bookkeeping also cost
space/time; there are no per-row timers or atomics.

## Remaining bottleneck and next structural step

A separate five-second `sample` capture begins at the first Run. The four
workers wait in `__psynch_cvwait` for 1,773 / 1,782 / 1,790 / 1,791 of 1,823
samples each (97.3%–98.2%). These are wall-stack samples, not CPU percentages.
The diagnostic preserves the complete timed graph and ordered Run signature.
Progress logging contributes 99 main-thread inference samples and is not product
work; optimized inlining and the partial window limit attribution.

Of 1,820 main-thread inference samples, inclusive counts include:
`matches` 717, `publish_finished_tables` 388, `Scheduler::batches` 370,
`FreeJoin::admit` 178, residual `Frame::step` 148, `Columns::put` 107.
These overlap and must not be added. Four-worker phase medians still include
2.416 s search, 1.621 s RHS and 1.199 s query update.

The next priority is transferring **candidate selection plus full residual
query enumeration** through the existing Cell Query, preserving source order
and the same Run read boundary. Currently `query_worker_batch` rejects expansion
queries (`point_tables == None`) and `FreeJoin::admit` still constructs domains
on the coordinator. That boundary leaves substantial work outside workers.
Another grain adjustment or more filter threads cannot address it. Worker
read views should borrow existing membership/fields without cloning whole
indexes or sharing lazy `Rc` caches; existing absorption and prefix takeovers
must retain their proofs and savings. RHS/publication parallelism remains a
separate required step toward sustained full utilization.

## Acceptance and reproduction

- 28 integration tests pass. A new native-checked 4,096-entry fixture compares
  every Run snapshot, ordered bindings and all guard counts under serial,
  two-worker and four-worker execution through late input, union, deletion and
  recreation; it asserts that the new route actually executes.
- All 16 complete timing processes and the independent profile have identical
  final states and ordered logical/executed Run signatures (16,883 Runs), plus
  identical constructor requests, updates, unions and created facts. Raytrace
  evidence remains relative, not an independent native proof.
- The frozen pre-change binary and candidate have identical sum-bits states;
  the unchanged native choice validator returns `pass` / exit 0 for the candidate.
- Runtime unit tests, minimal/combined-feature checks and README
  compile/run/bench (repeat 1) pass. README smoke timings are not performance
  evidence. The baseline tag is unchanged.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,storage-metrics,parallel-entry-filters
# Freeze this executable before any other build; use new output directories.
python3 benchmarks/parallel-entry-filters/measure.py BINARY RAY_PROGRAM ROOT/timing
python3 benchmarks/raytrace-thread-bottlenecks/profile.py ROOT/manifest.json ROOT/timing/samples.json ROOT/profile --lane filter4 --duration 5 --interval-ms 2
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/parallel-entry-filters/collect.py ROOT RESULTS.json
```

Use the frozen `cell-fixed-reads` programs identified by the result hashes.
Prepare sum-bits exports under the existing acceptance contract; `sum-off`
uses the pre-change binary and `sum-on` enables the new path. Raw binaries,
exports, logs and samples remain ignored under `out/parallel-entry-filters`.
The committed results retain every timing sample, worker work, semantic hashes,
and sampled main-thread attribution. No full-utilization claim is made.
