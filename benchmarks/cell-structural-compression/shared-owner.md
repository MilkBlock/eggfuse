# Completed components take over source-frame storage

The preceding experiment discharged parent references but retained all fact-owning
Cells. The existing catalog already supplies checked component membership from
actual Entry applications. This change uses that membership to replace eligible
completed source records, rather than adding a parallel maintained fact graph.

At a settled source Run boundary, at least two eligible frames in one component
move their fields and FactState records into shared arrays. The existing logical
ID directory distinguishes active and completed storage; no second per-fact index
is built. FactRef(cell,op), per-fact visibility, epochs, birth times, hashes and
retirement remain authoritative. Frame descriptors retain template/lifecycle and
array-range information. In-flight frames, shared leases, parent-backed inputs,
writer/external reference holders and unsupported facts stay on their old path.

Slots already proved equal to the component's existing symbols are removed from
the transferred field arrays. Ordinary scalar/unsupported fields remain explicit.
When the last component fact disappears while a retained parent still needs those
symbols, the required completed frame moves back to ordinary storage and the
existing component-death path restores its equality fields. This boundary fallback
creates no per-producer consumer lists. Full shared arrays release with their last
frame; partially retired slices remain charged until then.

This is opt-in through `Graph::transfer_completed_owners` under storage-metrics.
There is no default execution policy or speed claim. It is the actual standalone
Cell runtime, not native egglog and not a standalone graph mock.

## Measured result and controls

Same closure-existing program; every one of 1,428 saved graph and ordered effect
hashes passes, with transfer after each original Run and without diagnostic slot/
parent compaction. Semantic acceptance passes. The storage control reclaims the
source record arena's spare capacity in **both** lanes, and leaves field/fact
capacities otherwise natural. It prevents claiming source-arena shrinking as
structural compression.

| Final census | Control | Shared owners |
| --- | ---: | ---: |
| Counted Graph bytes | 1,541,640 | 1,447,936 |
| Explicit live Cell slots | 13,770 | 11,875 |
| Source record capacity bytes | 286,200 | 198,840 |
| New completed descriptor/owner capacity bytes | 0 | 102,400 |
| Cell slot allocation bytes | 462,960 | 384,384 |
| Fact allocation bytes | 292,752 | 262,584 |

Net saving is **93,704 bytes, 6.08%** of this census. Boundary high-water equals
these final values in both lanes. This is not total egraph heap, RSS, or the peak
while arrays are being transferred. The latter remains unmeasured. Logical fact
counts and source effect scheduling are unchanged. Some savings are shared array
capacity, alongside real removal of duplicate equality-slot entries.

838 frames transfer cumulatively; 728 survive in 353 shared owners. 302 surviving
owners span distinct source started_epoch values. Full original source records
remaining: 1,657. 2,218 equality slots are delegated cumulatively, no frame restore
is needed on this sum-bits execution (the fallback is exercised by a regression).
The live explicit-slot difference is 1,895, not 2,218; cumulative work is not a
simultaneous storage census.

The shared arrays retain 142 retired slot entries and 155 retired fact positions.
The new record capacities actually cost 15,040 bytes more than the old records
for the corresponding live IDs in this control. These costs are included, not
hidden. The result is useful structural progress, **not** the requested large
whole-egraph compression or the 30%-of-original target.

An earlier array-migration-only run appeared to save 14.3% against an unshrunk
source arena. That number mixed reclamation and replacement and is superseded by
the matched control above. Do not promote it as a structural result.

## Remaining obligations and next opportunity

The layout still retains a descriptor per original logical Cell, dynamic scalar
inputs, per-fact metadata, unused array positions in partially retired groups,
and the old boundary indices. Most shared owners contain only two live frames.
The 58/143 Get completion chain is not claimed fully taken over: parent/writer
restrictions still exclude relevant frames. No additional saturated RHS applies
are skipped by this storage change.

Next compilation should remove repeated retained state and use shared layout
information to reduce descriptor/fact metadata, while broadening proven coverage.
Simply increasing migration counts is not a credit signal. Charge boundary restores,
address routing, array movement, retired slices and peak allocation; maintain
all original source Run/effect ordering and uncovered readers.

## Validation

