# Restoration boundaries for cross-stage composition

Scope: the standalone Cell CPU in this worktree, not native egglog. This change
observes the opt-in completed-owner store; it removes no logical fact, query,
publication or allocation. The ordinary parallel lane does not enable this store.

The previous installed-catalog audit (README.md) found 821 fully witnessed RHS
applications. A stage switch could reuse their actual results under the compiled
Entry and effect-order proofs. That opportunity does not prove it safe to merge
all source storage into a single restoration unit. Mutable reads, new union-enabled
matches, residual enumeration, visibility and external readers remain live.

## Amplification boundaries

- Owned union dispatch traverses activated static signal uses and key candidates;
  stable Eq fields do not need canonical-ID rewriting.
- Last scalar provider retirement invokes `preserve_completed_scalars`, which
  can unseal an entire source frame to recover a small number of bindings.
- Last component fact retirement scans component signals and source frames,
  restoring symbolic slots still required by external readers.
- `extend_completed` copies the old owner prefix plus the new suffix. Repeated
  growth can accumulate quadratic movement independently of union.

Template composition should retain independently restorable source slices. Do not
turn a shared template DAG into an indivisible recursively expanded storage tree.
A useful Bake score must charge retained boundary interfaces, restoration size and
old-prefix movement as well as removed duplicate slots and publication work.

## Added observation

`completed_profile().restoration` reports events, reconstructed slots and facts,
summed container capacity bytes, and the largest single event with its template.
It records successful `unseal_completed` calls only. Missing/already-unsealed
frames do not increment counters; deleted facts are not reconstructed. The maximum
is container capacity, not a bound on all memory caused by a union.

Excluded: later scalar insertion, source arena growth, retained old owner arrays,
component teardown scans, temporary query rows and allocator overhead. No event
is attributed to union merely because it occurred during execution. All callers
are aggregated; this report alone does not identify a triggering union or cause.
Counters occupy fixed per-store state and do not add per-instance history or an
index. This observation does not change stage admission or publication order.

## Validation

The existing multi-stage owner test now checks one-source restoration, unaffected
siblings, exact container-capacity accounting, missing-source non-events and a
second restoration after its fact was deleted. Five fact-state tests pass with
`sparse-cells,storage-metrics`; the full runtime library suite also passes all
200 tests under those features. No timing or compression benefit is claimed.

Reproduce:

```sh
CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,storage-metrics --lib fact_states
```

The next comparison must replay identical installed catalogs and report both
storage savings and restoration/extension work. Previously saved measurements
from another branch are not measurements of this worktree.

## Current-branch batch evidence

Measured with runtime source at `09fe0691` plus the existing, unrelated query
completion working-tree edits (neighbor/query/query snapshot/worker/runtime).
Those edits were present before this audit and are not included in its commit.
Inputs are the four frozen `out/cell-bake-owner-merge/batch/*/candidate.json`
files; file hashes and full Graph teardown attribution are in
`restoration-results.json`. No source/catalog retraining occurred.

| case | Graph owned bytes | restoration events | restored container capacity | maximum event | old slots moved | old facts moved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 779,975 | 0 | 0 | 0 | 154 | 186 |
| loopfact | 678,385 | 0 | 0 | 0 | 110 | 159 |
| sum-bits | 2,054,923 | 6 | 1,968 | 360 | 688 | 943 |
| dot-product | 2,030,643 | 0 | 0 | 0 | 2,087 | 1,265 |

All four final graph digests match the saved catalog executions, over respectively
418, 398, 882 and 954 Runs. This run checked final hashes and Run counts, not each
intermediate Run or native egglog semantic equivalence. Restoration is aggregate
across causes. These results supersede neither other-branch results nor worst-case
bounds for future large indivisible frames.

Stable ports, components, boundary routing and frame directories together occupy
41.7%, 37.1%, 46.2% and 44.9% of Graph heap. These are storage categories, not all
redundant bytes. Cell storage occupies another roughly 26%–28%. This supports
prioritizing duplicate instance/address representation while retaining small
restoration boundaries; it does not support building a new fallback mechanism
merely to eliminate the currently observed 1,968 bytes of restored containers.
The ordinary barrier history alone retains 98,304 bytes in each of sum-bits and
dot-product. The structural branch already has an explicit-observation version
(`a3269a73`); its integration must preserve opt-in trace consumers.

