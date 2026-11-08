# Shared symbolic repair slices

This changes the opt-in standalone Cell CPU backend from `ee259fd2`.
The previous ownership experiment established persistent subscription removal,
but an equality traversed its entire lifetime owner's body. On the frozen
208-unit sum-bits catalog that meant 113,962 body visits, 306,860 equality-port
checks, and 20,339 more body reads to rebuild owner boundaries. These existing
operation counts identify the opportunity; no new Raytrace run or union-frequency
survey is used in this iteration.

## Representation and execution

`bake-cell-ownership` now emits `eggfuse-ownership-markers/v2`. Each marker contains
a symbolic port program: a mapping from body columns to symbols, immutable
symbol-to-local-instruction slices, native result locations, and source-ordered
union instructions. Equal programs share one allocation across templates, and
all instances of a template use that allocation. The artifact loader independently
rederives the complete program. Old v1 descriptors must be rebaked from the source
catalog; changing an artifact checksum cannot authorize different instructions.

The compiler reuses the existing local-union symbolic analysis. Copies and
unconditional constructor congruence combine symbols. It does **not** assume an
explicit union has executed. Constructor closure is disabled across templates
containing visibility mutations, so deleting and recreating the same constructor
can produce distinct result identities. The ordinary RHS union path evaluates
the marker instruction at its original source position. Other union producers,
including congruence collisions and existing optimized RHS paths, enter the same
committed-equality dispatcher.

A native equality result addresses its source template signal directly. External
inputs, cross-frame inputs and escaped aliases bind template signals at component
boundaries. One binding serves all uses of that symbol in the template. Native
internal signals have a root and live-use count but no entry in the canonical-root
boundary directory. The directory contains template signal handles, not per-row
destination lists. Runtime equality remains authoritative; addresses and program
sharing do not prove equality.

On a committed union, the dispatcher activates these shared slices. Several
signals can already alias dynamically: their instructions are combined per fact
before deciding whether the change is result-only or requires key completion.
This combines work within one committed equality, preserving original witness
ordering, collision probes and publication barriers. Future unions are not
batched across visibility boundaries. The same slices supply equality-bound
candidate domains, with the residual legacy index for unsupported rows.

Boundary bindings are incrementally created, redirected and retired. Deleting a
signal's defining constructor does not discard its still-live local users. No
survivor resubscribes, and neither union propagation nor boundary maintenance
enumerates the lifetime owner's body. Empty lifetime owners can still be released
without visiting their members. Full inventory assertions are performed during
reporting, outside inference.

## Structural gates and limits

The cross-stage regression fixture adds 0, 32 and 300 independent constructors
to an otherwise identical producer template. All three executions perform exactly
four field checks, four changed fields, four body visits, five slice instructions
(one belongs to a retired body), and zero boundary refresh reads. The larger case
also crosses the lifetime-owner capacity limit. Added live state is counted;
constant repair work is not a claim of constant allocation or memory usage.

Focused checks additionally cover late congruence chains, candidate completeness,
aliases across repeated union waves, origin deletion, delete/recreate lifetimes,
a union after a terminated RHS prefix, corrupted descriptors, and physical sharing
of immutable programs. Semantic fixtures compare every Run's state, bindings and
schedule with the original backend and also execute their source in native egglog.

The final workspace run passes 204 tests, with four preexisting ignored. All
12 focused tests pass in both sparse and non-sparse configurations. A runtime
build with no default features also passes its compile check.

The remaining boundary state is significant. Cross-stage matching currently
connects template instances through named signal bindings, including between
frames in the same lifetime owner. It does not yet fuse those component interfaces
into one shared cross-stage expression. Those bindings are explicitly reported,
not counted as eliminated owner-internal relationships. The new inventory's
`internal_eq_ports` means native **within-template** ports; the predecessor used
lifetime-owner containment, so those two inventory fields must not be subtracted.

Likewise, `boundary_live` changes unit from root-to-owner memberships to
root-to-template-symbol memberships. `native_signal_routes` and
`boundary_signal_routes` replace the old owner-route counters; the latter remain
zero. `slice_steps` includes skipped inactive instructions, `coalesced_slice_steps`
counts additional instructions for an already selected fact, and `port_checks`
counts the fields actually inspected. The work-credit ledger charges signal
binding operations, record creations/retirements, activations, slice execution and
candidate planning. Occupancy gauges and shared-program counts earn no credit.
Binding-record creations are not measurements of heap allocation calls or bytes.

