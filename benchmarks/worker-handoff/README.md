# Compiler preparation for ae123cf9 worker handoff

This is a preparation artifact for the standalone Cell CPU, not a runtime
optimization or native egglog measurement. The target branch's query workers
complete point-query Entries, return Matched values, restore source ordinals and
select winners before making Binding/StagePatch and executing RHS serially.

Opportunity: use actual successful Cell/Run transitions from the last catalog
to select compositions that discharge repeated binding assembly, retained-slot
transfers and internal publication. Execution frequency selects candidates; it
never proves validity. This artifact consumes the existing checked catalog; it
does not train a new catalog or manufacture execution counts.

Generate on this branch:

```
cargo run -p eggfuse-cell-compiler --features iterative-bake --example emit_worker_handoff -- PROGRAM.json HANDOFF.json
```

`worker_handoff::validate(program, handoff)` reconstructs the entire artifact,
rejecting altered program identity, operations, catalog or obligations. The
sidecar is deliberately not installed in Program or used to grant execution
permission. The exact program digest binds rule/operation/slot IDs. It must be
regenerated after recompiling or changing the Bake catalog.

Information supplied:

- Per rule: template ID, frame width, successful-match input slots, input slots
  used by RHS, and existing slot-definition coordinates.
- Per original RHS operation: read slots, destination slot, table, effect kind
  and candidate shared Entry IDs. Literals and instruction semantics remain in
  the authoritative Program, not copied into another instruction language.
- One shared Entry schedule with its existing consumer projections/control.
  Candidate routing means matching the source table only; it is NOT proof that
  a query succeeds, that a mutable read publishes, or that all candidates can
  receive a result. Existing aliases/last-write selection remain authoritative.
- Reconstructed stage contracts: exported source sites, inherited result-slot
  mapping, query/RHS reuse proofs, next states, restart and retained distance.
  These describe existing bounded paths, not arbitrary cross-stage closure.
- Live obligations: source ordinal/winner/delta ownership, residual enumeration,
  actual returned receipt, current Eq, mutable reads, visibility, retirement,
  generation and cross-thread ownership. Every worker_execution_proved flag is
  false: primitive classification alone is not a purity/error-order proof.

Integration points in ae123cf9:

1. query_workers::finish_run: retain successful frame ownership after winner
   selection; use rhs_input_slots rather than inventing another binding layout.
2. runtime's Binding::matched / StagePatch construction: consume that same
   storage, maintaining original rule/ordinal order and ordinary deduplication.
3. RHS and Shared Entry: resolve actual receipts into the export slots, then
   use the existing Entry projections and state transitions. Remove a packet
   or transfer only after proving its visibility, replacement and lifetime
   obligations; cross-Run edges still wait at the original Run boundary.

The sidecar currently depends on this branch's v2 state-contract support
(7d4144b1 and its prerequisite state-plan implementation); it is not advertised
as a standalone cherry-pick onto ae123cf9. Its JSON is available immediately
for downstream design; compiler integration must port the checked contract
producer as well. No change is made to the other worktree.

Against the current branch, runtime execution and program bytes are unchanged:
no runtime loader, dispatch or publication path consumes this sidecar. The
sample records static counts/encoded size, not saved operations or speedup.
The existing semantic exports remain applicable because no executor or input
artifact changed. Tests reconstruct the fixture and reject forged metadata.

## v2: compact contracts and conservative RHS/repair forecast

The next iteration keeps the original successful-instance catalog as its
bounded cross-Run evidence. It does not infer new proven transitions from hit
counts. Scheduled switches can discharge inherited result transfers only where
the existing stage proof says so; speculative wider repair stays a live duty.

V2 replaces repeated stage query/sorts/effects with references through
activation.rule and the exact Program digest, preserving pivot, completion
proofs, transitions and retention. Effects reference entry_routes by table
index; that shared array supplies candidate Entry IDs once per table. This
supersedes v1's per-effect entry_candidates arrays. Consumers must reject an
unknown schema and reconstruct-validate before using these references.