149 runtime tests (including parallel-residuals); 34 ownership tests; 21 ripsat
integration tests. The new integration regression checks serial and two-worker
execution after transfer, later matching, union collisions, explicit deletion, and
component death while an external parent still reads a delegated field. The arena
regression checks duplicate-group rejection, logical addresses after partial
retirement and release of arrays with the last frame. Default runtime cargo check
passes. The final extra profile fields and duplicate-input rejection do not change
the audited valid runtime path; the storage control uses the final profiling code.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/shared-owner-symbolic.json --natural --shared-owners
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_parent_storage -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/shared-owner-symbolic.json out/cell-structural-compression/shared-owner-storage-control.json --shared-owners
```

## Connect completed parent inheritance to owner replacement

The last catalog's actual execution detached 128 parents, but the storage transfer
excluded every `symbolic_slots` frame. That excluded the exact state produced by
completed-parent lowering. Removing this exclusion lets the checked symbolic
read contract survive physical replacement. Unsupported parent projections,
external references, active writers, shared arrays and unsettled Runs retain the
same exclusions. No new binding copy or lookup registry is introduced.

The combined opt-in run enables `use_completed_parent_takeover` and calls the
existing transfer at Run boundaries. The new `shared_owner_inherited_frames`
counter records already-symbolic frames actually transferred (not all detached
parents, and not saved RHS work). It records 37 frames. Cumulative transfers grow
838 -> 898; surviving transferred frames 728 -> 787. Rule 58 now contributes 28
surviving transferred frames; rule 143 remains outside this surviving coverage.
Cross-started-epoch owners grow 302 -> 321. Their epochs establish observed stage
span, not a proof of saturation against arbitrary future external input.

With the same source-record capacity control in both lanes:

| Final counted storage | Bytes |
| --- | ---: |
| Control | 1,541,640 |
| Previous shared owners | 1,447,936 |
| Parent inheritance + shared owners | 1,438,168 |

The combined saving is 103,472 bytes (6.71%); incremental saving is 9,768 bytes.
Explicit slots are 11,833; parent links 216. Boundary high-water equals final
storage. The full results, including charged metadata and retired array ranges,
are in `inherited-owner-results.json`. This remains a partial Graph census, not
full heap or intra-Run peak; no additional saturated RHS skipping or speed gain
is claimed. It demonstrates why parent detachment and owner replacement need to
compose, but does not establish the requested large whole-egraph compression.

All 1,428 original graph and ordered RHS/write/resume checks pass. The new final
export passes `choice_diagnosis.py`; see `inherited-owner-semantic.json`. All 34
ownership tests pass. The existing deletion/union/retained-parent regression now
runs both ordinary inputs and parent-inherited inputs, each serially and with two
workers, and requires inherited frames to reach physical shared storage.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/shared-owner-inherited.json --natural --shared-owners --parent-takeover
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_parent_storage -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/shared-owner-inherited.json out/cell-structural-compression/shared-owner-inherited-storage.json --shared-owners --parent-takeover
```

## Whole Graph heap and transfer peak (requested allocation bytes)

The partial census above omitted ownership and other Graph state. The existing
allocation observer now has matched `record-control` / `inherited-owners` modes,
records the transfer's within-Run peak, and emits destructive field attribution.
Both modes run the same 1,428 source Runs and match the previously audited final
state. This memory observer does not replace the earlier per-Run semantic audit.

| Requested allocation measure | Control | Inherited owners |
| --- | ---: | ---: |
| Graph-owned heap released after Executor teardown | 3,068,093 | 2,964,621 |
| Compiled Program heap released afterwards | 117,207,936 | 117,208,416 |
| Maximum additional heap during a transfer boundary | 0 | 49,552 |

Thus the **Graph-owned heap reduction is 3.37%**, not 6.71%. Both are valid only
with their stated denominators. Compiled Program memory is separate, and gains
480 bytes for completed-parent layouts. Process peaks include that Program,
Executor caches and the fixed diagnostic buffer; they are not Graph-only peaks.
The complete summary is `inherited-owner-heap.json`. Its unlisted Graph teardown
residual is explicitly charged: 55,820 bytes in both lanes. Shared allocations
are charged to their last owner; these are requested bytes, not RSS.

Largest remaining Graph fields after takeover:

| Field | Bytes |
| --- | ---: |
| Cell storage | 971,208 |
| Functions | 354,408 |
| Ownership components | 279,488 |
| Stable ports | 224,118 |
| Ownership boundary signal index | 214,568 |
| Ownership frame directory/records | 163,584 |
| Legacy uses index | 119,468 |
| Constructor intern index | 102,408 |
| Ownership barrier observation history | 98,304 |

The measured 103,472-byte saving is entirely in Cell storage. The ownership
components, frame directory and boundary index have not been replaced by the
completed owner backend. This changes the next priority: increasing source-frame
transfer counts alone still leaves the parallel ownership representation intact.
A structural completion state must share the authoritative component addressing
and template wiring, and remove its redundant representation, while retaining
external query domains, fact visibility, stable port identities and worker read
epochs. The boundary index is not all removable just because a component spans
Runs: external consumers and future union-enabled matches remain live.

The 98,304-byte barrier vector is observer history, not a semantic egraph fact.
Removing it must not be credited as saturated-Cell compression. This distinction
prevents hiding instrumentation reclamation inside the requested structural gain.

