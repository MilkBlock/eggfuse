# Stable ports, local congruence, and dependency-scoped completion

Objective: remove rebuild stalls introduced by incidental representation work,
then remove other obstacles to multithreading, implement parallel execution,
and improve inference using stronger Bake and compiler information. In
particular, a region must continue while unrelated equality propagation is
pending. This work targets the actual **standalone Cell CPU executor**, not
native egglog.

Current admission: the ordered-publication regression below withdraws the
general overlapping-epoch proof from `3c5739e8`. Corrected sum-bits execution has
six query waits and four RHS waits. The optional uniqueness experiment removes
17 queue obligations but no waits and is **not admitted as an optimization**.
Earlier sections retain historical measurements, not current admission claims.
Optional `--guard-workers` now dispatches completion-candidate reads to a private
persistent pool. This does not remove the ten source waits or parallelize commits;
the experiment remains default-off and has no performance admission.

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
| Costs remain accountable | Read resolution, temporary views, exact Eq tests, condition visits, boundary notifications, queue operations and allocations all reported; semantics and whole-process baselines retained | Field, key, condition, scope and publication-selection operations included in Bake's ledger; worker preparation, dispatch, collection, speculation and allocator requests recorded; speed/scaling admission pending |
| Other parallelism obstacles are removed | Audit and resolution of shared mutable state, equality-directory contention, publication ownership, effect order, allocator pressure, and global work queues | Exact guards use immutable Send + Sync views and local counters; opt-in persistent workers execute them; mutable commits, publication ownership and useful task grouping remain open |
| Parallel inference is implemented and validated | Real concurrent workers; race/lifetime stress; correct boundary effects; scaling and full-cost baseline comparisons | Partial: actual completion-candidate reads run on persistent workers with ordered commits; concurrent mutation, independent task progress and scaling remain open |
| Bake exploits compiler information | Checked candidate coverage, typed read/write footprints, static alias/lifetime facts and local wiring; selection charged against observed total runtime work | Checked merge reads/births, source-union effects, shared influence wiring and compiled bound expressions; cheaper coverage/order proofs and useful parallel task grouping remain open |

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

## Checked merge footprints and future result influence

The previous catalog identified `ExtractedExpr` and `hi-bound` as reached global
boundaries. Their checked merge bytecode is now used to derive separate read and
constructor-birth footprints. Ordinary function calls read a port; constructor
calls query a key and may publish a new fact. These reads constrain which pending
tasks must participate in the original ordered completion pass. They do not
themselves imply a write to the read table. Missing checked code, unsupported
instructions and opaque equality literals retain the global fallback.

Equality-task reachability is closed before adding birth writes. Creating a
fresh constructor result is not an equality between existing results, so a merge
birth does not automatically propagate a union through every table containing
that result sort. Read prerequisites are closed separately. Source `set` and
incoming source unions include the hidden merge reads they may execute, even
when those reads produce no further writes. The existing ordering and epoch
gates remain mandatory. Container sort analysis follows the declared element
sort; the supported `Set<Eq>` no longer makes every table opaque.

Concrete influence also distinguishes the input union already committed from
the result equalities still to come. For a pending table, the input cause roots
index the shared signal wiring to find that table's possible collision outputs,
including peers that are not themselves pending. Only those output roots seed
the subsequent influence walk. This avoids treating every sibling constructor
using the already-changed input as part of each pending group's future work.
Every collision peer shares a changed input port, so the existing complete
native/boundary domain supplies the candidate coverage. No new per-instance
consumer index or operator-bucket scan is introduced. Missing code and the
4,096-visit bound still fall back to the complete typed footprint.

Fixtures verify that an ordered merge can create `Smaller` and a later Run can
consume it while independent congruence remains pending. A second fixture uses
the **same changed input** for A and B: B's mutable consumer completes and its
result is consumed while A stays pending. Other tests cover implicit constructor
reads, source-set demands, hidden read-only callbacks triggered by source union,
container equality and missing-code fallback. A selection unit test isolates
read dependencies from write effects. An exploratory removal of read selection
did not fail the constructor integration fixture, because its constructor births
already selected the same chain; that fixture alone is not credited as proving
the separate read-selection branch. All 261 workspace tests pass (four ignored),
63 focused fixtures pass in both storage configurations, and the minimal runtime
compile check passes.

The frozen sum-bits audit retains all 1,428 ordered Run observations and all
state/RHS/write/resume/Spine digests, also matching the prior binary's hashes.
Ordinary runtime counters equal the global local-congruence control. Compiler
effect edges fall from 99,201 to 30,664; the distinct wait relation has 42,294
edges. The six opaque tables and 38 opaque full completions disappear. There are
71 statically deferrable tables, but this is a proof classification, not a count
of tasks that actually run concurrently.

