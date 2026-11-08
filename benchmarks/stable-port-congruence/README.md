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
| Covered constructor lookup uses operator/scalar discrimination plus exact port equality | Same lookup answers before/after aliasing; static positions or explicit boundary port domains; no operator-bucket scan disguised as indexing | Verified for scalar constructors with an equality input; immutable birth hints plus complete port domains |
| Local congruence uses shared template conditions and static wiring | Multi-input conjunction, shared cross-stage chains, unrelated-noise invariance; no per-instance producer-to-consumer index | Bounded shared conditions and foreign candidates execute in one ordered pass; all-input, cross-stage, noise and mixed-boundary tests pass |
| Canonical key maintenance is removed where coverage is complete | Checked coverage certificate; zero rehash/index relocation for the admitted region; incomplete cases remain explicit boundaries | Removed for completely owned scalar constructors with equality inputs; logical congruence checks remain |
| Completion waits follow actual dependencies | One region advances and publishes while another has pending congruence; dependent and negative observations wait correctly; queued work eventually reaches the same fixed point | Actual Executor fixtures advance, publish and consume independent regions of the same Eq sort; no useful main-workload bypass, same-table independence still open |
| Lifetime and generation are safe | Partial births, deletion, retained consumers, rebirth, stale queued events, late unions and boundary aliases | Existing lifetime fixtures pass through local conditions; conditions retain no instance state and inspect live facts; future asynchronous queues need separate generation tests |
| Costs remain accountable | Read resolution, temporary views, exact Eq tests, condition visits, boundary notifications, queue operations and allocations all reported; semantics and whole-process baselines retained | Field, key, condition, scope and publication-selection operations included in Bake's ledger; retention peaks reported; parallel and full-cost admission pending |
| Other parallelism obstacles are removed | Audit and resolution of shared mutable state, equality-directory contention, publication ownership, effect order, allocator pressure, and global work queues | Not implemented |
| Parallel inference is implemented and validated | Real concurrent workers; race/lifetime stress; correct boundary effects; scaling and full-cost baseline comparisons | Not implemented |
| Bake exploits compiler information | Checked candidate coverage, typed read/write footprints, static alias/lifetime facts and local wiring; selection charged against observed total runtime work | Shared conditions and influence wiring plus conservative source-union write footprints; precise merge/container effects and bound write scopes pending |

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

## Port-equality constructor step

`--port-keys` implies stable fields. The compiler's typed coverage admits scalar
constructors with at least one equality input. Enabling verifies every existing
fact in an admitted table has symbolic-port ownership; births assert the same
invariant. A bound equality input reaches every possible matching constructor
through the root's boundary signals or native signal and shared template slices.
Exact table, scalar and corresponding port values establish the match. This
does not scan the operator bucket and does not add a per-producer consumer list.
Boundary domains may still be large; this step does not claim constant work.

Existing index entries become immutable birth hints: they are inserted at birth,
never relocated by union, and removed at fact retirement. A hint hit requires
the same exact guards. A miss falls back to the complete port domain, so aliases
cannot hide an existing constructor. During collision completion, pending facts
are excluded until their source-ordered turn, preserving the legacy survivor and
receipt order. Output equality, visibility merging and retirement remain real
logical work. Uncovered tables retain their existing path.

All 228 workspace tests pass (four preexisting ignored); 32 ownership/port
fixtures pass in sparse and non-sparse configurations. The direct alias test
requires a birth-hint miss to find the old constructor through its new equality
domain, and deletion/rebirth rejects the old stable address. Further fixtures
cover simultaneous key changes and scalar discrimination after equality merges.
The minimal runtime without default features compiles.

The final sum-bits audit again matches all 1,428 ordered Run observations and
all state/RHS/write/resume/Spine digests. Canonical key completions, hash changes
and repair index probes drop from 1,046 each to zero. The replacement still
performs 1,046 equality completions and 878 result publications. It performs
18,476 constructor probes, 11,171 successful birth hints, 7,305 port-domain
probes, 18,080 candidate visits and 35,186 field comparisons. Port/root reads
increase from 91,647 to 119,758. These include setup and audit accesses and are
not timing or allocation results. An exploratory version without birth-hint
probes needed 18,476 domain probes, 27,299 candidates and 51,478 comparisons;
its intermediate counters are explicitly separated in the evidence.

The new work is charged in `work_credit.rs`; counting only old repair probes
would give false credit. We have not run a latency campaign for this structural
step. Local compiled pair conditions and the global publication barrier are
still outstanding. This is an implementation in the standalone Cell CPU, not
a change to native egglog.

