# Stable ports, local congruence, and dependency-scoped completion

Objective: remove rebuild stalls introduced by incidental representation work,
then remove other obstacles to multithreading, implement parallel execution,
and improve inference using stronger Bake and compiler information. In
particular, a region must continue while unrelated equality propagation is
pending. This work targets the actual **standalone Cell CPU executor**, not
native egglog.

Structural starting revision: `5ffdec1d`; the independently verified signal-slot
improvement `7c7ab5d3` is integrated before validating these field changes. The
previous frozen sum-bits execution still needed
1,046 constructor key completions and 2,098 typed field checks despite precompiled
local repair slices. Runtime `Executor::run` calls global `Graph::repair()` before
publishing any table. Changing storage alone does not remove this barrier.

## Requirements and completion evidence

The following requirements retain the complete structural objective. Passing one
phase does not establish completion of the objective.

| Requirement | Evidence required | Current status |
| --- | --- | --- |
| Covered node fields use stable symbolic ports as authoritative storage | Addresses unchanged across union; read views match reference; no canonical Eq values stored in covered nodes | Verified by field fixtures and frozen sum-bits audit |
| Covered constructor lookup uses operator/scalar discrimination plus exact port equality | Same lookup answers before/after aliasing; bounded candidate sources; no operator-bucket scan disguised as indexing | Not implemented |
| Local congruence uses shared template conditions and static wiring | Multi-input conjunction, shared cross-stage chains, unrelated-noise invariance; no per-instance producer-to-consumer index | Not implemented |
| Canonical key maintenance is removed where coverage is complete | Checked coverage certificate; zero rehash/index relocation for the admitted region; incomplete cases remain explicit boundaries | Not implemented |
| Completion waits follow actual dependencies | One region advances and publishes while another has pending congruence; dependent and negative observations wait correctly; queued work eventually reaches the same fixed point | Not implemented |
| Lifetime and generation are safe | Partial births, deletion, retained consumers, rebirth, stale queued events, late unions and boundary aliases | Field deletion/rebirth and retained-consumer tests pass; queued-condition tests pending |
| Costs remain accountable | Read resolution, temporary views, exact Eq tests, condition visits, boundary notifications, queue operations and allocations all reported; semantics and whole-process baselines retained | Initial field counters only |
| Other parallelism obstacles are removed | Audit and resolution of shared mutable state, equality-directory contention, publication ownership, effect order, allocator pressure, and global work queues | Not implemented |
| Parallel inference is implemented and validated | Real concurrent workers; race/lifetime stress; correct boundary effects; scaling and full-cost baseline comparisons | Not implemented |
| Bake exploits compiler information | Checked candidate coverage, typed read/write footprints, static alias/lifetime facts and local wiring; selection charged against observed total runtime work | Existing fragments only; new structural metadata pending |

For parallel claims, exercise the protocol with concurrent workers and contested
boundary aliases, not merely a single-threaded queue. A single global union-find
lock or a mandatory global queue drain would leave the objective incomplete.

## First implementation step

`--stable-ports` enables Cell ownership and changes covered fact storage to typed
scalar values or `PortRef { component, symbol }`. The composition's immutable
symbol numbering supplies the address. Component IDs are monotonically allocated
and never recycled; retired addresses must not resolve a later instance.

`Graph::fact` and live `fact_column` reads resolve the ports through the equality
relation. Returned rows remain immutable snapshots for the existing matcher and
publication APIs. Stored nodes do not retain these canonical snapshots. Existing
shared slices issue change notifications; `project_owned_ports` no longer writes
Eq values into these nodes. Canonical key completion and the global Run barrier
remain in this first step and are separately reported, not credited as removed.

This compatibility interface can increase read-time allocation and equality
resolution. Counters report row views, port reads, root resolutions, notifications
and remaining key enqueues. A later direct field-reader interface may avoid view
materialization; it is not assumed free in the current implementation.

## Field-step verification

The workspace passes 226 tests (four preexisting ignored). Ownership and stable
field fixtures pass 30 tests in each of sparse and non-sparse configurations; the
runtime without default features also passes its compile check. The tests cover
cross-stage chains, partial multi-input equality, late union after deleting the
producer, immutable returned snapshots, and stale port rejection after component
retirement/recreation.

The frozen sum-bits audit compares `--cell-ownership` with `--stable-ports` using
the same baked artifact. All 1,428 Run observations, final state, ordered RHS,
effective writes, resumes and normalized Spine traces match exactly. There are
2,895 live stable nodes containing 7,814 port fields. The old field projection
path performs zero checks/copies (previously 2,098 checks). The same 1,046 key
completions and 878 result publications remain: key maintenance and the global
barrier are explicitly **not removed yet**.

The audit records 35,602 temporary row views and 91,647 port/root reads. These
counters cover all accesses since enabling the mode, including setup and ordered
audit reads; they are not execution-only allocation counts or a latency claim.
No performance campaign is attributed to this partial structural step. The
independent signal-slot improvement has its own two-workload results in
[signal-lifetime](../signal-lifetime/README.md).

Reproduce with a fresh `out/stable-port-congruence` directory. Copy the unchanged
sum-bits artifact from `out/ownership-fragments/baked-sum-final/program.json` into
`out/stable-port-congruence/sum-program.json`; its file hash is retained in
`fields-audit.json`. Build compiler tests and the audit runtime separately so
feature unification does not change exported JSON ordering.

```sh
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2 > out/stable-port-congruence/workspace-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test stable_ports --test cell_ownership -j 2 > out/stable-port-congruence/fields-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test stable_ports --test cell_ownership -j 2 > out/stable-port-congruence/fields-non-sparse-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2 > out/stable-port-congruence/minimal-check.log 2>&1
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/fields-audit-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/fields-audit-runtime benchmarks/stable-port-congruence/fields-audit-manifest.json out/stable-port-congruence/fields-audit
python3 benchmarks/stable-port-congruence/collect-fields.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Next structural steps

Constructor candidates must come from static marker positions or explicit boundary
port domains. Exact corresponding input equality proves congruence; a fingerprint
only narrows candidates. Scalar-only keys can retain an immutable index. A dynamic
class-wide scan or a new per-instance consumer subscription list is not an
acceptable replacement for key repair.

Compile local conditions from operator-compatible positions in the shared shape.
A condition publishes result equality only when all input guards are proved and
both facts refer to live incarnations. Static port-to-condition routes are shared
code. Birth/retirement and cross-region aliases must preserve completeness. Only
regions whose local and boundary candidate coverage is proved can leave the old
canonical-key path.

Finally separate propagation progress, publication, and completion requirements.
Unrelated positive work can advance while a region is pending; absence tests,
source-ordered nonmonotone effects, and final observations require explicit
completion of their dependency region. Unknown equality is not false equality.
Tests must exercise this behavior through the executor, not just private queues.

After regional completion works, audit `Rc`-owned plans versus instance state,
the shared equality directory, mutable function merges, publication ownership,
and allocation on the dispatch path. Do not hide a global lock behind a regional
API. Parallel workers need immutable shared code and explicit ownership of
mutable regions, with ordered boundary effects where program semantics require
them. Compiler-derived effect footprints and checked local coverage should drive
these decisions. Thread safety alone is not performance evidence; retain serial
controls, worker-count comparisons, and sum-bits/Raytrace end-to-end results.