completion_forecast reuses completion_plan::Plan::derive, not another solver.
It exposes query demands separately from conditional RHS accesses/repair
obligations, transitive completion reads, merge descriptors, opaque tables,
Run scopes and the existing conservative deferrable classification. An actual
binding activates RHS demands. Union propagation, mutable merge order, current
representatives, pending writes and liveness remain runtime responsibilities.
This forecasts a possible affected scope, never an actual collision, result
identity, repair count, or permission to move a whole RHS into a worker.
Unsupported derivation is explicit and authorizes no bypass.

The forecast stores identical ordered scalar arrays once in plan.vectors;
plan.body references them as {"vector": index}. Resolve these references to
recover the exact existing Plan serialization. This preserves order, masks,
empty arrays and conservative scope. The forecast remains preparation only;
it has no runtime consumer yet and earns zero saved-operation credit.

`forecast-check.json` compares compact UTF-8 JSON against d97e42b3 on the same
program. Stage contracts shrink 78,410 -> 27,695 bytes. Sharing forecast vectors
shrinks that representation 381,567 -> 203,366 bytes. Including the new forecast,
the complete sidecar grows 905,056 -> 1,044,950 bytes: no overall size win or
runtime speedup is claimed. These are encoded artifact bytes, not heap/RSS.
Reproduce with the emitter above and compact JSON serialization on both commits;
use separate checkout/target directories. The executor and source artifacts
are unchanged, so saved semantic exports remain applicable. Tests verify
contract preservation, route tables, vector roundtrip and forged-data rejection.

## Runtime obligation sharing

`completion_plan::Plan::derive` now interns identical immutable query/RHS/access
lists across rules using exact ordered contents. Runtime rule demands reference
`Rc<[usize]>` owners instead of allocating independent Vec payloads. The
compile-local interning registry is dropped before execution; no runtime
reverse-consumer list or parallel fact graph is added. All demand lookups and
conservative repair checks remain authoritative and unchanged.

On the same frozen sum-bits artifact, 1,746 lists share 744 owners. Logical
payload changes from 496,824 bytes to 82,112 bytes including estimated Rc
headers; shared handles occupy another 27,936 bytes. This excludes allocator
rounding, transient interning, other Plan members and whole-process RSS. The
full serialized forecast remains exactly equal to the previous plan. This is
runtime representation compression, not fewer repair operations or measured
speedup. See `shared-demands-check.json`.

Reproduce the census using `cargo run -p eggfuse-cell-compiler --example
inspect_completion_storage -- PROGRAM OUTPUT`. The output includes both the
full derived Plan (for exact comparison with the expanded v2 forecast) and its
storage census. Existing staged/merge tests check source Run behavior; a
focused test checks shared pointer identity and ownership after cloning/dropping
the plan. The normal runtime's 1,428 sum-bits Runs and final state agree with the
frozen prior execution, and choice_diagnosis reports pass. No performance
campaign was run. The next opportunity is to make the same typed scopes support
actual work elimination, rather than treating shared storage as a repair win.

## Reuse selected RHS scopes within a Run

The matched-rule loop now recognizes consecutive rules referencing the same
interned RHS demand owner. It traverses that scope only once, preserving the
first-occurrence table order and the original per-table deduplication for all
other scopes. The previous-owner handle is stack-local and never survives the
call: no cached readiness or facts cross source Runs. Access readiness, current
repair conflicts, liveness and visibility checks are unchanged.

`rhs_group_checks` counts actual pointer comparisons and is charged by Work;
`rhs_group_reuses` is coverage only and earns no separate credit. On the new
short staged fixture two active rules have the same two-table scope. The old
loop would make four table probes (computed from that exact selected input);
the observed new loop makes two probes plus one pointer comparison. Final graph
and ordered Run fields agree with ordinary completion. The saved evidence is
`shared-scope-check.json`; its old probe count is an explicit model of the old
loop, not a separate binary measurement. No latency or general repair speedup
is established. Unmatched rules remain absent, nonconsecutive duplicates are
not optimized, and varied adjacent scopes pay the additional comparison.

Reproduce using SHARED_SCOPE_EVIDENCE=OUTPUT with the staged_completion test
matched_rules_reuse_the_same_compiled_rhs_scope. The current evidence records
16 passing staged/merge tests. This optimization acts on the actual selected
instances, using exact immutable typed scopes from Bake; training frequency
is not treated as a validity certificate.

