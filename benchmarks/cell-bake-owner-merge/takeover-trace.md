# Learn from the actual transferred and retired Cell layout

The previous passive catalog runner compacted array capacity but did not use
completed-source takeover, stable fields, port-only domains or retired prefixes.
Its final graph could match production while its intermediate ownership shapes
were different. Learning another catalog from that execution missed actual
post-retirement continuations.

`runtime_catalog_trace --completed-owners --retired-prefixes` now uses the same
boundary actions as the selected storage execution. Passive tracing no longer
blocks prefix retirement: its records contain static shapes and operation
positions, and cannot add executable shapes. Exploratory training remains
incompatible with retirement. The existing proof that the installed prefix
preserves all reachable append transitions remains authoritative. Source
identity, native-port guards, visibility and settled-boundary checks remain live.

The deletion/union/recompletion integration fixture now enables passive tracing
while requiring real prefix retirement and identical snapshots, binding audits
and exported graphs. All 69 ownership tests pass (queue job 388).

## Observation and batched selection

Using the 108-extension Program from `direct-prefix-growth`, job 386 checks all
882 saved Run graph/effect digests. Final ownership inventory and prefix
retirement statistics equal the unobserved execution: 147 takeovers retire 190
source frames and 486 symbols. Observer probe counters are diagnostic overhead,
not unchanged runtime work or savings.

The trace has 1,449 proposals: 571 one-hop, 324 two-hop and 554 three-hop paths.
Repeated proposals with shared inputs number 64, 145 and 255 respectively.
Batch job 387 runs the existing typed selector at three budgets, retaining all
seed transitions, then measures each resulting Program with the same frozen
`component-reuse` runtime and flags.

| Budget | Replaced maximal paths | Graph bytes | Resident Program bytes |
| --- | ---: | ---: | ---: |
| Seed | 0 | 1,256,075 | 107,599,014 |
| 32 | 32 | 1,254,943 | 107,519,028 |
| 128 | 81 | 1,242,855 | 107,935,263 |
| 256 | 81 | 1,242,855 | 107,935,263 |

The selected 128-budget graph saves 13,220 bytes. Components fall from 1,364 to
1,280; 148 final components contain four source frames. Component storage saves
9,984 bytes, live-fact directory capacity 1,024 and boundaries 4,344; source Cell
storage grows 2,132 bytes. Source records/fact identities are not claimed deleted.
Resident Program grows 336,249 bytes and process requested-heap peak grows from
113,429,158 to 113,752,343. This is a Graph-only reduction, not a total-process
memory reduction or a timing result. It measures standalone Cell runtime, not
upstream egglog.

Graph is 49,044 bytes above the historical 30% threshold. Its historical
3,979,373-byte denominator is a working-tree observation, not an isolated
immutable baseline executable. Saturated RHS skipping is still unfinished.
Only 135 apply observations are fully RHS-covered inside a component; 4,537
lack a local constructor, 1,050 encounter writes and 157 nontrivial unions.
More paths alone do not prove these effects redundant. Cross-source matching,
mutable reads and ordered effects still require checked completion programs.

## Reproduction

Run builds and commands below through the shared compute queue. Build examples
with `iterative-bake,sparse-cells,storage-metrics`.

```sh
runtime_catalog_trace out/cell-direct-prefix-growth/budget128/program.json out/cell-component-reuse/checked.json out/cell-takeover-trace/trace.json --completed-owners --retired-prefixes
python3 benchmarks/cell-bake-owner-merge/takeover_trace_batch.py out/cell-takeover-trace out/cell-direct-prefix-growth/budget128/program.json out/cell-component-reuse/memory.json /private/tmp/eggfuse-dual-local-target/debug/examples/extend_observed_owners out/cell-component-reuse/runtime_storage_peak
```

Use a fresh output root containing the trace; selector output directories must
not already exist. The batch's final digest and Run sequence checks are not
per-Run acceptance. Selected-candidate boundary and native acceptance results
are recorded separately in the adjacent JSON report.

Selected budget 128 passes all 882 graph and ordered effect checks against the
seed (job 389), also exactly matching the previous saved checks. The native
choice validator passes all four comparisons with overall `status: pass`
(job 390). The 32 and 256 variants have final-state and Run-sequence checks
only; the full admission claim applies to budget 128.