The runtime now performs ten partial publications (25 table batches). It leaves
90 task occurrences pending across selected completion passes; this counts
remaining tasks per pass, not unique tasks or eliminated work. **No subsequent
source Run or binding executes while those tasks remain pending.** All ten
following waits intersect the ruleset's direct/implicit access footprint;
zero are caused solely by the additional incoming-union footprint. That access
footprint still includes every rule's LHS and RHS, including unexecuted RHSs.
This evidence prioritizes bound access scopes and separating query readiness
from the effects of actual bindings, rather than removing the union safety gate.

This remains an experimental path, not an admitted speedup. The first attempt
with precise merge effects still replayed input influence and needed 1,061,534
membership checks and 230,171 static steps. Restricting the starting points to
future results reduces these to 677,512 checks and 150,901 steps. However, the
previous `f8238efd` experiment needed only 251,236 checks and 35,462 steps because
its coarse global boundaries stopped the proof early. Final tracked scratch
growths rise from 566 to 1,343, head probes from 1,046 to 1,059, and legacy
frontier probes from 638 to 938. Logical equality completions remain 1,046.
The new seed-candidate work is included in Bake's heuristic ledger. Growths are
not complete allocation counts; no timing or worker-scaling claim is made.

The compact evidence retains both intermediate overapproximations, final costs,
and the preceding experiment's counter deltas. Reproduce with the usual separate
workspace, focused and minimal builds, saving logs under `merge-scopes-*.log`.
Include `--test merge_completion` in both focused commands and set
`MERGE_COMPLETION_EVIDENCE="$PWD/out/stable-port-congruence/merge-scopes-fixture.json"`
only for the sparse focused run. Then build the standalone runtime separately:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/merge-scopes-final-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/merge-scopes-final-runtime benchmarks/stable-port-congruence/merge-scopes-audit-manifest.json out/stable-port-congruence/merge-scopes-final-audit
python3 benchmarks/stable-port-congruence/collect-merge-scopes.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Query snapshots and matched-rule RHS demands

The `9a5c0a18` catalog's ten waits all intersected the combined query/RHS access
footprint. That footprint included rules with no bindings. The next compiler
proof splits query tables from each rule's RHS accesses, hidden merge reads and
incoming-union effects. `--port-scopes` first waits for query readiness before
dirty-reader selection, seals all matching into one source snapshot, then waits
only for the RHS demands of matched rules. The pending work still uses its
original epoch and ordered completion path. An empty Run has no RHS demand;
its unchanged result still controls a saturating schedule.

A wait between matching and RHS publication must retain the matched Entry
origins and sealed Spine cursors, receipt forwards and frame ancestors. The
binding union generation is captured before matching, so old bindings cannot
receive a freshness certificate from the later completed graph. Matched origins
remain alive until the bindings are consumed; ordinary end-of-Run publication
can then clean them while retaining any still-outstanding deferred consumers.

Six short integration fixtures cover independent committed facts and subsequent
consumption, an actual RHS access wait, an explicit-union effect fence, an empty
saturating Run, the immutable matching snapshot, and matched Entry lifetime.
The independent fixture commits **three fact births through two bindings**, and
a subsequent Run consumes the independent result while one same-sort congruence
task remains pending. Temporarily clearing matched origins during publication
makes the Entry-lifetime fixture fail with an out-of-bounds sealed cursor;
restoring the guard makes it pass. The full workspace passes 267 tests (four
ignored), the 69 focused tests pass in both sparse and non-sparse configurations,
and the runtime compiles without default features. Global-observer configurations
keep their barriers and are not counted as independent-progress evidence.

The frozen sum-bits audit again matches all 1,428 ordered Run observations and
all state/RHS/effective-write/resume/Spine hashes, including the previous binary.
Ten completion waits split into **three query waits and seven matched-RHS waits**.
Of the seven RHS waits, six intersect the matched rules' access footprint and
one is caused solely by the conservative incoming-union expansion.
There are 40 bindings matched while old work is pending, but **zero bindings or
RHS mutations execute before that pending work completes**. Two empty Runs carry
pending work and lose the fully-settled idle shortcut (769 becomes 767); they
produce no independent result. All other ordinary runtime counters match the
global local-congruence control. This is not admitted as a speedup.

The per-rule RHS union costs 3,614 demand probes, eight scratch-vector growths and
13 matched-rule visits, all charged in Bake's heuristic work ledger. Readiness
checks include both the post-completion proof and classification of actual access
versus conservative union waits: 4,878 checks versus the previous 4,257. Carrying
the empty Runs raises partial publications from ten to twelve and peak retained
receipt forwards from zero to twelve. The existing proof still walks 150,901 static
steps and incurs 1,343 tracked scratch growths; these growth counters are not a
complete allocator census. Fact births and function updates have separate
counters from logical matches and executed bindings. No timing or real-worker
scaling claim is made. The remaining question is which bound accesses and effect
ports actually intersect the pending Cell region, rather than merely sharing a
table; the union safety gate and ordered mutable effects remain live obligations.