## Rejected unconditional nonconsecutive grouping

An isolated follow-up assigned exact RHS scope IDs and maintained a per-call
seen bitset. It preserves first-occurrence demand order and passed all 16
staged/merge tests. However, on the existing short duplicate-scope fixture it
still makes two table probes while increasing group checks from one to two,
adding two word writes and 32 bytes of scratch capacity. Rule group IDs also
add storage. This is not evidence for replacing the cheap consecutive check.
The production implementation remains e3630ee8's algorithm.

`nonconsecutive-scopes.patch` reproduces the rejected implementation on
e3630ee8; apply only in an isolated checkout. Run the staged_completion test
matched_rules_reuse_the_same_compiled_rhs_scope with SHARED_SCOPE_EVIDENCE set
to a fresh JSON path, and compare the checkpoint counters with
shared-scope-check.json. `nonconsecutive-scopes-check.json` records the rejection.
No latency was measured. The fixture does not contain nonconsecutive duplicates,
so it establishes an added cost on already-covered input, not the absence of
benefit on other workloads. Further selection should use actual matched-rule
sequences and scope lengths rather than interpreting increased coverage as
saved work. No new runtime cache remains from this experiment.

## v3: remove redundant per-operation and per-rule fields

The entire v2 handoff, including the repair forecast, can be reconstructed from
v3. Rules reference a template layout holding frame width, definitions and
ordered effects. Operation position is its array index; Entry route is the
existing table ID. Effect kind determines whether the result is an actual
returned receipt, a local value or no result. No node address is inferred from
producer/op coordinates. Worker permission remains globally false; original
rule/match ordering and successful-match/winner establishment are common
constraints, not repeated fields on every rule.

Readers must explicitly accept v3 and reconstruct-validate the sidecar.
Layouts may be shared by rules using the same template, but this sample has
582 distinct layouts for 582 rules: the measured saving is primarily removal
of redundant fields, not template coalescing. No facts, stages, predicted tables
or remaining runtime obligations are discarded. This format is preparation,
not permission to eliminate publication or repair.

`compact-layouts-check.json` records compact UTF-8 size 1,044,950 -> 705,544
bytes (-32.5%), with the repair forecast unchanged. Unlike the earlier v2
addition, the full artifact is now also smaller than v1's 905,056 bytes, while
retaining the added forecast. This measures encoded artifact size, not retained
runtime graph memory, loading latency or execution speed.

Generate v2 on 0a3e6f65 and v3 on this commit using emit_worker_handoff, the same
program and separate Cargo target directories. Run:

```
python3 benchmarks/worker-handoff/check_compact_layouts.py --before V2.json --after V3.json --output CHECK.json
```

The check expands every rule/effect and compares the entire content except the
schema tag and self-checksum, including all 582 rules and the forecast. Compiler
unit/integration checks pass (13 library tests and four state/handoff tests).
The runtime and its input Program are unchanged, so this step does not require
new inference timing or claim a new semantic execution result.

## Predict repair influence using existing Cell union identities

RHS dependency derivation now resolves union operands through the Cell's
existing ordered Copy/constructor alias proof. Equal resolved operands add no
union-induced sort-wide repair scope. The actual union instruction, query,
constructor accesses and ordinary execution checks are untouched. Other unions
retain the previous conservative transitive influence. Opaque literal handling
also remains conservative. No equality solver, runtime equality cache or
future-union assumption is introduced.

The source Run may discharge an otherwise false repair fence only after the
rule actually matches; unmatched RHS obligations still do not activate. A
short `union x x` fixture now leaves unrelated repair pending across that Run
and reaches the same graph and ordered Run fields as ordinary completion.
A duplicate-constructor fixture confirms the Fb access stays live while the
identity union contributes no extra sort-wide scope. Existing nonidentity-union,
mutable merge, late input and publication tests still pass (18 total).

See `noop-union-check.json`. Reproduce with NOOP_UNION_EVIDENCE=OUTPUT and the
staged_completion test
identical_union_operands_do_not_predict_an_unrelated_repair_fence, plus
constructor_alias_union_keeps_constructor_access_but_not_sort_wide_fence.
The frozen sum-bits full forecast is exactly unchanged versus the saved prior
plan: it offers no extra scope-reduction opportunity here. No speedup, additional
sum-bits repair saving or broad runtime compression is claimed. This extends
what typed Cell facts can prove, without treating occurrence counts as proof.

