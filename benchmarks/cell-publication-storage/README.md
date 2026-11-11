# Transfer fingerprint storage and reuse the publication buffer

Control: `5197c099`. This is the fifth implementation since the previous normal
checkpoint, on the **standalone Cell CPU**, not native egglog.

The latest grouped publication still copied each new fingerprint array into
its index owner before updating reverse buckets. `Columns::put` now borrows the
old fields while updating buckets, then moves the new array into the existing
map entry. Exact-value read-lease invalidation, collision handling, removals,
field masks and ordinary index membership retain their previous semantics.

Sieve also discarded the original change vector after every publication. It
now clears that vector and returns its allocation to `QueryIndexes`, including
the disabled path. No events remain live across Runs; no new buffer or fact
representation is introduced. The vector can retain its largest prior capacity,
which trades higher live memory for fewer allocations. This is storage reuse;
it discharges no further rule applications, query checks or cross-Run effects.

Separate allocator-instrumented executions, with four workers and grain 64:

| Observation | sum-bits before → after | Raytrace first 1,280 Runs before → after |
|---|---:|---:|
| Allocation calls | 80,289 → 79,389 | 2,322,042 → 2,319,370 |
| Reallocation calls | 13,469 → 13,067 | 343,439 → 341,837 |
| Cumulative requested bytes | 19,604,491 → 19,248,523 | 961,909,636 → 947,155,076 |
| Live requested bytes after execution | 135,493,823 → 135,497,918 | 701,517,059 → 702,041,346 |
| Peak live requested bytes | 135,914,890 → 135,918,985 | 701,526,265 → 702,049,200 |

These include worker scratch variation and are allocator requests, not RSS or
memory traffic. They do not establish a speedup. Graph states, all ordered Run
fields, actual effects, Sieve, Free Join and Entry/index work agree. No saved
query or Bake credit is claimed. The explicit live-memory increase is retained.

101 runtime unit tests and 31 related compiler integration tests pass, covering
collisions, read leases, union, late input, deletion/recreation and workers.
The unchanged native sum-bits validator returns `pass` / exit 0. Minimal compile
and README compile/run/bench (repeat 1) pass; these are smoke checks only.

Freeze a control at `5197c099`, then build the candidate with:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,cell-entry-reverse,view-ports,allocation-metrics --example query_prefix
```

Use the frozen `cell-fixed-reads` sum/Raytrace programs with the query-prefix
arguments documented in the column-influence experiment, 2,000/1,280 requested
Runs, repair ports, Entry publication and absorption; reverse selection stays
off. Save binaries as `control`/`runtime` and exports as `sum-before`, `sum-after`,
`ray1280-before`, `ray1280-after`. Prepare the original sum semantic inputs with
the candidate as `run-values/state.json`, then:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-publication-storage/collect.py ROOT RESULTS.json
```

Raw artifacts remain ignored in `out/cell-publication-storage`. The normal
five-implementation timing checkpoint uses a separately built executable with
no allocator instrumentation.