Reproduce with the frozen artifact and the separate workspace, focused and
minimal commands above, using `staged-scopes-*.log` names. Add
`--test staged_completion` to both focused commands (along with the five suites
from the merge refinement), and set
`STAGED_COMPLETION_EVIDENCE="$PWD/out/stable-port-congruence/staged-completion-fixture.json"`
only in the sparse focused run. For the negative control, temporarily change
`if !self.retain_matched_origins` to `if true` in `stage_spine.rs`, run only
`matched_entry_origins_survive_completion_and_publication_before_rhs`, capture
`staged-scopes-origin-negative.log`, restore the source, and rerun the sparse
focused tests. Do not run concurrent builds during this source mutation. Then
build the standalone runtime separately:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/staged-scopes-runtime
python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/staged-scopes-runtime benchmarks/stable-port-congruence/staged-scopes-audit-manifest.json out/stable-port-congruence/staged-scopes-final-audit
python3 benchmarks/stable-port-congruence/collect-staged-scopes.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Bound constructor effects and pure source epochs

The preceding audit's seven RHS waits all occur in `type-helpers`, rules 576 and
577. The six apparent access waits include the future result-union expansion of
`TypeList-ith` Set; they are not six direct reads of `Base` and its consumers.
Optional `CELL_CPU_PROGRESS` output now lists the actual matched rules and their
conflicting pending/access tables. It adds no work when progress output is off.

The new opt-in `--pure-epochs` path keeps query readiness, then checks the bound
RHS. Its compiler class admits copies, checked i64 arithmetic, explicit union and
shared-owned constructor Set. Set tables must already be complete. An already
true union or Set has no new equality effect. Other candidates require a closed
pure influence proof using the existing root domains and shared template
wiring. The supplied result of every Set is included, even when its key is
absent: two bindings may otherwise collide with each other's newly born facts.
Mutable/legacy users, missing code and budget overflow retain the old wait.
No custom merge is executed during this preview.

The table queue now stores the original epoch with each pending fact. The new
mode admits multiple pure source epochs in one table; repeated notification of
one fact keeps the maximum epoch. Completion also joins the current task epoch
with both rows' epochs before publishing a collision equality, so an older task
cannot backdate a result after a newer peer has completed. Ordinary scoped modes retain their table-wide
assertion and the default flat queue remains unchanged. This adds one u64 epoch
payload per table-queued fact; it does not add a producer/consumer reverse index.
The reference ordering of table heads and facts remains intact.

Eight fixtures establish actual progress across pure epochs, preserved row epochs
under repeated input changes and a newer completed collision peer, colliding absent-key Sets, no-op effects with a
mutable user, a live mutable-boundary rejection and the bounded-walk fallback.
They also exercise resumed shared Entries after two-dimensional key collisions.
Removing the peer-epoch join in a negative control backdates the final G row to
epoch one instead of two; restoring it makes the fixture pass.
The progress fixture commits one source union and two new facts, then consumes
the new result while old congruence remains pending in the same table. Effective
source unions are now counted separately from logical bindings, fact births and
function updates. Tests verify the final state and ordered source observations.
These are standalone single-thread Cell CPU results, not native egglog or worker
scaling results.
The workspace passes 275 tests (four ignored), and all 77 focused tests pass in
both sparse and non-sparse configurations. The minimal runtime compile check
also passes.

Sum-bits retains all 1,428 ordered source observations and the exact state, RHS,
effective-write, resume and Spine hashes from `e30c2e1d`. However, its three
admitted batches are **all no-ops**. Twelve bindings execute while work remains
pending, but zero new facts, function updates or effective source unions do so.
The total ten completion waits remain: three query/seven RHS becomes six
query/four RHS. Three additional empty Runs lose the fully-settled idle shortcut
(767 becomes 764), and partial publication passes increase from twelve to
eighteen without increasing the 25 published table batches.

The four candidates with actual changes all hit `TypeList-length`. The current
proof includes Set key roots and both sides of each union. It therefore includes
unchanged inputs in the potential effect closure. This rejection does not prove
that these four RHSs actually write `TypeList-length`; the next proof needs to
separate reads, displaced roots and complete operator-filtered collision outputs.
Removing that boundary without such a proof is not justified.

This remains unadmitted as a performance improvement. The extra preview performs
25 key lookups, 105 bytecode operations, 275 copied/inserted value slots and 83
tracked scratch growths. Ordinary key lookups rise from 19,326 to 19,351. The
influence proof adds 172 static steps (150,901 to 151,073), while readiness checks
rise from 4,878 to 7,268. Pure mode also performs 1,046 completion-epoch checks
without joining any different epochs on this workload. These operation counters
and selected growth events are not a complete allocation census or a latency
model. Bake's heuristic ledger
charges the new preview and epoch bookkeeping; no timing claim is made.