## Reuse executable constructor-elision proofs in forecasts

RHS scope derivation now consults the same validated static_skip mask as the
ordinary Cell executor. Only constructor Let operations already skipped by that
executor stop contributing new RHS demands. Mandatory query reads remain; an
actual earlier constructor operation still contributes its access. Set, mutable
reads, Hide and non-elided operations retain their previous requirements. The
existing global deletion restrictions on alias proofs remain authoritative.

Against d9ae41af, the frozen sum-bits catalog changes 63 rules, removing 72 RHS
and 73 direct-access table memberships (overlapping categories, not additive
saved work). The shared demand payload plus estimated Rc headers decreases
82,112 -> 64,160 bytes; handles remain 27,936 bytes. These are stored prediction
structures, not whole-process memory. `alias-demand-check.json` records exact
subset checks, unchanged query demands and the before/after source hashes.

The scoped release comparison uses an isolated control built from current
sources with completion_access.rs restored to d9ae41af, and the candidate built
with the new proof use. Both use sparse-cells,view-ports,storage-metrics. Their
1,428 Run signatures/final state match and choice_diagnosis passes. Scoped work
counters are identical: this workload's pending windows do not exercise the
newly removed demands. Thirty staged/merge/witness tests pass, including a new
matched-constructor test with/without an active deletion rule. No runtime repair
reduction is claimed for sum-bits.

At the user's explicit timing request, `time_alias_scopes.py` ran one warmup and
seven interleaved pairs per mode, without compilation during measurement.
`alias-scope-timing.json` saves every sample and binary/program hashes. Normal
inference medians are 26.117/26.074 ms; scoped inference 31.739/31.433 ms.
Normal process medians are 145.816/143.055 ms; scoped 173.849/182.791 ms. Paired
candidate/control inference ratios are 1.0048 [0.9956,1.0116] and 0.9982
[0.9142,1.0154]; paired process ratios 1.0038 [0.9798,1.0115] and 1.0118
[0.9947,1.0464]. No stable speedup is established. The unpaired scoped process
median increases 5.1%, while the paired estimate increases 1.2% with uncertainty
crossing parity. One short workload cannot establish a general regression bound.

Reproduce using the script's --baseline, --candidate, --program, --root (fresh
directory) and --output arguments. Both binaries must be frozen ordinary
release builds; artifacts under out/ are not tracked. This experiment measures
the standalone Cell CPU, not native egglog speed.

## Shared immutable influence/wait matrices

After the existing mutable transitive closure and merge-birth/read dependency
construction finishes, exact equal u64 rows are interned across both matrices.
Runtime row lookup still indexes the same bit positions; scope selection and
repair ordering are unchanged. The interning registry is compile-local and is
not retained. Boxed row directories avoid retaining the larger Vec<Vec<u64>>
allocation capacity when converting to smaller shared handles. This is not a
new relationship graph or an approximation of repair influence.

For the frozen sum-bits catalog, 802 rows have 249 distinct contents. Logical
retained storage (payload, row directory, estimated Rc headers) decreases from
64,160 to 30,760 bytes (-52.1%). The old directory model is 24 bytes per Vec on
this 64-bit host, and rows were allocated at the exact dense width. The new
directory occupies 12,832 bytes and shared payload/Rc headers 17,928 bytes.
Outer container headers, allocator rounding, temporary closure construction and
interning storage are excluded. No latency/peak RSS saving is claimed.

`shared-matrices-check.json` records the census and exact closure signature.
The diagnostic helper now hashes every affects(a,b) result and every singleton
scope, in addition to the full serialized Plan. All are equal before/after.
To reproduce the baseline signature on 83e1b566, use the new
inspect_completion_storage helper with only its `matrices` report field removed
(the old Plan lacks that census method). Use separate checkouts/target dirs.
The new helper reports the shared storage directly. Existing scoped correctness
checks pass: 31 staged/merge/scoped tests plus a row-sharing test covering high
bits, cross-matrix sharing, unequal rows and owner lifetime. Runtime algorithms
and forecast results are unchanged; the already accepted semantic exports
remain the development reference, not a newly claimed execution measurement.

