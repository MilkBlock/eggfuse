# Keep compiled Cell execution separate from optional discovery state

Baseline: `28711d73`. This changes the standalone Cell CPU runtime, not native
egglog. It is a storage/allocation checkpoint, not speed admission or proof of
general egraph sparsity. It follows the measured join and ownership opportunity
in [cell-projected-owner](../cell-projected-owner/README.md).

The compiled switch already knows the active Cell at each execution position.
Instances nevertheless stored that Cell ID again, together with a candidate
composition stack, pending Join, witness and sample window, even when executing
a frozen catalog without learning. The active ID is now read from the switch.
The discovery fields live in one optional `Rc<Discovery>`; forks share it until
modified. Normal compiled execution never constructs that owner. The original
stack reducer for uncompiled catalogs still creates and uses it.

Actual result history, logical output, direct-match ownership and the last
applied Run stay in the execution state. In particular, retaining the last Run
preserves provenance when collection starts later. Successful applications
still update all original hit counters; query success does not become a rule
application. Root receipts, catalog resets, source publication boundaries and
residual matching retain their previous behavior. No new binding/fact graph or
per-producer subscription is introduced.

## Measured costs

The normal combined sum-bits program and its uncombined control both retain
all 677 checked integer work counters. History allocations stay at 369: the
165 owner allocations removed by the preceding change remain eliminated.

| Record on this 64-bit build | Before bytes | After bytes |
|---|---:|---:|
| Cell Entry | 192 | 104 |
| Completion | 192 | 104 |
| Query winner | 296 | 208 |
| Legacy route | 184 | 96 |

The execution State is now 64 bytes. The projected history handle itself is
still 24 bytes; this change removes redundant state elsewhere, rather than
claiming to shrink that handle. Relative to the pre-projection version, Entry
and completion records are 104 instead of 184 bytes. Compiled applications now
read the active unit from the shared switch when counting hits; this is a real
read cost replacing the redundant stored ID.

A separate allocator-instrumented executable ran each mode once on the same
complete sum-bits candidate. It measures requests during execution, excluding
setup, reporting and export, and must not be used for latency measurement.

| Execution mode | Allocations before → after | Requested bytes before → after |
|---|---:|---:|
| Normal | 168,132 → 168,132 | 30,803,935 → 29,054,935 |
| Collect actual applications for Bake | 177,811 → 181,642 | 32,189,711 → 30,836,863 |

Normal inference requests 1,749,000 fewer bytes. Learning requests 1,352,848
fewer bytes but performs **3,831 extra allocations**, primarily for independent
discovery owners. It is not an allocation-count win in learning mode. The
sampled candidate's equal-weight work score remains 2,768; that score does not
price these allocator differences or prove throughput improvement.

The normal final published-discovery census is zero. The learning census has
476 distinct owners (49,504 bytes including estimated Rc headers), 27,680
stack bytes and 111,776 shared-window bytes. These are final reachable storage,
not lifetime or peak allocation counts. Peak live requested bytes, which
include allocations already live at inference start, decrease only 153,484
bytes normally and 76,761 bytes with learning. They are not RSS measurements.

## Evidence and reproduction

Both old/new production modes preserve the final graph and all 1,428 ordered
Runs. Both Bake rounds preserve the **entire saved apply history**, not merely
its event count, and choose the identical candidate. Graph, schedule, ordered
RHS, writes and resumes match the existing five acceptance hashes. Native
sum-bits choice acceptance passes. A separate `--audit-stages` comparison tests
the fallback path; it disables compiled publication and is not used to claim
direct-completion coverage.

94 sparse runtime tests, 79 default runtime tests and 27 integration tests pass
(`ripsat_completion`, `state_inheritance`, `query_receipts`, `query_workers`).
Forked discovery tests preserve the producer while modifying a successor;
direct-completion fixtures verify all Run boundaries and zero published
discovery owners without training. Minimal-feature compilation and README
compile/run/bench pass; bench uses one repetition as a smoke check. No full
Raytrace timing campaign was run.

Freeze both binaries from the baseline and candidate using:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime
```

Use the preceding experiment's identical `out/queued-union-admission/program.json`
and `out/cell-projected-owner/uncombined-program.json`, with `--local-congruence`.
For the allocation diagnostic, copy the same
`engine/cell-runtime/examples/cell_state_allocations.rs` into the isolated
baseline checkout (its production sources remain untouched) and build in each
checkout with the same feature list:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --example cell_state_allocations
target/release/examples/cell_state_allocations PROGRAM FRESH_OUTPUT normal
target/release/examples/cell_state_allocations PROGRAM FRESH_OUTPUT learn
```

The new Bake replay uses the preceding seed and parameters:

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/terminal-union-seed.json --output out/cell-execution-state/iteration --objective ripsat-completion --score measured-work --rounds 1 --trial-limit 1 --local-congruence true
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-execution-state/semantic out/cell-execution-state/semantic-acceptance.json
python3 benchmarks/cell-execution-state/check.py out/cell-execution-state benchmarks/cell-execution-state/results.json
```

The collector checks measured source/binary identities, exact old/new states,
ordered Runs, work and discovery counters, complete histories, selected
candidate identity and semantic input hashes. [results.json](results.json)
retains both positive and negative allocation deltas. This change and the
projected-owner change are the first two implementation commits in this batch;
defer the next combined speed admission to the agreed cadence.