Reproduce with the same frozen program and separate builds as above. Save the
workspace, focused, non-sparse and minimal logs under `pure-epochs-*.log`, add
`--test pure_epochs` to the preceding six-suite focused commands, and set
`PURE_EPOCH_EVIDENCE="$PWD/out/stable-port-congruence/pure-epochs-fixture.json"`
only for the sparse focused run. To reproduce the negative control, temporarily
replace `epoch.max(row).max(peer.unwrap_or(0))` with `epoch` in
`ownership_pending.rs`, run only
`an_older_task_cannot_backdate_a_collision_with_a_completed_newer_peer`, and save
`pure-epochs-peer-negative.log`. Restore the source before rerunning the focused
suite. Do not run concurrent builds during that mutation. Then:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/stable-port-congruence/pure-epochs-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/pure-epochs-runtime benchmarks/stable-port-congruence/pure-epochs-audit-manifest.json out/stable-port-congruence/pure-epochs-final-audit
python3 benchmarks/stable-port-congruence/collect-pure-epochs.py out/stable-port-congruence benchmarks/stable-port-congruence
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

## Displaced source effects and complete collision peers

The prior catalog's seven `type-helpers` waits are still the opportunity: rules
576/577 only copy values, compute an i64 offset, union bound `BaseType` values and
Set `TypeList-ith`. Typed compiler facts already establish this restricted RHS
class and complete direct Set-table reads. Actual bound execution now separates
read-only keys, absent-key births and known result equalities. The goal is to
commit these source effects across Runs while older `Base` congruence remains
pending, without executing or reordering an unknown mutable merge.

The preview maintains a finite exact-key overlay for earlier births in the same
sealed RHS. Thus two initially absent Sets are not assumed independent. Its
known equality pairs are grouped transitively before effects are walked: choosing
the larger endpoint of each pair independently would miss roots displaced by a
chain. Shared template wiring on displaced members identifies affected operators;
all members then supply those operators' collision outputs, including the
unchanged representative. Unrelated operators on the unchanged input no longer
start the closure. The output closure also follows source aliases and new Set
sites. A birth whose input may change under older pending work contributes its
output, using the pending forecast's complete root frontier; unknown frontiers
stay conservative. No instance-owned producer/consumer index is introduced.

Six new short fixtures cover unchanged unrelated users, same-operator peers with
mutable consumers, transitive source pairs, read-only birth inputs, birth keys
that collide after source union, and duplicate initially absent keys. Temporarily
omitting the unchanged-side candidates makes the peer fixture incorrectly admit
its batch as closed-pure; restoring that code restores rejection. Rejection
retains ordinary scoped/eager handling, which can still advance unrelated work.
The existing cross-epoch,
shared Entry, publication lifetime and budget fixtures remain in the test suite.
The production path remains opt-in under `--pure-epochs`. The workspace passes
281 tests (four ignored); sparse and non-sparse focused suites each pass 83 tests,
and the no-default-feature runtime compile check passes.

The retained final audit compares the same frozen sum-bits program against the
local-congruence and staged-scope controls, and the committed `210b57dd` hashes.
All 1,428 Runs retain exact state, ordered RHS, effective writes, resumes, schedule
and normalized Spine results. Four nontrivial batches now join the three no-op
admissions. They commit **five effective source unions and six new facts while
older congruence is pending**. RHS waits fall from four to zero; six query waits
remain, so total waits fall from ten to six. Six mixed-epoch task insertions,
one notification-epoch advance and three causal completion-epoch joins now occur
on this workload. This is the standalone single-thread Cell CPU executor.

This does not establish a full-cost speedup or worker scaling. The preview still
performs 105 instructions, 25 key reads, 275 copied/inserted slots and 83 tracked
scratch growths. It adds four exact-key overlay comparisons. The proof adds
288 source-relation steps and 622 new-site checks, retains at most 599 frontier
root entries, and still walks shared wiring at runtime. Static steps rise from
151,073 to 151,515 and tracked proof/forecast scratch growths from 1,359 to 1,389.
The audit records these alongside four fewer forecasts, 2,224 eliminated RHS
demand probes, 1,525 fewer membership checks and two fewer total key lookups.
Query/publication costs remain. Growth-event counters are not a complete allocator census, and Bake's
charged work ledger is not elapsed time. Reusable compiler/Bake certificates and
concurrent ownership remain unfinished work.

Reproduce using the same Cargo environment and separate compiler/runtime builds
as the preceding experiments. Save workspace, focused, non-sparse and minimal
logs as `displaced-epochs-{workspace-tests,tests,non-sparse-tests,minimal-check}.log`.
The focused suites are `pure_epochs`, `staged_completion`, `scoped_completion`,
`port_completion`, `merge_completion`, `stable_ports` and `cell_ownership`.
Set `DISPLACED_EPOCH_EVIDENCE` to the absolute
`out/stable-port-congruence/displaced-epochs-fixtures` directory only for the
sparse focused run. For the negative control, temporarily skip `id == leader`
in the source-group member loop in `pure_effects.rs`, then run
`unchanged_input_peers_of_the_same_operator_keep_the_mutable_boundary` and save
`displaced-epochs-peer-negative.log`. Restore the file before positive checks.
Finally build only the standalone audit runtime and run:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/displaced-epochs-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/displaced-epochs-runtime benchmarks/stable-port-congruence/displaced-epochs-audit-manifest.json out/stable-port-congruence/displaced-epochs-final-audit
python3 benchmarks/stable-port-congruence/collect-displaced-epochs.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Compiler-derived bound effects and the remaining query fences

