# Shared entry ownership and measured Bake credit

This experiment extends `acaf80f0` on the **standalone Cell CPU runtime**.
It uses the preceding 208-unit sum-bits and 316-unit Raytrace catalogs with
constructor result-port propagation. Native egglog supplies focused semantic
checks; the timings do not measure native egglog.

## Which old path is replaced

The existing compiled entry node already owns a row's checked matching
parameters. Spine separately indexed its producer expression by the same row
witness, retired that index after changes, and looked it up during matching.
`--entry-publications` gives an exhaustive shared entry both responsibilities.

Ownership is restricted to tables with exactly one unfiltered entry pattern
and a scheduled Spine consumer. Literal/repeated-variable patterns, multiple
entry patterns, and dedicated view tables retain their existing owner. The
runtime derives this eligibility from the validated compiler entry plan.

An owned entry contains a lazily decoded packet and a handle to its producer
expression. Ordinary nodes keep their original compact packet maps; only
publication owners use the extended entry layout. Expressions use reusable contiguous slots; they do not allocate
one additional reference-counted object per publication. An unused producer
can publish before the first consumer without forcing row decoding. All
consumers borrow the same entry at their original scheduled Run.

After repair, the existing ordered publication logic resolves same-key
forwarding and selects the last producer. Its result is installed directly in
the entry. Matching reads the row and source together, eliminating the separate
Spine source hash lookup. Retirement removes both from the entry. Other rows
still use exact residual matching. No old source index is kept for owned tables.

This replaces source-index storage and maintenance for the covered entries.
It does **not** remove ordinary graph congruence repair, canonical table indexes,
RHS execution, visibility checks, or the Run publication barrier. The slot
number locates an expression; it is not an equality proof.

The complete application audit compares final graph exports, semantic
schedules, ordered RHS inputs, effective function writes, continuation resumes,
and normalized Spine shape traces. All comparisons pass. Ordinary dependency
repairs remain 1,496 / 479,589.

| Actual work | sum-bits control / nodes | Raytrace control / nodes |
|---|---:|---:|
| Legacy source-index writes | 8,414 / 2,501 | 2,302,142 / 258,317 |
| Legacy source-index probes | 5,738 / 2,521 | 1,871,989 / 286,859 |
| Entry row decodes | 6,357 / 5,743 | 2,407,239 / 2,313,765 |
| Legacy retirement header checks | 4,342 / 1,143 | 1,772,810 / 141,222 |
| New entry retirement checks | 0 / 2,854 | 0 / 1,558,795 |
| New entry expression writes | 0 / 5,913 | 0 / 2,043,825 |

Publication writes and visibility work have largely moved to the shared owner;
they are not all avoided work. The concrete eliminations include the separate
source index, 3,217 / 1,585,130 source hash probes, and 614 / 93,474 entry row
decodes. The final retirement dispatcher consumes explicit removals directly
from the sealed change batch and checks visibility only for wake events. Total
retirement header checks decrease by 345 / 72,793; it also avoids rereading the
already-known table identity. Pointer reads and expression-slot writes still cost work. Counts refer
to execution operations, not newly committed mutations. `audit.json` retains
the complete counters and trace hashes.

## Credit comes from complete executions

`iterate` now defaults to `--score measured-work`. The old frequency-times-proof
score remains available as `--score static` and orders proposals in both modes.
Existing catalogs and their typed certificates can be resumed unchanged.
The measured baseline is the catalog after the requested proof objective has
been emitted. Admission does not independently gate that objective migration
or remove earlier cells; the timing experiment therefore keeps the frozen v2
catalogs in every lane and measures entry ownership separately.

For each bounded proposal, the compiler executes the current catalog and that
catalog plus exactly one candidate from the same initial graph. Pair collection
is disabled in **both** scored executions: discovery itself can force otherwise
unused producer roots into existence. A trial must preserve the full semantic
audit, including ordered effective writes and resumes, before receiving credit.

The score is the sum of `baseline counter - trial counter` over the explicit
operation ledger in `tools/cell-compiler/src/work_credit.rs`. It includes global
key probes, row reads, constructor/union requests, frames, repairs, matching
candidates, source-index and entry operations, origin-key slots, query attempts,
context-cache operations, guards, publication index writes, and actual history
reads, copied slots and container allocations. Receipt hits receive no direct
reward. Failed matches and unused captures contribute to the measured costs.

Every operation currently has weight one. These are reproducible counts of
instrumented operations, **not calibrated nanoseconds or an exhaustive hardware
cost model**. Some counters measure different levels of an operation, such as
constructor dispatch and the key probe it performs. Compiler/trial time is
recorded separately and is not amortized into the inference score. A positive
score still requires an independent throughput measurement.

Learning remains bounded replay and recompilation from the initial graph,
with substantial discovery/proof/replay cost. This is not in-process online
catalog replacement.