The previous catalog's actual executions still select which work is useful;
this change compresses the exact type-derived closure they consume. It does not
claim that a scheduled cross-Run switch can discharge more work merely because
its masks share memory. All previously live matching, Eq, deletion, visibility
and publication obligations remain live.

## Build prediction masks directly and reuse closure scratch

Prediction construction no longer builds an n-by-n Vec<bool> matrix and scans
it again to produce u64 rows. It sets the same bits directly. Opaque/full rows
explicitly clear padding bits because global-effect classification counts bits;
boundary tests cover 0/1/63/64/65/127/128/129/401 tables.

Merge-birth influence still reads the pre-birth closed row. A single reusable
snapshot replaces cloning the entire task-effect matrix, so births cannot
spuriously activate another merge in the same pass. Both transitive-closure
passes likewise reuse one pivot buffer each instead of cloning every pivot.
The ordering and scope of all proof computations remain unchanged.

On the 401-table frozen catalog, the removed intermediate boolean payload is
160,801 bytes. The birth-snapshot payload changes 22,456 -> 56 bytes. Two closure
passes plus the birth pass use three explicit row buffers rather than 1,203.
These are source-level temporary representations, not instrumented allocator
calls or measured peak RSS; the boolean matrix and birth snapshot occur in
different phases and their sizes must not be added as a peak-memory claim.
Retained prediction storage is unchanged.

`direct-mask-check.json` compares against c8b099fd. Running the same
inspect_completion_storage example on both versions yields identical complete
diagnostic JSON, including all serialized facts, every influence pair and every
singleton waiting scope. Thirty-one staged/merge/scoped tests and two boundary/
sharing tests pass. No new inference timing was run. Existing accepted semantic
exports remain the reference because the executor and every generated
prediction are unchanged. This change removes redundant work needed to build
predictions; it does not claim broader repair coverage or new Run takeover.

## Closure compression timing (83e1b566 -> b840448c)

`closure-compression-timing.json` measures the standalone Cell CPU runtime,
not native egglog, on the frozen sum-bits program. Both release binaries use
sparse-cells, view-ports and storage-metrics, with CELL_CPU_HASH_BITS=64.
`time_alias_scopes.py` ran one warmup and seven alternating paired repetitions
per mode. Every sample agrees on the exact final-state hash and 1,428 ordered
Run signatures. This is a before/after regression check, not a fresh native
semantic proof. Binary hashes and individual samples are saved in the JSON.

Median milliseconds (baseline -> candidate):

| Mode | Setup | Inference | Process wall |
| --- | ---: | ---: | ---: |
| normal | 3.413 -> 3.352 | 27.285 -> 27.942 | 149.316 -> 151.282 |
| scoped | 28.118 -> 29.359 | 31.637 -> 33.599 | 174.110 -> 182.859 |

Paired median candidate/baseline ratios for scoped setup, inference and wall
are 1.0315, 1.0337 and 1.0285. Their paired bootstrap 95% intervals are
[1.0155, 1.0498], [1.0033, 1.0992] and [1.0066, 1.0474], respectively.
Normal-mode intervals include 1. These samples show no speed benefit and a
small scoped-mode regression; they do not isolate which of the two commits
causes it. Ratios of medians differ from medians of paired ratios.

Call-site inspection: scoped_completion::use_scoped_completion derives the
Plan once when enabling this optional mode, inside main's setup timer. Normal
local-congruence mode does not build it. Offline worker-handoff compilation
also derives the Plan. Direct mask construction and scratch reuse optimize
this preparation, not a per-RHS or per-repair loop. Runtime scope selection
and influence checks read the retained matrices; sharing changes their storage
but removes no logical check. No profile establishes those reads as a hotspot.

The retained-matrix reduction (64,160 -> 30,760 logical bytes) remains valid,
but must be reported with this time cost, not as RHS publication acceleration.
Further speed work should target measured repeated Entry/publication work;
this measurement does not justify more prediction-builder micro-optimization.

## Use executed-operation proofs to compress RHS receipt frames