## Small application audit

Only sum-bits is executed in this iteration. It passes the full graph, schedule,
ordered RHS, effective-write, resume and normalized Spine comparison, both against
the same binary with ownership disabled and the retained `ee259fd2` audit.
These are structural operations in the standalone runtime, not native egglog
measurements; logical matches are not described as committed mutations.

The primary comparison is against the ordinary backend, with result-port repair
and shared Entry publication enabled. The owner-scan predecessor was already a
performance regression; improvements against it do not establish baseline savings.

| Baseline comparison | Ownership disabled | Shared slices |
|---|---:|---:|
| Fields checked by typed constructor propagation | 3,773 | 2,098 |
| Exact key probes | 1,046 | 1,046 |
| Legacy subscription calls | 6,716 | 2,187 |
| Legacy subscription value visits | 19,944 | 7,709 |

The candidate also creates 8,909 symbol-binding records and performs 12,430
attachment/retirement binding reads, plus 7,570 boundary insertion attempts.
These costs must accompany the legacy maintenance savings. Each equality currently
builds temporary ordered maps/sets and column vectors, then sorts/deduplicates them.
Their allocations, allocated bytes, tree comparisons and actual hash-table probes
are not fully measured. An equally weighted sum of the existing counters is not
a validated execution-time model and cannot establish an acceleration result.

`baseline-comparison.json` retains this comparison and its explicit omissions.
The table below is a secondary diagnosis of the removed owner-scan regression:

| Metric | Previous owner scan | Shared slices |
|---|---:|---:|
| Owned live constructor bodies | 2,895 | 2,895 |
| Body visits during propagation | 113,962 | 1,988 |
| Equality-port checks | 306,860 | 2,098 |
| Body reads during boundary refresh | 20,339 | 0 |
| Boundary insertion attempts | 28,020 | 7,570 |
| Ordered key completions | 1,046 | 1,046 |
| Result-only publications | 878 | 878 |

All 2,098 checked fields change. The slice interpreter executes 2,628 instructions,
including 558 inactive instructions and 82 instructions combined with another
instruction for the same fact. New state includes 6,976 live symbol bindings,
of which 4,922 have boundary-directory entries, versus 1,500 coarse owner boundaries
previously. There are 12,430 binding reads during attachment/retirement. The
remaining legacy reverse edges stay at 2,885. The 983 template descriptors share
306 distinct in-memory port programs.

This establishes selective propagation and removes the two full-body maintenance
loops. It does not establish an application speedup or complete cross-stage
interface compression. No timing campaign or Raytrace evaluation is included.
The next structural target is sharing/composing the cross-frame bindings without
losing late external alias notifications or changing ordered publication.

`fixtures.json` contains the size-independence evidence. `monitor.json` retains
every sum-bits publication barrier and the predecessor comparison. `audit.json`
contains trace digests and operation reports; `bake.json` records compiler coverage.

## Reproduction

The frozen source catalog is produced by the producer-receipts experiment.
Output directories must be new. Retain the previous committed audit for comparison.
Build the compiler and runtime separately: Cargo feature unification from the
compiler enables JSON insertion order, changing raw exported object bytes. The
standalone runtime build matches the predecessor and retains exact file-hash checks.

```sh
mkdir -p out/ownership-slices
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test cell_ownership -j 2 -- --nocapture > out/ownership-slices/focused.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test cell_ownership -j 2
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake -j 2
cp target/release/eggfuse-cell-compiler out/ownership-slices/compiler-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/ownership-slices/audit-runtime-standalone
out/ownership-slices/compiler-final bake-cell-ownership --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-slices/baked-sum-final
python3 benchmarks/result-port-repair/audit.py out/ownership-slices/audit-runtime-standalone benchmarks/ownership-slices/audit-manifest.json out/ownership-slices/audit-standalone
python3 benchmarks/ownership-slices/collect.py out/ownership-slices benchmarks/ownership-slices
```
