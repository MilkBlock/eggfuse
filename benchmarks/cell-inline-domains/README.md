# Carry single witnesses directly into Cell queries

Control: `3c4dc524`. Scope: **standalone Cell CPU**, not native egglog. This is
a representation takeover with short work/semantic checks. It is not a 2x or
throughput result; the historical fastest control remains `8fffff65`.

## Opportunity and removed handoff

The last full [normal-profile diagnostic](../cell-absorption-guard/profile.json)
records 5,191,492 one-column Entry projection reads and 3,118,476 materialized
projection rows. Those totals include larger domains and repeated reads, so
neither is a singleton count or a count of allocations that can be removed.
The current implementation nevertheless exposes a concrete redundant handoff:
the index already distinguishes one witness from many, but returns even a sole
witness through a separately allocated `Rc<Vec<Dependency>>`.

The existing typed Cell query determines the projected column and receiving
atom. The current, version-checked index supplies the actual domain. A sole
witness now travels inline through Free Join admission, `Subtrie`, the residual
Cell kernel and the ordinary query enumerator. It never converts back to a
vector at those handoffs. Larger domains retain their existing shared view,
deterministic order, refinement and neighborhood-cache identity. No persistent
candidate index, binding copy, result cache or subscriber list is added.

This uses existing Cell dataflow to delete a temporary container; it does not
admit another Ripsat state or establish a cross-Run completion. A scheduled
block switch can still borrow the candidate only within its sealed matching
phase. Exact fields, constructor predicates, visibility, semi-naive ownership,
late membership, union and retirement remain the original executor's work.
A single fingerprint candidate is not evidence that a query matched. Research
projection/frontier observers retain their original shared-domain path.

## Costs and validation contract

Candidate and Subtrie headers become wider in the sparse build. The report's
`query_domain_transport` exposes their actual `size_of` values. Every present
one-column bucket adds a shape check, including buckets that remain shared;
the consumers also dispatch on the candidate representation. The existing
`shared_column_reads` continues to count one-column index accesses regardless
of their return representation.

Bake Work charges `projection_shape_checks`, rejects missing/unknown versioned
accounting, and awards no separate credit for `inline_domain_deliveries`.
Remaining materialized rows retain their existing work charge. These are coarse
operations, not CPU-cycle estimates. Repeated inline reads do not imply repeated
avoided allocations: the former implementation could reuse a cached singleton
view. Header payload and row materialization are not allocator totals or RSS.

The index test uses both ordinary and forced-zero fingerprints. It verifies
single-to-many-to-single-to-empty membership, retained old domain snapshots,
shared-view identity for multiple witnesses and absence of singleton views.
The native-checked fixture exercises source Runs with scalar changes, new
members, union, deletion, hiding and recreation, and compares serial/worker
executions at every Run. Existing query, publication and completion regressions
retain their checks.

## Short measured work

Both lanes use the same frozen programs, four query workers, grain 64, canonical
storage, repair ports, Entry publication and Cell absorption. Binary/program
hashes and full retained counters are in [results.json](results.json).

| Observation | sum-bits before / after | Raytrace 1,280 Runs before / after |
|---|---:|---:|
| Entry materialized references | 4,093 / 2,422 | 278,826 / 224,008 |
| General-probe materialized references | 110 / 236 | 8,309 / 9,472 |
| Both materialization counters combined | 4,203 / 2,658 | 287,135 / 233,480 |
| New shape checks | 0 / 6,899 | 0 / 331,535 |
| Inline projection returns | 0 / 5,468 | 0 / 243,359 |
| Inline domains delivered after ownership checks | 0 / 4,493 | 0 / 230,428 |
| Entry probes, unchanged | 17,430 | 1,218,004 |

An independent later general probe can still require a shared view that Entry
admission no longer built. This moves 126 / 1,163 references between the two
materialization counters. The net reductions are **1,545 / 53,655**, not the
Entry-only differences. The collector allows only these two Free Join counters
to differ and requires their total to fall. This is not an allocation count.

On this target, the candidate is 16 bytes and its Subtrie is 32 bytes; the old
Rc-only field and Subtrie were 8 and 24 bytes. That widening also affects inline
domain-list storage. Capacity growth, actual allocator traffic and peak memory
are not isolated by this diagnostic. More than six new shape checks occur per
net removed materialized reference on this Raytrace prefix; their cost differs
from constructing a heap owner. No net work-credit or time win is inferred.

All exact states, ordered logical/executed Run records, graph-operation counters,
query counts and unaffected Free Join counters match. The sum-bits native
choice validator returns `pass` / exit 0. There are 103 passing runtime tests
and 52 compiler/unit/integration tests. All-feature and minimal compilation pass,
as do README compile/run/bench commands; bench repeat 1 is a command smoke check.
This is the fourth implementation since the maintenance throughput checkpoint;
full speed comparisons remain on the agreed five-implementation cadence.

## Reproduction

Freeze the control before building and use fresh output directories:

```sh
cargo build --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports --example emit_cell_source
target/release/examples/emit_cell_source tools/cell-compiler/tests/fixtures/inline-domains.egg ROOT/fixture
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports --example query_prefix
python3 benchmarks/cell-inline-domains/check.py BEFORE_QUERY_PREFIX AFTER_QUERY_PREFIX ROOT/fixture/program.json SUM_PROGRAM RAY_PROGRAM SAVED_SEMANTIC ROOT/checks
```

The short collector compares the fixture, complete sum-bits and the first 1,280
Raytrace Runs. It requires exact state, ordered logical/executed Run signatures,
all graph-operation counters, query counts and unaffected Free Join work.
It invokes the unchanged sum-bits native choice validator using its saved
contract inputs. Raytrace evidence is relative and prefix-limited. Binaries,
programs, states and logs stay under ignored `out/cell-inline-domains`.