Do not skip scalar preservation solely because `parent_users == 0`. Already
matched but not yet executed same-Run bindings can still read old source recipes;
`release_empty` explicitly keeps ancestors until the Run boundary. A future
skip requires an admission/visibility proof covering these pending readers.

Reproduce the memory runs (one process per case, no latency comparison):

```sh
CARGO_INCREMENTAL=0 cargo build --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_peak
mkdir -p out/cell-restoration-boundaries
for case in fact loopfact sum-bits dot-product; do
  target/debug/examples/runtime_storage_peak out/cell-bake-owner-merge/batch/$case/candidate.json out/cell-restoration-boundaries/$case.json inherited-owners --port-domains-only
done
python3 benchmarks/cell-bake-owner-merge/restoration_results.py out/cell-restoration-boundaries out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/restoration-results.json
```

## Explicit barrier history integration

Adapted the structural branch change `a3269a73`: ordinary execution now retains
only cumulative ownership counters. Explicit barrier tracing, catalog observation,
fragment training and Executor audit retain boundary records. A late explicit
request records its missing prefix; repeated requests do not reset that prefix.
This avoids allocating history proportional to source Run count in production.

48 ownership integration tests pass, including equal exported state for ordinary,
audited, catalog-traced and late-traced execution. Four frozen memory replays
match all prior `completion_work` and `source_storage` fields exactly, including
restoration counters, plus final hashes and Run counts. The sole changed Graph
teardown field is `ownership.barriers`:

| case | Graph before | Graph after | released bytes | fraction |
| --- | ---: | ---: | ---: | ---: |
| fact | 779,975 | 755,399 | 24,576 | 3.15% |
| loopfact | 678,385 | 653,809 | 24,576 | 3.62% |
| sum-bits | 2,054,923 | 1,956,619 | 98,304 | 4.78% |
| dot-product | 2,030,643 | 1,932,339 | 98,304 | 4.84% |

This is observation-state removal, not fewer logical facts, a RHS takeover or a
speedup. Pending same-Run reads and small source restoration boundaries remain.
The next structural target remains duplicate stable/instance representation.

Rebuild and repeat the preceding memory commands into `out/cell-explicit-barriers`,
then compare with:

```sh
python3 benchmarks/cell-bake-owner-merge/barrier_results.py out/cell-restoration-boundaries out/cell-explicit-barriers benchmarks/cell-bake-owner-merge/barrier-results.json
```

## Stable-node projection scope

An offline join of the same saved live fact lifecycles with component frame
ordinals and shared shape programs covers every stable node exactly. No new
runtime census state or rerun was needed. `template_projection_census.py` rejects
missing source frames, duplicate directories, absent layouts and mismatched
stable-node totals.

| case | stable nodes | no dynamic scalar fields | scalar-bearing nodes |
| --- | ---: | ---: | ---: |
| fact | 948 | 653 | 295 |
| loopfact | 892 | 633 | 259 |
| sum-bits | 2,895 | 1,825 | 1,070 |
| dot-product | 2,825 | 2,023 | 802 |

These scalar-free records are candidates for complete removal from the stable
node map, deriving their field descriptors from the existing authoritative
FactState, frame ordinal and shared template. This is 63%–72% of record counts,
not 63%–72% of Graph bytes. Scalar payloads, fact liveness, equality state and
boundary indexes remain necessary. No records have been removed by this census.

Current `Fields` retains two Arc handles per node (program and ports), component,
operation and a scalar slice; `Stored` also retains table. Program and port wiring
are already shared; eliminating those handles is distinct from deleting shared
wiring. The structural worktree's template projection implementation is relevant
prior work, not yet proof of integration into this parallel branch.

The hard integration obligation is `port_guard::Snapshot`: its nodes and
components represent an immutable read epoch while the coordinator can retire
facts. A projected lookup must use matching frozen membership and wiring, not
live Cells. Preserve source-frame restoration slices, actual constructor results,
coordinator liveness checks and panic cleanup. Charge any new snapshot membership
records and lookup work against the removed stable records; cloning the full
instance graph would invalidate the intended savings.

Reproduce without executing the workload again:

```sh
python3 benchmarks/cell-bake-owner-merge/template_projection_census.py out/cell-explicit-barriers benchmarks/cell-bake-owner-merge/template-projection-census.json
```

## Projection implementation integration