Reproduce using the same artifact and build commands above, then:

```sh
# Save the workspace/focused/minimal logs under port-key-*.log, as consumed below.
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/port-key-runtime-final
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/port-key-runtime-final benchmarks/stable-port-congruence/port-key-audit-manifest.json out/stable-port-congruence/port-key-audit-final
python3 benchmarks/stable-port-congruence/collect-port-keys.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Initial shared local conditions

`--local-congruence` additionally compiles guarded constructor-pair conditions
from each shared composition shape. Compilation happens once at mode setup,
not at instance birth or union. Plans contain static site routes, corresponding
input-port equalities, scalar columns and result ports. Operator tags remain
runtime guards because a port program can serve multiple operators. Plans with
more than 16 equality-key sites are explicitly uncovered, never truncated into
an incomplete proof. Ordinary ownership/port-key mode does not build these plans.

Input-change notifications follow the existing shared signal slices to these
conditions. A visit checks both live facts, source-ordered pending status, the
operator, scalar guards and **every** input equality before the existing logical
commit publishes output equality and retires the duplicate. Identical shared
symbols prove their own equality without a root lookup. No per-instance
condition state, waiter list or cached satisfied bit is retained; deletion and
rebirth cannot inherit a prior condition result. Birth lookup remains the exact
port-key path, so a new constructor cannot miss an already-congruent live fact.

The first implementation (`3c8c51e0`) checks whether the chosen input domain has any foreign
constructor before using the complete local pair set. `closed_regions` counts
successful **probes**, not distinct regions or a permanent closure certificate.
A later alias or birth rechecks the boundary. If foreign consumers exist, the
complete generic port domain still runs. This conservative gate is correct but
duplicates discovery work; it is not admitted as a performance improvement.

All 232 workspace tests pass (four preexisting ignored), with 36 focused tests
in sparse and non-sparse configurations and a minimal compile check. Fixtures
show that partial two-input equality does not merge outputs, the second input
activates the next constructor layer, shared conditions fire across source Runs,
100 unrelated nodes leave local work unchanged, and foreign/oversized regions
retain exact fallback behavior. Existing lifetime/visibility fixtures also run
through the new path.

The sum-bits audit preserves all 1,428 ordered Run observations and all digests.
There are 2,176 shared conditions across 606 covered shapes (24 uncovered).
Of 1,046 logical completions, 54 pass the local-only gate, 982 retain a foreign
candidate and 10 have an uncovered source shape. The local path visits 125
conditions and fires eight, all across stages. It avoids only 54 generic probes
while adding 10,598 boundary-signal visits and 5,330 boundary-site checks. Port
reads increase slightly from 119,758 to 119,793. These counters expose the bad
gate rather than establish a speedup. No timing campaign was run for it.

Evidence is in `local-condition-audit.json` and `local-condition-validation.json`.
Reproduce with the same separate builds, save validation logs under
`local-condition-*.log`, then:

```sh
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/local-condition-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/local-condition-runtime benchmarks/stable-port-congruence/local-condition-audit-manifest.json out/stable-port-congruence/local-condition-audit
python3 benchmarks/stable-port-congruence/collect-conditions.py out/stable-port-congruence benchmarks/stable-port-congruence
```

This experiment motivated integrating internal conditions and foreign candidates
in one exact ordered pass, described next. The initial negative result is kept
separately, not overwritten by the subsequent improvement.

## Shared conditions with one boundary pass

The current `--local-congruence` path obtains internal candidates directly from
the shared condition routes. It chooses one equality input using root signal
cardinality, without visiting every possible anchor's consumers just to plan.
The chosen root's foreign signals supply the remaining candidates through shared
input routes. An oversized foreign template uses its existing complete signal
slice filtered to the corresponding input column. No runtime consumer list is
created. All candidates are ordered by fact identity before exact guards run,
preserving survivor, visibility and receipt order across local/foreign mixtures.

An open boundary no longer repeats the generic lookup. Only an uncovered source
shape takes the old complete path. Coverage holds because every congruent foreign
constructor must have an equal value in the chosen input column; every internal
pair with a compatible layout appears in the compiled conditions. Operator and
all remaining inputs still require exact guards. The lookup proves the answer
for the current equality relation; it is not a declaration that no future union
can affect the region.

The scratch candidate list has 16 inline entries; larger lists allocate and sort
with explicit growth/comparison counters. On sum-bits it grows 43 times in 26
spilled probes, with 8,895 sorting comparisons. These are not whole-process
allocation counts. The Bake work ledger charges collection, sorting, boundary
visits and exact guards as well as the old work that remains.

All 233 workspace tests pass (four preexisting ignored), 37 focused fixtures pass
in both configurations, and the minimal runtime compiles. New mixed-candidate
fixtures preserve the oldest eligible survivor when both a local peer and a
foreign candidate exist. Oversized source and foreign templates are both
exercised. The same frozen sum-bits audit preserves all 1,428 Runs and all hashes.

Of 1,046 logical completions, 1,036 use the combined route and 10 retain the
generic source fallback. There are 189 probes with no foreign candidates and
847 with foreign candidates. Local conditions fire 108 times, 96 across stages;
foreign candidates account for another 733 collisions. Successful decisions
proceed through the existing visibility/receipt/retirement commit path; these
are not counts of effective union operations. Output propagation and the global
Run barrier still remain.

| Work counter | Port-key baseline | Combined route |
| --- | ---: | ---: |
| Generic port-domain probes | 7,305 | 6,269 |
| Generic planning signal visits | 260,196 | 200,707 |
| Generic planning slice visits | 555,540 | 428,687 |
| Generic execution slice visits | 156,401 | 116,376 |
| New boundary signal visits | 0 | 20,710 |
| New boundary site checks | 0 | 17,234 |
| New uncompiled foreign slice steps | 0 | 3,218 |
| New local condition visits | 0 | 611 |
| Port/root reads | 119,758 | 120,437 |

This is a structural-work improvement against `f8a3ee35`, not a latency or
multithreading result. No structural timing campaign has been run. The evidence
retains setup and ordered-audit accesses, and reports added work rather than
crediting the generic-probe decrease in isolation.

Save validation logs under `routed-condition-*.log`, build the audit runtime
separately as above, then reproduce:

```sh
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/routed-condition-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/routed-condition-runtime benchmarks/stable-port-congruence/local-condition-audit-manifest.json out/stable-port-congruence/routed-condition-audit
python3 benchmarks/stable-port-congruence/collect-conditions.py out/stable-port-congruence benchmarks/stable-port-congruence --prefix routed-condition
```

## Compiler-scoped completion queues

`--scoped-queues` additionally enables table-owned pending queues and checked
completion scopes. It deliberately retains the source Run publication barrier;
this flag does not claim independent Executor progress. The ordinary path keeps
its original flat set. Scoped queues retain one membership per fact, with only
nonempty table heads in the ordered directory, so choosing a scope does not scan
every unrelated pending fact. Scope, head and fallback work is charged in Bake's
ledger. The originating epoch stays attached to queued work.

The compiler computes transitive effects from constructor result sorts and typed
table fields, plus ruleset read/RHS demands. Unknown containers and pending
opaque merge programs retain conservative boundaries. A readiness answer cannot
be true while source connectivity is still pending. Fixtures prove that B's
Graph closure can finish while A remains pending, delayed facts preserve their
old epoch, multi-sort chains wait correctly, mutable and opaque merge effects
remain exact, and a scope from another program is rejected.

All 237 workspace tests pass (four preexisting ignored), with 41 focused tests in
sparse and non-sparse configurations and a minimal compile check. Ownership
fixtures run the new queues through the ordinary full-completion Executor. The
sum-bits audit preserves all 1,428 Runs, state/effect digests, normal runtime
counters and stable-port counters. It adds 1,046 head probes and 1,599 head
updates. Because the Executor still waits globally, these additions are overhead,
not savings or a timing result.

The same audit exposes an admission failure: 401 tables, 99,201 potential effect
edges, **zero** tables accepted for cross-Run deferral by this coarse proof.
Table/type scopes alone therefore cannot solve the intended workload. Six opaque
tables include a known `set<Expr>` and five known merge programs. Stronger compiler
effects and concrete shared Cell ports must refine the proof. Independent Graph
fixtures are not evidence of independent publication or parallel inference.

The exact lifetime/publication obligations and next integration gates are in
[scoped-executor-contract.md](scoped-executor-contract.md). The core evidence is
retained in `scoped-core-audit.json` and `scoped-core-validation.json`. Save the
usual separate validation logs under `scoped-core-*.log`, then reproduce:

```sh
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/scoped-core-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/scoped-core-runtime benchmarks/stable-port-congruence/scoped-core-audit-manifest.json out/stable-port-congruence/scoped-core-audit
python3 benchmarks/stable-port-congruence/collect-scoped-core.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Remaining completion and concurrency work