The next repeated-work target is the actual Cell effect frame, rather than
one-time forecast construction. The last catalog's normal sum-bits execution
initializes 12,028 receipt slots. EffectPlan still allocated raw slots for
constructor aliases that every execution path already skips, including closed
completion, prefix execution and first-miss resume. Such raw results are always
absent. The older comment that closed completion could record them was stale.

EffectPlan now uses the executor's validated static_skip proof to omit these
transient slots, including full structural capture and history-only demands.
There is no runtime filter or new instance metadata. Original effect donors
remain allocated; a retained query-alias output still reserves its final prefix
slot and fills it only after history observes the raw absence. An omitted raw
slot returns None as before. The operation-to-slot descriptor array stays the
same size. This does not change RHS instructions, published output positions,
Run order, receipt resolution, visibility checks or cross-stage history facts.

Normal sum-bits before/after b840448c/39512f71 kernel:

- Receipt slot initializations: 12,028 -> 10,790, removing 1,238 (10.3%).
- All other normalized work fields are unchanged, including publication work.
- Exact final state and all 1,428 ordered Run signatures agree.
- Required native choice diagnosis: pass, bound to the candidate state hash.
- Entry publication, closed-alias and state-inheritance suites: 16 tests pass
  both in the ordinary feature set and with structural-depth enabled. The
  existing effect-donor regression additionally requires one initialized slot
  per one-source frame; the skipped duplicate must not allocate an empty slot.

This is an actual execution-frame reduction, not broader takeover of internal
cross-stage publication. Source aliases provide the typed proof; the scheduled
switch must still preserve actual witness, inherited absence and boundary
publication. No allocation-count, peak-RSS or speed benefit is inferred from
these initialization counts. This is the first implementation since the last
requested timing checkpoint; no timing campaign was run.

Saved result: `../cell-unification/elided-receipt-slots-check.json`.
Reproduce normal runs with the same release features as the timing section,
using baseline and candidate binaries and fresh `baseline`/`candidate`
subdirectories under a pre-created root. Run the required choice diagnosis on
saved native references and the candidate export, then check them with:

```sh
python3 benchmarks/cell-unification/check_elided_receipts.py \
  --root out/elided-receipt-slots \
  --program out/cell-slot-inheritance/compact-final/program.json \
  --baseline /private/tmp/closure-current-runtime \
  --candidate /private/tmp/eggfuse-state-target/release/eggfuse-cell-runtime \
  --output benchmarks/cell-unification/elided-receipt-slots-check.json
```

## Read the compiled receipt donor directly

The previous normal catalog execution had 1,604 successful query-alias forwards
and 294 effect-alias forwards, versus 1,313 history capture reads and 195 already
inherited slots. Before publication, every alias first probed its skipped raw
operation and only then read the compiler-known source. The raw result is absent
by the same execution proof used for receipt-frame compression.

Cell Output now selects the existing query/effect source before reading it.
Ordinary outputs still read their own actual receipt. A missing donor returns
None and keeps the existing publication fallback; source identity is neither a
visibility certificate nor permission to replace a returned receipt with a
producer/op address. No cache, runtime index, consumer list or extra instance
state is introduced. Source Run publication order and history capture remain
unchanged. This does not discharge another cross-Run publication boundary.

On the same sum-bits program, before/after 4d8caa0d, all normalized work counters,
1,428 ordered Run signatures and the final graph are identical. The required
choice diagnosis passes. At least 1,898 redundant raw-slot probes disappear:
this lower bound follows from the successful forwarding counters and the old
and new code paths, not a new probe counter. Missing donors can save further
probes but are excluded from the bound. No latency or publication-work reduction
is claimed. This is implementation two since the last timing checkpoint.

The 16 entry-publication, closed-alias and state-inheritance tests pass with
iterative-bake, sparse-cells, view-ports and structural-depth. A runtime unit
check verifies donor-only access including missing donors (no raw-alias read),
query donors (no effect read), and ordinary output receipts. Existing tests
retain deletion, union, aborted RHS, cross-stage inheritance and winner-order
coverage. Saved evidence is `../cell-unification/direct-receipt-donors-check.json`.
Use `check_elided_receipts.py --mode donors` with the fresh baseline/candidate
exports and the required semantic acceptance JSON to reproduce the work check.

