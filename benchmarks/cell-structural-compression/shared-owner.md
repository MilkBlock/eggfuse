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