The latest catalog demonstrates 1,046 equality completions after removing key
maintenance. Cross-Run fragments can share the local conditions and their
dispatch; the remaining obligations are complete candidate coverage, live fact
checks, all-input conjunction and boundary alias handling. Typed constructor
schemas and checked Entry substitutions can prove local wiring, while operator
tags must remain explicit: port-program identity alone does not imply the same
constructor. The next experiment must report local versus boundary condition
work against this port-key version, without claiming that all congruence work
has disappeared.

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


## Selective Executor publication

The opt-in `--scoped-execution` path now waits for a ruleset's compiler footprint
**before** dirty-reader selection and matching. It commits explicit source unions
at the end of the Run, completes mutable/legacy effects, and may retain pure
constructor obligations while independent source occurrences proceed. Matching
within one source Run still uses its original finite snapshot. Source checks
and equality-sensitive guards request their complete footprint. Final execution
drains outstanding work; an explicit `execute_until` checkpoint may retain it.

`ChangeBatch` moves whole table maps between reusable batches, including exact
coalesced event counts. Only ready tables reach shared Entries, query/range/
neighbor indexes and reader delivery. Deferred anchors retain their source slot
in the shared Spine context arena; new Runs append slots, and the arena clears
when all anchors have published. Receipt forwards survive until deferred anchors
resolve. This deliberately retains already-consumed slots too while any anchor
remains pending; peak contexts/anchors/changes/forwards report that cost. It is a
single-thread publication protocol, not a worker implementation.

