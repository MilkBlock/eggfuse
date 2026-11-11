# Project complete-key Cell reads at their source

Control: `c073c460`. Scope: **standalone Cell CPU**, not native egglog.
This is the fifth implementation after the maintenance checkpoint. Short work
checks below do not establish throughput or the requested 2x improvement.

## Opportunity and removed representation

The saved full [Raytrace diagnostic](../cell-absorption-guard/profile.json)
contains 1,118,287 neighbor point-cache hits and 11,004 probes, plus 84,121
PointPorts requests and 21,650 hits. Hits include negative reads, so these are
not counts of removable positive row allocations. The typed Cell query already
provides a complete key and consumes only its returned value, witness, epoch
and visibility. Nevertheless, the residual kernel and both existing caches
used a full `Row`, retaining its complete field array with an atomic shared
owner in sparse builds.

These queries now carry `Point` directly. Ordinary function reads use the same
index or unit-storage lookup and project the authoritative result without
building a row, retaining its field array or decoding unused keys. A decoded
result remains authoritative when present; otherwise the result is canonicalized
exactly as `function()` would do. Constructors keep their existing candidate,
hash-collision and hidden-row selection and project at that boundary. Research
lookup observers retain their existing instrumented source lookup.

PointPorts and neighbor caches replace their row payload, including neighbor
publication refreshes. The kernel consumes the owned result directly. Existing
keys, capacities, epoch/version checks, negative results, retirement handling
and publication order remain. No second index, fact graph, binding array,
per-producer consumer list or new cache is introduced. A scheduled block can
use this representation within its existing read boundary; this does not add a
new cross-Run proof or broaden LazyUnion normalization.

The logical lookup count, exact conditions, delta ownership, residual coverage,
source Runs and graph effects must remain unchanged. The cost of the actual
result's ownership remains: text, set and structural-key values may still share
their own allocations. Header sizes are reported, not assumed smaller. Cold
constructor reads still build the original Row. These changes do not eliminate
all graph field arrays or their storage maintenance.

## Evidence and accounting

The [short result](results.json) uses four query workers, grain 64, canonical
storage, repair ports, Entry publication and absorption on both sides:

| Work | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Graph key lookups, unchanged | 12,061 | 577,506 |
| Positive function reads projected directly | 184 | 8,238 |
| Neighbor cache hits, unchanged | 39 | 4,015 |
| Neighbor cache probes, unchanged | 65 | 4,442 |

The current Point header is 48 bytes; the previous Row header is 56 bytes.
This excludes allocator overhead, cache capacity and separately owned result
values. Exact state, every source Run and all other checked work agree.
The unchanged sum-bits choice validator returns `pass` / exit 0.

`stats.function_point_reads` counts positive direct function reads, not avoided
queries, allocations, committed mutations or total cache transfers. Existing
lookup and cache-work accounting remains authoritative; Bake Work does not
award this coverage a second credit. `query_point_transport` reports actual
Point/Row header sizes; neither measures allocator traffic or peak RSS.

The short comparison retains exact states, all ordered logical/executed Run
records, graph statistics except the new coverage counter, lookup counts, Free
Join work and neighbor cache work. It invokes the unchanged sum-bits native
choice validator. Raytrace uses the first 1,280 Runs and is relative evidence,
not independent native acceptance or a full throughput comparison.

The unit test compares projected reads with ordinary rows before and after
union/repair, decoded-field invalidation, deletion and recreation, for nullary,
unary and multi-key functions with scalar and equality results. It verifies one
lookup per attempt and no retained ownership of the full field array. Existing
publication tests retain replacement/retirement ordering and deferred-table
visibility checks; query-worker integrations compare every source Run and
ordered bindings, including forced constructor hash collisions.

104 runtime unit tests and 52 compiler/integration tests pass. All-feature and
no-default-feature compilation pass, as do the README compile/run/bench commands.
The README bench uses repeat 1 only as a command smoke test, not speed evidence.

## Reproduction

Freeze the control before building and use fresh output directories. The existing
native-checked `inline-domains` fixture supplies mixed constructor/function
reads, union and deletion. Build products and raw state exports stay under
ignored `out/`.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports --example query_prefix
python3 benchmarks/cell-point-results/check.py BEFORE AFTER FIXTURE_PROGRAM SUM_PROGRAM RAY_PROGRAM SAVED_SEMANTIC NEW_OUTPUT
```

The fifth-implementation timing comparison is a separate campaign with frozen
normal executables and complete source workloads. See the
[query transport checkpoint](../cell-query-transport-checkpoint/README.md): the
five changes together improve Raytrace inference by about 2.8% against the
previous checkpoint in that campaign. It does not isolate this projection's
contribution or establish 2x.