The preceding execution catalog admits seven `type-helpers` batches but pays
105 preview instructions, 275 copied/inserted values and 83 scratch growths. The
same compiler facts that restrict those RHSs to Copy, checked i64 arithmetic,
Union and shared-owned constructor Set allow preprocessing their value flow.
The new plan removes Copy operations by sharing expression addresses and reads
only referenced binding slots. Arithmetic uses checked Add/Sub/Mul operations and
dense temporary values. Ordered Set/Union effects retain the exact-key overlay
and displaced-root/complete-peer proof from `10ae5ece`; no collision or equality
is assumed by the compiler. All arithmetic remains represented, including an
unused operation whose failure must retain the original failing RHS path.

Plans are shared once per template through immutable Arc code, and are prepared
only when `--pure-epochs` is enabled. Ordinary scoped execution does not retain
this code. Sum-bits prepares 59 templates, 146 value expressions and 60 effects,
eliminating 72 static Copy instructions. The old whole-binding clone and mutable
slot-map preview are removed, including the no-longer-used slot-capacity helper.
This establishes reusable read-only code, not concurrent Graph ownership.

The same sum-bits audit retains all 1,428 source observations and exact
state/RHS/effective-write/resume/Spine/schedule hashes. All port-influence and
completion-queue counters match `10ae5ece`. The existing five effective source
unions and six fact births still occur while prior congruence is pending; there
are still six query waits and no RHS waits. Preview scratch growths fall from
83 to 3 and materialized values from 275 to 155. Executed arithmetic/effect
instructions fall from 105 to 65 after removing Copy. The new evaluator also
performs 155 expression steps and 105 bound-input reads; those operand costs were
not separately measured by the old counter. They are charged to Bake's work
ledger. These are selected operation/allocation events, not a whole-execution
allocation count or measured speedup.

Three new short tests cover nested arithmetic and consumed births across pending
work, checked overflow preserving the original failing RHS, and an arithmetic
key that must find an existing result with a mutable user. In a negative control,
replacing compiled multiply by addition probes the wrong key and incorrectly
admits that last batch. Restoring the operation restores rejection. This tests
the preview's actual effect proof, rather than only the unchanged RHS evaluator.
The workspace passes 284 tests (four ignored), both sparse and non-sparse focused
suites pass 86 tests, and the no-default-feature compile check passes.

Progress-only query diagnostics identify the outstanding waits:

| Run | Ruleset | Effective congruence unions | Other observed work |
| --- | --- | ---: | --- |
| 23 | type-analysis | 9 | Base and HasType query versions advance |
| 79 | type-helpers | 0 | One TCons query version advance; no collision or legacy repair |
| 86 | type-analysis | 1 | Base and HasType query versions advance |
| 169 | type-analysis | 12 | Base and HasType query versions advance |
| 477 | always-run | 0 | Two Concat query version advances; no collision or legacy repair |
| 581 | cleanup-drop | 50 | DelayedDropUnion query versions advance |

Zero unions at Runs 79/477 do not authorize dropping publication. Separating
those three row-publication obligations from potential congruence, with complete
candidate and snapshot proofs, is the next concrete opportunity. Broad runtime
influence walks, shared mutable ownership and real worker execution remain open.
This result measures the standalone single-thread Cell CPU, not native egglog.

Reproduce using the same Cargo environment and seven focused suites from the
preceding section, with `compiled-effects-` log names. Save the workspace,
sparse/non-sparse focused and no-default-feature logs. For the negative control,
temporarily replace `Self::Mul => a.checked_mul(b)` with
`Self::Mul => a.checked_add(b)` in `completion_rhs.rs`; run only
`compiled_arithmetic_keys_select_the_actual_mutable_collision_result`, saving
`compiled-effects-arithmetic-negative.log`. Restore the source before all positive
checks. Build the standalone audit runtime separately from compiler tests:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/compiled-effects-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/compiled-effects-runtime benchmarks/stable-port-congruence/compiled-effects-audit-manifest.json out/stable-port-congruence/compiled-effects-final-audit
python3 benchmarks/stable-port-congruence/collect-compiled-effects.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Ordered publication and the rejected uniqueness experiment

The preceding catalog identified Runs 79/477 as potential discharge points:
one TCons and two Concat rows needed publication after a no-collision check.
Compiler facts already provide equality-key columns, complete owned-operator
coverage and shared input routes. Those facts permit a sufficient uniqueness
proof: if one complete input domain contains no other live constructor of the
same operator, the changed key cannot collide. This is stronger than merely
observing zero unions at a query fence.