`scoped-executor-fixture.json` records actual Executor checkpoints: after the
first source Run A has one pending completion and two pending anchors. B then
executes two Runs, publishes three table batches and creates a `SeenB` fact from
the preceding Run's output while A remains pending. A dependent observation then
completes A; final graph and ordered binding/changed counts equal the global
reference. Additional fixtures cover an inequality guard, a source check that
itself forces completion, deletion/recreation, delayed receipt resolution,
origin epochs and final draining without a dependent source Run. Global snapshot
and incompatible global audit consumers explicitly retain full completion and
are reported; they do not count as evidence of independent progress.

The small fixture pays 24 dependency checks, 12 table-selection checks and 14
direct-publication checks. It retains at most five change records, two anchors
and two context slots. These counters describe replacement work, not a latency
benefit. Already-ready independent reads skip redundant publication passes.

Validation passes 245 workspace tests (four preexisting ignored), 48 focused
fixtures in both sparse and non-sparse modes, and the no-default-features
compile check. The frozen sum-bits audit retains all 1,428 exact ordered
Run/effect observations.
Its proof still admits **zero** deferrable tables. An initial implementation
added 659 scoped completion requests, 638 legacy frontier probes and 38 opaque
fallbacks without bypassing a barrier. The compiler's empty admission result now
specializes these queries and split bookkeeping away. Final queue counts,
ordinary runtime counters, stable-port work and index publication counts equal
`--scoped-queues`; the old binary's semantic hashes match as well. This retains
the full barrier in sum-bits and establishes **no speedup**. The rejected overhead
is retained in `scoped-executor-audit.json` rather than credited as useful work.

The next required refinement remains concrete bound Cell ports, including
same-sort independent regions, plus precise container and merge effects. Table
scopes demonstrate the publication protocol but cannot establish workload
locality. Shared mutable state, real workers and complete-cost performance
admission are still open requirements.

## Concrete port influence experiment

The opt-in `--port-scopes` mode refines the type-only completion proof using
actual equality roots and shared Cell wiring. The previous catalog admitted no
deferred tables: an unrelated mutable function using the same Eq sort blocked
every constructor. A queue now records the roots that actually caused its
pending work. Shared influence code follows changed inputs to possible result
equalities, and follows result-only uses as observations. It does not walk back
through every other input of a constructor. Thus two regions sharing an
unchanged `Context` input need not acquire the same influence footprint.

This is a conservative reachability proof, not speculative congruence: it
performs no simulated union or key comparison. Existing native/boundary symbols
provide cross-component connections; no per-instance consumer index is added.
Legacy or mutable consumers retain their typed boundary effects and ordered
completion. Missing wiring and a 4,096-visit budget fall back to the complete
typed proof. Queue groups and publication remain table-granular; this does not
yet separate disjoint regions using the same constructor table.