## Rejected query-witness projection experiment

The existing QueryFacts demand selected three specialized query collectors:
no intermediate witness list for None, one inline witness for One, and the old
list for All/Ports/Tracked. Source queries, guards, epochs, required final facts
and publication stayed unchanged. The candidate patch and metering-only control
patch are saved in `../cell-unification/`; neither is installed in the kernel.
Both patches apply to 07c62ee5 individually (do not apply them on top of each
other). The control adds three counters to the original collector. The timing
baseline is unmodified 07c62ee5, built with the same release feature set.

Sum-bits intermediate witness writes fell 2,178 -> 131, but the new path added
487 single-atom comparisons and 870 demand dispatches. Charging all three yields
690 fewer equal-weight operations. `check_witness_projection.py` verifies the
metered control against the saved unmodified execution and checks that all other
normalized work is unchanged. Exact final state, all 1,428 Run signatures and
native choice diagnosis agree. Eleven Entry publication tests, seven query
receipt tests, eleven witness-source tests, three closed-alias tests and four
credit tests passed, including empty/single demand and added-cost charging.

The user requested a speed gate before further work. One warmup and seven
alternating pairs per mode, using `time_alias_scopes.py`, produced:

| Mode | Inference median ms (old -> trial) | Wall median ms (old -> trial) |
| --- | ---: | ---: |
| normal | 25.521 -> 26.017 | 139.586 -> 142.702 |
| scoped | 31.598 -> 31.230 | 173.496 -> 174.240 |

Paired inference ratios were 1.0153 [0.9847, 1.0343] and 1.0027
[0.9020, 1.0277], respectively (95% bootstrap intervals). Neither establishes a
speed benefit; wall-time intervals also cross 1. The small work-count saving
is insufficient evidence of acceleration. Runtime and credit changes were
withdrawn, retaining only reproducible patches and text evidence. No Raytrace
campaign was run. The user then directed further work toward storage compression
and deferred hotspot investigation until the parallel branch returns instances
directly. `query-witness-projection-timing.json` contains individual samples and
binary hashes; `query-witness-projection-check.json` contains work/semantic checks.

## Pack shared effect-slot descriptors without another index

Following the user's direction to defer hotspot work until the parallel branch
returns instances directly, compression continues in the existing shared Cell
layout. EffectPlan previously stored an optional descriptor containing a u32
slot and an optional u8 history position. On this target each entry occupied
8 bytes. A packed descriptor stores the same optional full-range NonZeroU32
and one byte encoding absent history as 0 and positions 0..63 as 1..64.
Each entry is now 5 bytes. No slot-range restriction, side index, per-instance
metadata, layout-owner header or runtime relationship maintenance is added.
Packed fields are copied by value; Rust rejects unaligned references, and no
unsafe block is used. The tradeoff is potentially unaligned descriptor loads,
not a claimed execution speed improvement.

The actual lazily retained sum-bits descriptors decrease from 6,376 to 3,985
bytes (797 entries, saving 2,391 bytes / 37.5%). This is only descriptor-array
capacity, excluding allocator rounding; it is not a 37.5% reduction of total
runtime storage. Shared Plan headers, publication storage, instance result
frames, logical work and inheritance coverage are unchanged. Previous catalog
executions identify these retained layouts. Scheduled cross-Run inheritance
keeps its original slot mapping and provenance checks; packing proves no new
work redundant and receives no extra Bake operation credit.

Seventeen tests pass: a packed-descriptor test preserves absent slots, the full
u32 index, both ends of the 64-bit inheritance mask and an existing arena prefix;
plus the sixteen Entry publication, closed-alias and state-inheritance tests
with full structural capture compiled in. Exact sum-bits final state, all 1,428
ordered Run signatures and every normalized work field agree. Required native
choice diagnosis passes. No additional speed campaign was run.

`../cell-unification/packed-effect-slots-check.json` records the retained census
and binary hashes. Reproduce with saved baseline/candidate exports using
`check_elided_receipts.py --mode packed`, the same program/binary arguments as
previous checks, and `out/packed-effect-slots` as root. The checker accepts only
the descriptor-byte change, checks the exact 8-to-5 ratio and requires semantic
acceptance bound to the candidate state.