`--unique-port-publication` enables this opt-in experiment on top of pure epochs.
It chooses the smallest native/boundary input domain and follows shared condition
input routes (or the complete original shape slice when the bounded plan is
absent). It checks live facts and actual operator identity, including hidden and
already pending peers. A proof must find its own source. There is no per-producer
consumer list, full operator scan, candidate sorting or per-attempt heap buffer.
The 64-visit budget covers anchor reads, signals and static steps. Unknown or
large domains retain normal completion. Accepted rows publish their joined epoch
and query change directly, removing the key queue insertion and completion.

Uniqueness at one instant is insufficient. In the regression, a batch first
moves a high-index F input to N(0), then moves a lower-index F input to N(0).
Publishing the first F early makes it a completed collision survivor; ordinary
completion would process the lower witness first. This changes ordered exported
witnesses. The fixture's scalar record value remains unchanged; no numeric
divergence is claimed. Disabling the remaining-unions guard reproduces this
failure. The experiment now also refuses to bypass existing lower completion
tasks or in-flight/queued legacy work. It advances only a no-collision prefix of
the existing completion order.

Splitting these unions across source Runs exposed the same ordering hole in the
previous pure-epoch proof, even with the new experiment disabled. Pure
constructors do not imply order-independent survivor selection. The corrected
proof rejects a new affected operator when it overlaps any older completion
footprint, including effects reached through shared output wiring. This is
conservative: it does not claim every same-operator overlap intrinsically needs a
barrier. A new fixture still commits an H equality while F completion is pending
in the same Eq sort. Other fixtures retain independent births and consumption.
The five old tests expecting overlapping epochs now require the ordering fence
and retain their exact state, schedule, visibility and epoch assertions.

All three sum-bits lanes retain the previous exact state, ordered RHS, effective
write, resume, normalized Spine and schedule hashes across 1,428 Runs. The
corrected pure-epoch lane rejects four Base overlaps: RHS waits return from zero
to four, and the previously admitted five effective source unions and six births
while pending return to zero. Those earlier admission claims are withdrawn.
The current proof does not establish finer independence for those four batches.

Compared with that corrected control, the uniqueness experiment produces:

| Observed work | Control | Experiment |
| --- | ---: | ---: |
| Equality-key enqueues / completions | 1,046 / 1,046 | 1,029 / 1,029 |
| Query waits / RHS waits | 6 / 4 | 6 / 4 |
| Stable port reads | 120,494 | 120,668 |
| Queue head probes | 1,059 | 1,292 |
| Queue head updates | 1,599 | 1,565 |
| Influence forecasts / tracked scratch growths | 97 / 1,360 | 97 / 1,360 |

The proof is attempted 1,091 times and publishes 17 rows. It performs 226 anchor
reads, 1,244 signal visits and 1,348 static steps. Including membership, order,
site/operator checks and publication, Bake charges 7,506 added proof events.
The local congruence visitor does less work, but unchanged waits and the added
checks do not justify admission. There is no timing claim or complete allocator
census; selected scratch-growth counters and diagnostic maps are not a count of
all allocations. The experiment stays disabled by default.

The small positive fixture changes pending work from one to zero, publishes the
row without a key enqueue and lets the next Run consume it. Tests also cover
foreign operators, pending/hidden peers, multi-input notifications, deletion and
recreation, older-task/newer-row epochs, and budget fallback. The workspace passes
295 tests (four ignored); both sparse and non-sparse focused suites pass 97;
the minimal compile check passes. These are standalone single-thread Cell CPU
results, not native egglog or multithreaded speedup.

The next useful compiler/Bake information must prove smaller independent
regions and admissible publication order without repeating a runtime domain
walk. Existing Eq guards, boundary coverage, liveness and row epochs remain
obligations. Shared mutable Graph ownership and actual workers are still open.

Reproduce using the preceding eight focused suites (add `unique_publication` to
the seven listed above), with `unique-publication-` log prefixes. Set
`UNIQUE_PUBLICATION_EVIDENCE="$PWD/out/stable-port-congruence/unique-publication-fixture.json"`
for the sparse suite. Save the workspace and no-default-feature checks as usual.
To reproduce the batch negative control, temporarily replace the
`remaining_unions != 0 || !self.pending_unions.is_empty()` guard with `false` in
`unique_port_publication.rs`, run only
`early_publication_preserves_survivor_order_for_ordered_merge_observations`, and
save `unique-publication-batch-negative.log`. For the epoch negative control,
disable the two forecast-order rejection checks in `pure_effects.rs`, run only
`separate_source_epochs_preserve_ordered_merge_observations`, and save
`unique-publication-epochs-negative.log`. Restore sources before all positive
checks and the standalone audit build:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/unique-publication-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/unique-publication-runtime benchmarks/stable-port-congruence/unique-publication-audit-manifest.json out/stable-port-congruence/unique-publication-final-audit
python3 benchmarks/stable-port-congruence/collect-unique-publication.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Immutable guard evaluation

The preceding run provides two useful constraints. Four Base overlaps cannot
currently cross a source switch without an ordering proof, and speculative
uniqueness checking adds work without removing waits. Inspecting the first
rejected overlap also shows that a pending survivor may have a later FactRef
than a newly changed peer. An existing stable target is therefore not a general
permission to reorder the remaining chain. The conservative source fence stays.