Only the highest positive candidate is admitted in a round. Independent trial
credits are never summed to justify adding several overlapping cells together.
The next round measures against the newly accepted catalog. A bridge with only
predicted future benefit earns no measured reward. Existing cells are not
automatically removed. `--trial-limit N` bounds full replays; `trial_limit` as a
stop reason means ranked candidates remain untried.

The first four proposals from each prior catalog all fail this gate:

| Case | Static predicted reads | Actual global probes saved | Net instrumented operations saved |
|---|---|---|---|
| sum-bits | 51, 38, 12, 8 | 3, 2, 0, 8 | −206, −405, −94, −56 |
| Raytrace | 4,778, 4,060, 498, 431 | 162, 28, 21, 431 | −37,151, −18,539, −2,847, −2,944 |

For example, Raytrace's first proposal saves 162 global probes while adding
14,854 history reads, 14,854 history-slot writes, and 7,427 history allocations.
Much of its query reuse replaces a context-cache read. Its 4,778 winning visits
are neither global lookup savings nor committed mutations.

The catalogs remain at **208 / 316 units**. Each run tested four of the first
16 ranked proposals; 12 remained untried. This result establishes rejection of
these specific candidates, not convergence or absence of other useful cells.
`credit.json` includes every counter delta, witness, semantic audit, and trial
compile/replay duration. No held-out workload generalization is claimed.

## Inference measurements

The final normal executable compares the same frozen catalog with ownership
disabled (`control`) and enabled (`nodes`). `parent` is the archived preceding
runtime with the same catalog. Every lane enables result-port repair. After one
warmup per lane, sum-bits has 31 interleaved fresh-process samples and Raytrace
has seven. No build, audit, or learning process overlaps the timing run.
Background load on the shared workstation is uncontrolled.

| Case / lane | Median inference | Median peak RSS through inference |
|---|---:|---:|
| sum-bits / parent | 20.998 ms | 167.500 MiB |
| sum-bits / control | 20.873 ms | 167.516 MiB |
| sum-bits / nodes | 21.127 ms | 167.734 MiB |
| Raytrace / parent | 7.778 s | 1,875.438 MiB |
| Raytrace / control | 7.667 s | 1,874.484 MiB |
| Raytrace / nodes | 7.764 s | 1,856.672 MiB |

**No stable application speedup is demonstrated.** Node/control median
inference increases 1.22% / 1.26%. The median within-round paired changes are
+1.68% / −1.08%; Raytrace's opposite signs and overlapping ranges prohibit a
consistent speedup claim. Its control samples span 7.425–7.956 s and node
samples 7.395–7.855 s. Raytrace saves about 17.8 MiB of peak RSS.

Raytrace's median query-update/publication phase increases from 1.485 to
1.554 s, while search decreases from 3.618 to 3.603 s. Removing the separate
source index does not eliminate the entry's own maintenance. The node path
therefore remains **opt-in**; the default catalog is not enlarged or replaced.

`timings-sum.json` and `timings-raytrace.json` retain every sample, binary and
program hashes, phase times, and invariant operation counts. Setup and graph
export are excluded from inference time; peak RSS is sampled before export.
`diagnostics.json` records the preceding implementation variants separately.
Their timings are not cumulative improvements and are not the final result.

## Reproduction

Build normal inference, audit, and learner executables separately so the timed
binary does not carry the ordered-trace instrumentation:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake
```

Keep each executable before building the next feature set. The frozen programs
come from `out/producer-receipts/learn-sum-bits/program.json` and
`out/producer-receipts/indexed-audit-learn-raytrace/program.json`; extract their
`iterative_bake` objects as the resume catalogs. Their creation is documented
in the preceding producer-receipts experiment.

For each program/catalog pair:

```sh
out/entry-publications/compact-compiler iterate --program PROGRAM --resume-catalog CATALOG \
  --output NEW_DIR --objective stage-congruence --score measured-work \
  --rounds 1 --max-units 512 --new-per-round 16 --trial-limit 4 \
  --entry-publications true --repair-ports true
```

The inference CLI uses `--entry-publications` and `--repair-ports` as flags;
the learner takes explicit boolean values. Use the existing
`benchmarks/result-port-repair/audit.py`, `benchmarks/leaf-completion/measure.py`
and `benchmarks/result-port-repair/collect.py` with the saved manifests. They
compare hashes before deleting only their own large generated graph exports.
`collect.py out/entry-publications credit.json --prefix compact-` verifies and collects the
completed learning checkpoints.

For the committed timing manifests, save the final normal and audit binaries
as `out/entry-publications/compact-runtime` and `compact-audit-runtime`;
save the learner as `compact-compiler`. The timing manifest's parent binary
is the archived `acaf80f0` predecessor implementation. Use `--repeat 31` for
`timing-sum-manifest.json` and `--repeat 7` for `timing-raytrace-manifest.json`.

Validation: 182 workspace tests pass with all features (four pre-existing
ignored tests); all seven query-receipt tests also pass without sparse cells.
Focused tests cover retirement/reinsertion, union forwarding, mutable values,
filtered-entry fallback, and rejection of a statically attractive cell whose
source history costs exceed its measured savings.