Before a source Run, the compiler supplies direct read/RHS demands **and** the
potential effects of its explicit unions and constructor `set` operations.
Read independence alone is insufficient: B's union can enter pending A through
existing constructor result aliases. This version conservatively expands such
writes by Eq sort. Removing that expansion fails the incoming-alias fixture's
no-dependent-bypass assertion, although its final graph alone still matches.
No incorrect final graph or epoch panic was observed in that negative control.
Refining incoming writes requires a bound-write proof or a stronger causal
epoch protocol, not deletion of the safety gate.

The same-sort fixture retains A's one completion and two publication anchors
while B commits two source Runs and a later rule creates `SeenB` from B's output.
An unrelated mutable table and a shared unchanged input remain present. Final
graph and ordered binding/changed observations equal the reference. Other
fixtures cover a real mutable boundary, incoming result aliases, inequality
guards, source checks, deletion/recreation, selective B completion and budget
fallback. Validation passes 253 workspace tests (four preexisting ignored), 56
focused tests in both configurations, and the minimal runtime compile check.

The same frozen sum-bits program preserves all 1,428 ordered Run observations
and state/RHS/write/resume/Spine digests. Ordinary runtime counters, stable-port
work and index publication counts equal `e0c61d3a`'s scoped-executor control.
It still performs 1,046 equality completions. **No source Run or binding advances
while another region is pending.** One partial publication is not useful
cross-Run progress. This mode remains experimental and is not admitted as a
performance improvement.

An initial probe added 747 influence forecasts, 13,748,491 membership checks,
265,859 static steps and 1,981 tracked scratch growths without useful progress.
Skipping empty/unchanged forecasts and stopping when a global boundary already
forces full completion reduces these to 87 forecasts, 251,236 checks, 35,462
steps and 566 growths. Actual cause tracking adds 1,110 probes, 4,238 comparisons
and 36 growths. These remain extra work against the control; scratch growths are
not complete allocation counts and no timing claim follows from this reduction.
All added categories are charged in the heuristic Bake work ledger.

The decisive observed boundaries are `ExtractedExpr` (36 already-pending global
obligations and 29 reached global boundaries) and `hi-bound` (one reached global
boundary). Their merge bodies call known constructors `Smaller` and `bound-min`.
The compiler already has their schemas and merge expressions. The next useful
refinement is an explicit merge read/write/birth footprint and recursive
container effects, preserving constructor-lookup dependencies and ordered
effects. Simply removing the global marker would not prove safe completion.

Evidence and the rejected first probe are in `port-scopes-audit.json`; the
fixture and validation have separate compact JSON records. Reproduce after
preparing the same frozen artifact as above:

```sh
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2 > out/stable-port-congruence/port-scopes-workspace-tests.log 2>&1
PORT_COMPLETION_EVIDENCE="$PWD/out/stable-port-congruence/port-scopes-fixture.json" CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test stable_ports --test cell_ownership --test scoped_completion --test port_completion -j 2 > out/stable-port-congruence/port-scopes-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test stable_ports --test cell_ownership --test scoped_completion --test port_completion -j 2 > out/stable-port-congruence/port-scopes-non-sparse-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2 > out/stable-port-congruence/port-scopes-minimal-check.log 2>&1
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/port-scopes-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/port-scopes-runtime benchmarks/stable-port-congruence/port-scopes-audit-manifest.json out/stable-port-congruence/port-scopes-audit
python3 benchmarks/stable-port-congruence/collect-port-scopes.py out/stable-port-congruence benchmarks/stable-port-congruence
```

Reproduce with the frozen artifact and separate compiler/runtime builds described
above. Use `scoped-executor-{workspace-tests,tests,non-sparse-tests,minimal-check}`
log names. The focused compiler test command adds `--test scoped_completion`;
set `SCOPED_EXECUTOR_EVIDENCE` to an absolute output JSON path to retain the sparse
fixture checkpoints. Build the same release audit features and run:

```sh
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/scoped-executor-runtime benchmarks/stable-port-congruence/scoped-executor-audit-manifest.json out/stable-port-congruence/scoped-executor-audit
python3 benchmarks/stable-port-congruence/collect-scoped-executor.py out/stable-port-congruence benchmarks/stable-port-congruence
```

The collector reads the retained initial attempt from
`scoped-executor-unspecialized-audit/results.json` when available, otherwise its
frozen compact counts from the committed audit. The current runtime intentionally does not offer a flag
to repeat this rejected overhead.