There is a separate implementation obstacle that does not require relaxing that
fence: local guard evaluation borrowed mutable Graph only to resolve ports and
update counters. The new `port_guard::ReadView` borrows the equality relation and
plain component bindings. `KeyGuard` adds a borrowed live node and an already
canonical key from the same read epoch. These types and shared condition plans
are Send + Sync without unsafe implementations. They contain no Graph, Rc-owned
packet, graph copy, canonical-row copy or shared mutable counters.

Both real runtime paths now use this evaluator: `exact_port_candidate` for
foreign/birth-index candidates and the local shared-condition loop. Candidate
selection still checks liveness and pending status in order. Operator/scalar/Eq
checks return their actual work in a local `Work` value; the coordinator folds
that work into the existing Bake counters. Successful guards do not authorize
retirement or establish domain completeness. The existing ordered commit and
boundary checks retain those obligations.

The compiler already establishes that both symbols of a local Eq guard belong
to one composed component. The evaluator uses that fact to resolve the component
once per condition, then reads its signal array directly. Local target-node Rc
cloning is removed, and scalar guards compare borrowed values. No parallel
speedup or constant-factor speedup is inferred from these code changes.

Two worker fixtures exercise the actual new kernels. Two scoped threads share a
condition and its bindings; three scoped threads evaluate descriptors borrowed
from a live Graph, including rejected operator and scalar guards. They return
separate counts and leave Graph counters unchanged. Multi-input conditions still
require every equality; shared-symbol checks retain their shortcut. A new borrow
observes an alias through the original PortRef, hidden peers remain eligible,
and deletion rejects the expired instance. The Rust borrow prevents mutation
while readers run. This establishes concurrent reading within a sealed epoch,
not an asynchronous result protocol across graph mutation.

The frozen sum-bits audit executes all three existing lanes for 1,428 Runs. Exact
state/RHS/effective-write/resume/Spine/schedule hashes and **all deterministic audit
counters** match `a64d43f1`. The pure lane still visits 18,080 key candidates,
compares 35,321 fields and visits 611 local conditions; query/RHS waits remain
six/four. Profiling clocks are excluded from counter equality and are not a timing
gate. The workspace passes 299 tests (four ignored), sparse and non-sparse focused
suites each pass 99, and the minimal compile check passes.

The Executor still invokes these kernels serially. Actual parallel execution is
verified only in the scoped worker fixtures. The next required work is to group
useful jobs and connect persistent workers without copying Graph or scanning
unrelated tables, retaining the source snapshot and ordered publications. Task
preparation, dispatch, result storage, allocations and contention must be charged;
small condition jobs are not automatically worthwhile parallel tasks.