Reproduce the two heap lanes with `runtime_storage_peak` and then compare:

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo build --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak
target/debug/examples/runtime_storage_peak out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/heap-detail-record-control.json record-control
target/debug/examples/runtime_storage_peak out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/heap-detail-inherited-owners.json inherited-owners
python3 benchmarks/cell-structural-compression/analyze_owner_heap.py out/cell-structural-compression/heap-detail-record-control.json out/cell-structural-compression/heap-detail-inherited-owners.json out/cell-structural-compression/shared-owner-inherited-storage.json benchmarks/cell-structural-compression/inherited-owner-heap.json
```

## Discard dead matched inputs from completed owners

The last catalog's executed frames still retained matched inputs that no completed
operation or later producer projection could read. The existing completed-parent
analysis now supplies both its parent proof and a per-rule discard list. It keeps
all operation operands/results, static result alias sources and multi-stage read
columns. Only matched input slots absent from that conservative retained set enter
the discard list. Imported or manually constructed templates without the checked
rule/template correspondence retain their fields.

At an eligible completed owner transfer, the runtime removes those fields before
moving the remaining array. The layout is shared per rule; there is no second
binding map or per-instance lifetime graph. Required scalar inputs, actual
constructor-result aliases and later cross-stage projections remain live. Ordinary
execution remains unchanged; `use_completed_parent_takeover` prepares this opt-in
analysis, and `transfer_completed_owners` applies it at the same settled Run
boundary. Existing external-reference, parent and shared-array exclusions remain.

An initial representation stored every retained slot and grew compiled Program
heap by 47,184 bytes to save only 34,008 runtime bytes. It was rejected. The final
representation stores only dead matched input numbers; it does not duplicate the
whole retained set in every compiled plan. It still has a measured static cost,
which is charged below.

Compared with the previous inherited-owner configuration:

| Measure | Previous | Dead-input layout |
| --- | ---: | ---: |
| Graph-owned requested heap | 2,964,621 | 2,930,613 |
| Compiled Program requested heap | 117,208,416 | 117,230,752 |
| Final explicit live Cell slots | 11,833 | 10,537 |
| Maximum transfer extra requested heap | 49,552 | 48,752 |

Runtime heap saves 34,008 bytes; compiled Program costs 22,336 additional bytes;
the combined retained Graph+Program saving is 11,672 bytes. Against the matched
control's 3,068,093 Graph bytes, cumulative Graph reduction is 137,480 bytes,
**4.48%**. This does not meet the large-compression target. No source facts,
constructor operations or additional RHS applications are skipped.

The discard counter is 1,482 cumulative fields, while the live field difference
is 1,296. Eq-symbol delegation remains 2,260 and is not counted again as a dead
input saving. Actual transfer count remains 898. Ownership components, frame
directory and boundary maintenance remain present; this change does not claim
to replace those paths.

Validation: 1,428 original Run graph and ordered RHS/write/resume checks pass;
final export semantic acceptance passes; 149 runtime, 35 ownership and 21 ripsat
tests pass; default runtime cargo check passes.
The dedicated fixture requires real unused-input deletion and later-stage reads
in both serial and two-worker execution. The retained-subset proof is conservative;
all original source/effect boundaries remain authoritative.

Reproduction uses the preceding commands with `completed-dead-inputs-audit.json`
as the audit output, and `dead-inputs-heap-record-control.json` /
`dead-inputs-heap-inherited-owners.json` as memory outputs. The analyzer's audited
final-state digest is unchanged. Tracked evidence is in
`completed-dead-inputs-results.json`, `completed-dead-inputs-heap.json`, and
`completed-dead-inputs-semantic.json`. These measure the actual standalone Cell
runtime, not native egglog; requested allocation bytes are not RSS.

## Rejected: replace a retired completion receipt from the current match

The current executable catalog contains seven direct-completion plans. Their
exports include current Query sites as well as historical Effect sites. A trial
used those existing typed sites (and known static query aliases) to repair a
retired receipt from an already matched constructor witness, with no key search.
It validated every output before updating any shared result slot and charged
new checks, writes and scratch allocations. Hidden/wrong-table/missing receipts
retained the old fallback; no equality-only substitution was admitted.

The actual 1,428-Run execution rejects this as a useful optimization:

- Direct completions remain 183; retired-witness fallbacks remain 26.
- Eligible matched-receipt checks: **zero**; updates, misses and scratch bytes:
  zero. None of these retired outputs is a Query site or the supported static
  Query alias. The relevant Get, Single and SubTuple tables are constructors,
  so the zero is not caused by a non-constructor admission guard.
- All pre-existing integer stage counters, Graph work counters, query counters
  and final source storage are unchanged. Timing fields are excluded.
- Every saved Run graph and ordered RHS/write/resume hash passes; final export
  exactly equals the already accepted dead-input execution.

The trial was removed from the engine. The reproducible source is
`matched-witness-trial.patch` (applies to `35c9afd0`); evidence is in
`matched-witness-trial-results.json`. The trial passed 21 ripsat integration tests
and five work-credit tests. This is a rejected experiment, not a new default
execution path, compression claim or latency improvement. Its work-credit reader
was finalized to exclude the miss outcome from charged work; the raw audited
reader also reported that zero-valued outcome.

This narrows the next structural target: current query evidence cannot replace
the remaining historical RHS results. Their actual receipt identities need to
survive coalescence through the existing completed-owner/publication state.
Adding a general pre-RHS query probe or retaining a second unbounded forwarding
history would preserve the duplicate maintenance we are trying to remove.
A future takeover must connect the existing result slots to static Cell wiring
at the actual coalescence point and preserve source-Run visibility; it cannot
infer constructor identity from equal result classes alone. That takeover is
not implemented by this trial.

To reproduce the trial in an isolated checkout with the same saved artifacts:
apply the patch, build `runtime_closure_work` with the preceding features, and
run the preceding audited command with output `matched-witness-audit.json`.
Keep the `--natural --shared-owners --parent-takeover` options. Compare to
`completed-dead-inputs-audit.json`, excluding timing fields; do not install the
trial merely because its semantic audit passes.

## Trace the actual retired-result lifetime

The rejected current-query recovery left 26 failures. A bounded, opt-in coordinator
archive now records captures, same-key forwarding, fact retirement, map clearing,
local/publication result refreshes, and the failed result's location. On a failure,
the observer replays its archive and samples the historical target's current table
and visibility. The archive never participates in execution or receipt resolution;
there is no new maintained forwarding index. Without explicit tracing, no events
or archive arrays are allocated. This observation is not a heap/speed benchmark.

The 32,768-event budget captured **4,792 events with zero drops**: 994 forwards,
844 fact retirements, 766 captures, 77 refreshes, 2,085 map clears, and 26 failures.
Multiple publication clears can occur within one source Run. Offline replay
checks each clear's map cardinality, chronological order, absence of cycles,
and agreement with both the current and archived targets sampled at failure.
Incomplete archives and inconsistent replays are rejected.

The result is specific:

- All 26 failures are rule 137, Effect 2: the `Single` result of
  `SubTuple(expr,x,1) -> Single(Get(expr,x))`.
- Every failed physical receipt had exactly one previously observed same-key
  forwarding edge. Its target was **visible in Single at the moment of failure**.
- All 26 forwarding edges had crossed a map clear and a source Run boundary.
  Run gaps were 3 (2 cases), 4 (18), 10 (2), 12 (1), and 13 (3).
- For 20 failures, a result slot holding the same old receipt had already been
  refreshed, yet the consumer still held the old reference. No capture of that
  old receipt occurred after the earlier refresh and before failure. Six had no
  observed refresh. Thus refreshing one retained occurrence does not cover every
  use. The archive does not identify unique shared-storage allocations, so it
  does not yet locate the exact pair of retained owners.

For example, receipt `(cell=536,op=1)` was captured at Runs 98, 102 and 106,
coalesced at Run 106 to `(129,78)`, and locally refreshed in a rule-143 result
slot. At Run 110 rule 137 still read `(536,1)` after the forwarding map had been
cleared; `(129,78)` remained visible. No new constructor query was needed to
establish that the previously recorded replacement still existed. This is
historical evidence, not authorization to retain the archive as a runtime map.

This rules out "the result no longer exists" for these 26 cases. It strengthens
the structural target: completed Cell state must keep the necessary result
identity shared through coalescence and downstream retention. Simply extending
the global forwarding map or scanning every history would add the duplicate
maintenance that the takeover is meant to eliminate. These 26 cases alone also
do not establish large whole-egraph compression.

All 1,428 saved Run graph and ordered RHS/write/resume hashes pass. Graph counters,
query counters and existing integer stage counters exactly match the previous
execution; final export matches and semantic acceptance passes. Runtime tests:
150; offline causal-analysis tests: 3; default runtime cargo check passes.
Tracked evidence: `receipt-lifetime-results.json` and
`receipt-lifetime-semantic.json`; the full raw archive remains in ignored `out/`.
This is actual standalone Cell runtime observation, not native egglog execution.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/receipt-lifetime-audit.json --natural --shared-owners --parent-takeover --receipt-trace
python3 benchmarks/cell-structural-compression/analyze_receipt_lifetime.py out/cell-structural-compression/receipt-lifetime-audit.json benchmarks/cell-structural-compression/receipt-lifetime-results.json
python3 benchmarks/cell-structural-compression/test_receipt_lifetime.py
```