Adapted the runtime portion of structural commit `8ca2cc62` to this branch.
`use_template_stable_fields()` removes scalar-free stable-node records at a
settled boundary and omits their later insertions. FactState remains the liveness
authority. Scalar-bearing records keep their actual values. Shared program/shape
wiring replaces per-node Arc handles; field reads resolve existing frame ordinals.
No parallel binding graph or per-producer consumer list was added.

Ordinary borrowed worker guards support projection. Overlapped completion batches
currently reject this opt-in mode in either configuration order: the candidate
membership snapshot still needs integration. The default materialized path keeps
its epoch snapshot and now shares program/shape directories. This is an explicit
incomplete integration boundary, not completion of the parallel compression goal.

49 ownership, 11 completion-batch, 5 parallel-guard and 2 read-guard tests pass.
The new projection test compares every Run through union, deletion and later
stages with zero/two query workers, and asserts actual record removal. Build:

```sh
CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --test cell_ownership --test completion_batches --test parallel_guards --test read_guards
```

These tests establish the covered execution behavior; fresh full-workload memory
and per-Run comparisons remain required before claiming a branch-level reduction.
The previously measured structural-branch savings are not reused as this branch's
results. This removes duplicate stable metadata, not logical egraph facts.

## Paired projection memory results

Fresh same-binary executions compare materialized and projected modes after
`48152cc2` (with the parallel branch's integrated domain completion). Both modes
already use shared layout descriptors. Thus these deltas isolate removal of
scalar-free stable records, not the earlier Arc-handle/layout change.

| case | materialized Graph | projected Graph | saved | fraction |
| --- | ---: | ---: | ---: | ---: |
| fact | 722,671 | 647,407 | 75,264 | 10.41% |
| loopfact | 637,465 | 612,377 | 25,088 | 3.94% |
| sum-bits | 1,891,123 | 1,790,771 | 100,352 | 5.31% |
| dot-product | 1,866,843 | 1,716,315 | 150,528 | 8.06% |

Every completion-work and source-storage field (including lifecycle and restoration)
is equal within each pair, as are final hashes and Run counts. Only stable_ports
changes in field-by-field Graph teardown. Records removed are 653/633/1825/2023.
Projection executes 87,871/79,294/450,205/681,454 times respectively; these are
real extra descriptor-reconstruction paths, not free reads. Layout-read counters
are also recorded. No speedup is inferred from memory savings.

Reproduce with the same memory command in both modes, adding `--template-fields`
only for projected output, into `out/cell-template-paired/CASE-MODE.json` where MODE
is materialized/projected. Build examples with
`iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit`.

```sh
python3 benchmarks/cell-bake-owner-merge/projection_results.py out/cell-template-paired benchmarks/cell-bake-owner-merge/projection-results.json
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch owned-state template-fields
```

The second command checks saved per-Run graph, ordered RHS and physical-write
digests plus terminal non-Run effects on the installed owned-state variant. It
is a standalone-runtime differential check, not a new native egglog acceptance
contract. Large logical-fact compression, overlap-mode support and stage-switch
RHS takeover remain incomplete.

Validation completed: all 2,652 saved Run checks and all four terminal checks pass;
compact evidence is saved in `projection-run-checks.json`.

## Projected candidates in overlapped completion

The earlier explicit rejection is now removed. Adapted the candidate-snapshot
implementation from the structural worktree: prepared completion tasks supply
their exact candidate read set. Only live scalar-free candidates receive a frozen
record containing FactRef, table, component and frame ordinal. Records are deduped
before insertion into a sorted vector; scalar payloads, equality, component wiring
and queues continue using their existing epoch snapshots. No full Cell clone,
per-producer consumer list or persistent membership index is introduced.

Frozen reads resolve membership exclusively through that batch's records. Later
coordinator retirement cannot make a worker accidentally consult live Cell state.
The existing coordinator validation remains authoritative at publication. Batch
records are released after all readers join, including panic cleanup. Scalar-free
births explicitly obey the frozen-node admission guard that was previously
implicitly enforced by map insertion.

New overlap counters charge candidate visits, unique records, binary-search
comparisons, insertion shifts, total batch capacity and maximum batch capacity.
The vector is bounded by distinct projected candidates, but insertion shifts can
still be quadratic in that distinct count. This is a measured-cost obligation,
not a claim that snapshots are free or that overlap becomes faster.

71 integration tests pass (49 ownership, 15 completion batches, 5 parallel guards,
2 read guards), including a scalar-free fixture that forces an effective union
while a reader is held, component retirement, panic after coordinator commit and
first-reader panic. All modes recover to the serial export and an empty completion
queue. The test checks nonzero projected snapshot records so an all-scalar fixture
cannot accidentally establish coverage. Default runtime also compiles.

```sh
CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit,completion-overlap-probes --test cell_ownership --test completion_batches --test parallel_guards --test read_guards
```

The previously reported four-case memory savings remain single-lane results.
End-to-end overlap memory/preparation cost and stage-switch RHS savings remain
unproven. This integration removes a compatibility blocker; it does not complete
the large-compression objective.

## Whole-workload overlap replay

`check-passive ... template-overlap` enables two guard workers (threshold 1),
batches of at most 16 tasks, template projection and overlapped completion on the
same installed owned-state catalogs. All 2,652 saved Run graph/RHS/write checks
and four terminal checks pass. Each workload actually executes projected snapshots:

| case | overlap epochs | candidate visits | projected records, summed over batches | snapshot peak capacity | insertion shifts |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 7 | 110 | 66 | 1,024 | 117 |
| loopfact | 8 | 60 | 35 | 512 | 35 |
| sum-bits | 83 | 2,641 | 1,132 | 8,192 | 13,709 |
| dot-product | 38 | 706 | 371 | 4,096 | 949 |

Records are deduplicated within a batch, not globally. Peak capacity is only the
added projected membership vector, not all completion memory or process peak.
Existing input/result buffers and overlay writes remain; complete counters are
retained in `overlap-projection-results.json`. For example sum-bits also requests
258,512 result-buffer bytes over the run. Comparing its 8 KiB snapshot peak to the
single-lane final-heap saving is not an end-to-end peak or net-memory measurement.
No latency benefit is claimed. The insertion-shift count makes preparation cost
visible rather than treating template-derived descriptors as free.

Reproduce after building the batch example with the previously listed features:

```sh
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch owned-state template-overlap
python3 benchmarks/cell-bake-owner-merge/overlap_projection_results.py out/cell-bake-owner-merge/batch/owned-state/checked.json benchmarks/cell-bake-owner-merge/overlap-projection-results.json
```

This closes the projected-overlap workload coverage gap. It does not reduce RHS
logical work or establish the requested large compression target; static reuse of
completed facts and stage transitions remain the structural next step.

## Preserve constructor witness positions for Bake

The old saturation observer discarded the location of constructors it found. Its
aggregate `(rule, shape, covered)` outcome could rank opportunities but could not
compile a result address. The explicit catalog trace now additionally aggregates
fully covered constructor paths by `(rule, shape, positions)`. Each position is
`(RHS operation, source frame ordinal within shape, source operation)`.
No instance ID enters that key. Only the selected fully covering component is
credited; partial matches and input-only union coverage create no constructor
path. Positions identify observed source facts, not synthetic result addresses:
execution must read the source fact's actual result, including foreign reuse.

This is trace evidence, not an executable certificate. Bake must prove operand
correspondence, visibility, mutable-read freshness and source-stage ordering before
replacing queries/publications. Multiple observed paths for a rule/shape remain
separate, so the trace does not silently select an arbitrary canonical path.
Existing copies/static aliases still receive no new saved-operation credit.

The observer remains gated by explicit catalog tracing; production does not
collect these paths. Two saturation tests pass, preserving exports, snapshots and
binding audits, checking relative source positions and rejecting partial/input-only
paths. No runtime effect is skipped by this change. The next compilation step can
now consume actual source positions instead of repeating a whole-component scan.

## Installed-catalog witness-path replay

The batch checker accepts `witness-trace` to observe the installed candidate while
checking the saved per-Run graph, RHS and write digests. It records the full catalog
trace alongside existing completion diagnostics; production execution is unchanged.
`witness_path_results.py` joins paths to the exact candidate artifact and ranks
observed constructor positions by applications. It also counts rule/shape groups
with several paths, so selection ambiguity is visible rather than hidden by an
arbitrary route choice. Counts include positions already handled by static aliases;
they must not be interpreted as additional removable operations.

The existing `complete_handoff` is the intended execution outlet: it validates a
live actual receipt against current arguments and assigns its actual result. A
shape-relative path can supply a candidate receipt, but cannot bypass that check
without a compiler proof of operand correspondence. Shape programs share layouts
across operators; rule tables and source code/operator compatibility must also be
proved. Current trace lacks a compiled mapping from consumer query anchors to the
selected component; reconstructing that by scanning components would defeat the
intended takeover. This is the next missing compilation obligation.

```sh
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch owned-state witness-trace
python3 benchmarks/cell-bake-owner-merge/witness_path_results.py out/cell-bake-owner-merge/batch/owned-state benchmarks/cell-bake-owner-merge/witness-path-results.json
```

The first witness replay completed all four Run and terminal checks, then failed
writing checked.json with OS error 28 (StorageFull). That artifact is incomplete;
no ranked-path results or successful end-to-end replay are claimed. Two completed
local test executables were removed to reclaim build space; source files, saved
traces and benchmark evidence were retained. A fresh replay/output validation is
still required before using the new witness-path data for compilation.

## Query anchors and durable observation output

Witness paths now include query positions `(query atom, source frame ordinal,
source operation)` in the same component. They are part of the aggregation key;
no runtime instance IDs are pooled. These anchors identify how an existing query
receipt can locate the component before selecting a constructor candidate.

Witness mode saves only saturation evidence, atomically checkpoints each case to
`CASE/witness-checked.json`, and writes the aggregate to `witness-checked.json`.
Ordinary `checked.json` is no longer overwritten by this mode. The two observer
regression tests pass, including relative query-anchor coordinates.

A concrete ambiguity is already present in the sum-bits trace: rule 90,
`BodyContainsExpr(body, Get(tup, i)) -> BodyContainsExpr(body, tup)`, shape 654,
query anchor `(1,2,0)`, has witnessed targets `(0,0,0)` and `(0,1,0)`, each observed
10 times. Thus even the same rule/shape/query-position tuple cannot select one
fixed target. Different matched bindings can require different witnesses. Bake
must retain a small typed candidate set and prove or check the remaining argument
correspondence; it must not choose a target solely by historical frequency.

Fresh replay completed successfully: 2,652 Run checks and all terminal checks
pass, with a 711 KiB aggregate. Fact/loopfact/sum-bits/dot-product produced
29/24/90/79 observed anchored paths, covering 57/30/179/165 applications.
Their rule/shape groups include 5/5/20/16 groups with multiple paths (which may
also have different query anchors). Full ranked evidence is saved in
`witness-path-results.json`. Weighted constructor-position counts are
75/39/217/207, including already static aliases; these are not saved operations.

## Typed bounded candidate compilation

`compile_ownership_witness_candidates` binds observations to the exact source
program digest and produces deduplicated candidate addresses grouped by rule,
shape and query anchor. It checks source/anchor frame layout widths and that their
shared layout admits the required operator. Shared-layout operator compatibility
is not an instance operator proof: the latter remains a runtime check.

Initial coverage is only operation-zero constructors whose operands are query
inputs or literals. Already static-skipped operations are excluded. Other
positions and noninstalled shapes remain unsupported, rather than causing a
runtime scan. No plan is installed into execution yet; this commit does not claim
query elimination, publication savings or a saturation certificate.

Two saturation regression tests pass, including wrong-source rejection. Compiling
saved actual traces without re-execution produces 19/17/44/28 candidate addresses
for fact/loopfact/sum-bits/dot-product. Plans remain reproducible generated output.

```sh
target/debug/examples/batch_cell_learning compile-witness out/cell-bake-owner-merge/batch/owned-state
```

Entries encode `(rule,shape,query_atom,anchor_frame,anchor_operation,
RHS_operation,target_frame,target_operation,table)`. The execution integration
must consume these through existing constructor preparation/handoff and check
current arguments, fact visibility/incarnation and stage ordering. A candidate
miss cannot justify suppressing ordinary residual matching or future union matches.

## Reconcile with the merged execution route

During the execution experiment, current HEAD acquired the structural witness
route implementation (`db61fbe4`, reconciled by `d4b9fa2d`). It already loads
`ownership_witnesses` into the shared compiler plan, requests query Entries,
selects shape-relative witnesses, proves keys from shared ports/copies when
possible, and otherwise retains exact-key validation.

A separate experimental entry directory hit its sibling-constructor test but
failed the useful-work gate: both control and candidate performed 3 port-key
lookups. Final exports, snapshots and binding audits matched. Its new lookup
attempt therefore did not establish removed work. The entire uncommitted duplicate
runtime directory, execution hook and experimental test were removed. This is
negative experiment evidence, not an optimization or speedup.

The existing `ownership_witnesses::Routes::compile` currently uses `or_insert`
for a single Target per `(shape, source ordinal, source code, source operation)`.
The observed multi-target traces require revisiting this selection. Exact-key
fallback preserves semantics when the first target is wrong, but cannot exploit
another witnessed target from the same entry. The next change should extend this
existing route representation and its validation, not add another per-Graph
candidate catalog. It must distinguish identical targets from genuinely different
alternatives, charge key comparisons, and demonstrate fewer generic lookups when
only a later alternative matches. Key-proved and dynamic-key routes must retain
liveness, operator/code and original effect-order checks.

## Multiple witnesses in the existing route

The shared `ownership_witnesses` route now retains deduplicated targets per
entry key using an inline single-element list. Single-target execution keeps its
previous path. With alternatives, execution visits only the compiled targets,
rejects missing/hidden/wrong-code targets and compares the current constructor
arguments before selecting one. It then uses the existing proven-key or exact-key
publication path. No second runtime catalog or per-instance binding copy is added.

`constructor_cell_route_alternative_checks` and
`constructor_cell_route_alternative_fields` charge the new selection work.
An unproved selected target still undergoes the ordinary exact-key validation;
those comparisons are not claimed as eliminated. Existing key-proof avoided-field
counters describe the publication path, not net avoidance across selection.

The new cross-stage test puts a type-correct but wrong-key target first, then the
correct target. All graph exports, source snapshots and binding audits match the
control, and generic constructor lookups are strictly fewer than both the no-route
control and the wrong-target-only configuration. This establishes a concrete
lookup takeover in the regression fixture, not a whole-workload speedup or a
large memory reduction. All 55 ownership tests pass, including existing union,
hide/delete, alias and code-tampering checks.

```sh
CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --test cell_ownership
```

Next measure installed-catalog coverage with the multi-target route, including
selection comparisons and additional static target storage. The large logical
compression and stage-switch RHS objective is still open.

## Installed multi-target catalog results

Reused the exact-source, already-audited `witness-observation.json` files from the
structural worktree and compiled them with current `apply-witnesses`. Their
29/24/90/79 recipes match the observed path counts. Candidate artifacts differ
from frozen seeds only by `ownership_witnesses` and the artifact checksum.
Both sides were executed with the same current binary and inherited-owner mode.

| case | port-key lookups before → after | route probes | alternative checks | alternative field checks | additional prepared field checks |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 2,452 → 2,422 | 258 | 22 | 36 | 76 |
| loopfact | 1,927 → 1,910 | 204 | 13 | 20 | 33 |
| sum-bits | 11,455 → 11,330 | 1,649 | 107 | 139 | 344 |
| dot-product | 8,299 → 8,139 | 1,988 | 87 | 124 | 437 |

All 2,652 per-Run graph/RHS/write checks and four terminal checks pass. Final
Graph owned heap is unchanged in each pair: 705,175 / 616,289 / 1,830,387 /
1,798,019 bytes. Retained Program grows by 111,184 / 92,660 / 297,564 / 274,040
bytes (catalog JSON and derived routes included). There is no runtime instance
compression from this change and no timing claim. These comparisons are against
no witness catalog, not an isolated single-target ablation.

This removes 0.9%–1.9% of port-key queries. It is useful lookup coverage, but far
from the requested structural target. The high route-probe count relative to
accepted results argues for selecting applicability earlier in the compiled Entry
and for whole-handoff/state takeover, rather than treating more speculative
candidate probes as progress by themselves.

Reproduce with the build flags above:

```sh
target/debug/examples/batch_cell_learning apply-witnesses out/cell-bake-owner-merge/batch witness-source witness-multi
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch witness-multi
```

For each case, run runtime_storage_peak on the seed and witness-multi candidate
with `inherited-owners --port-domains-only`, writing CASE-seed.json and
CASE-multi.json into out/cell-witness-multi, then:

```sh
python3 benchmarks/cell-bake-owner-merge/multi_witness_results.py out/cell-witness-multi out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/multi-witness-results.json
```