Reproduce with the same build environment, adding `--test read_guards` to the
eight preceding focused suites and using `read-guards-` log prefixes for the
workspace, sparse, non-sparse and minimal checks. Retain the previous
`unique-publication-final-audit/results.json` for deterministic counter comparison.
Build the standalone audit runtime separately from compiler tests:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/read-guards-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/read-guards-runtime benchmarks/stable-port-congruence/unique-publication-audit-manifest.json out/stable-port-congruence/read-guards-final-audit
python3 benchmarks/stable-port-congruence/collect-read-guards.py out/stable-port-congruence benchmarks/stable-port-congruence
```

## Persistent workers for completion-candidate reads

The previous execution established immutable guard inputs but still invoked all
guards on the coordinator. It also retained ten source waits. Earlier ordering
regressions prohibit speculating across arbitrary completion tasks: committing
one can change another's pending eligibility, aliases, liveness and survivor.
This iteration therefore tests the narrower opportunity of evaluating candidates
for one popped task concurrently. It discharges no additional cross-Run work.
Shared typed wiring and complete candidate domains retain their existing proof;
no new order or publication independence is inferred from Send + Sync.

`--guard-workers N [--guard-grain M]` enables a private persistent Rayon pool;
`N >= 2`, `M >= 1`, default `M = 32`. Lists shorter than `N * M` keep the existing
serial path. Larger lists run bounded rounds of at most `N * M` candidates,
divided into chunks of `M`. The pool is built once, not once per condition.
[ThreadPool::install](https://docs.rs/rayon/1.12.0/rayon/struct.ThreadPool.html#method.install)
allows these tasks to borrow the already separated read data and finish before
the Graph is mutated. This does not require converting Graph to Arc, cloning
canonical rows, adding unsafe Send implementations or maintaining worker-owned
reverse indexes. The source row's values and target Stored nodes are borrowed;
their Rc owners stay on the coordinator.

The coordinator binds live candidates, preserving the original pending filter.
Workers evaluate operator/scalar/Eq guards and return local work into bounded
scratch descriptors. After every round has finished, selection consumes results
in the original candidate order. Only the earliest match or error is observable;
a speculative error after that point cannot override it. The selected result
uses the original serial retirement/publication path. Every executed guard,
including discarded results, is charged. No reads overlap a union or deletion,
so this protocol needs no stale-result recovery, but also does not establish
independent progress during mutation.

The frozen sum-bits audit matches all 1,428 Runs and exact ordered state, RHS,
effective-write, resume, Spine and schedule hashes in all four lanes. Disabling
workers preserves every previous deterministic work counter. Enabling them
leaves committed effects and source waits unchanged (six query, four RHS).
Extra port/key reads exactly equal recorded speculative guard work.

The measured candidate distribution explains the granularity limit: 1,036
covered batches contain 4,985 candidate positions; 855 batches have fewer than
eight positions, and the maximum is 49. The remaining ten source attempts use
the existing uncovered-shape fallback.

| Configuration | Dispatched candidate batches | Dispatch rounds | Prepared candidates | Live guard descriptors | Extra candidate visits after the ordered winner |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2 workers, grain 1 | 758 | 1,379 | 2,706 | 1,985 | 447 |
| 2 workers, grain 32 | 0 | 0 | 0 | 0 | 0 |
| 4 workers, grain 8 | 17 | 27 | 630 | 458 | 154 |

Both workers participate in the fine-grain execution, and all four participate
in the four-worker execution. Distribution across workers is scheduling-dependent;
the guard work above is deterministic. The fine-grain lane adds 255 port reads,
187 key-field comparisons, 56 equality checks and 16 scalar checks. The four-worker
lane adds 158 port reads/key-field comparisons. Candidate preparation, lookup,
result collection, rounds, chunks and scratch requests have separate counters.
Scratch descriptors fit inline in these lanes; a larger fixture exercises and
charges the heap path. A zero scratch count does not mean zero scheduler cost.
Bake's deterministic ledger also charges batch selection, task preparation,
round/chunk dispatch, collection, scratch allocations and pool/worker creation.
Speculative guard work is already included in the ordinary guard counters and
is not charged twice. A real-execution credit fixture rejects missing dispatch
counters and assigns negative net work savings to parallelizing the same guards.
These equally weighted event counts remain an uncalibrated latency proxy.

A separate allocator diagnostic includes Graph/runtime setup, pool construction
and execution. Against its own serial control, the two-worker fine-grain lane
adds 47 allocations and two reallocations during setup (20,046 requested bytes),
then 23 allocations during execution (32,032 requested bytes). The idle coarse
pool has the same measured setup increment and no execution increment. The
four-worker lane adds 83 allocations and four reallocations during setup
(34,836 requested bytes), then two allocations (112 requested bytes) during
execution. These are one execution's allocator requests, not stable timing,
RSS, thread-stack size or a bound on scheduling-dependent allocations. Parsing
and export are outside those allocator intervals; common audit costs remain
present in both control and worker lanes.

Validation covers 304 workspace tests (four ignored), 103 focused tests in each
storage configuration, and the minimal compile check. The focused coverage adds
partial multi-input equality, wrong-operator/scalar peers, ordered cascades,
deletion/recreation, small-list fallback and spilled scratch. The final extra
scratch and credit tests are recorded separately from the earlier full suite,
avoiding a repeat of unchanged tests.

This is **default-off experimental parallel reading, not an admitted speedup**.
No wall-clock benchmark or scaling campaign was run. Per-task work is too small
to infer a useful benefit, and fine-grain dispatch adds many synchronous joins.
The next structural requirement is a compiler/Bake proof that multiple ready
tasks can share a read phase without invalidating ordered results. Increasing
candidate counts to occupy workers would defeat the local pruning objective.
The query matcher, mutable effects, publication ownership and source fences still
need their own parallel protocols.

Reproduce using the previous nine focused suites plus `--test parallel_guards`
and `parallel-guards-` log prefixes. Our first full suites contain the first three
worker tests; the final scratch test has separate `parallel-guards-wide-` logs
in the same three configurations. The collector also accepts fresh full-suite
logs containing all four tests without counting the scratch test twice. The
additional library test `parallel_guard_dispatch_cannot_hide_preparation_from_bake_credit`
has a `parallel-guards-credit-tests.log` from the compiler's all-features library
suite; the collector likewise avoids counting it twice in a fresh full run.
Preserve the `read-guards-final-audit/results.json` control. Build
standalone audit executables separately from compiler tests:

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/parallel-guards-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/parallel-guards-runtime benchmarks/stable-port-congruence/parallel-guards-audit-manifest.json out/stable-port-congruence/parallel-guards-final-audit
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics -j 2
cp "$CARGO_TARGET_DIR/release/eggfuse-cell-runtime" out/stable-port-congruence/parallel-guards-allocator-runtime
CELL_CPU_PROGRESS=1 python3 benchmarks/result-port-repair/audit.py out/stable-port-congruence/parallel-guards-allocator-runtime benchmarks/stable-port-congruence/parallel-guards-audit-manifest.json out/stable-port-congruence/parallel-guards-allocator-audit
python3 benchmarks/stable-port-congruence/collect-parallel-guards.py out/stable-port-congruence benchmarks/stable-port-congruence
```
