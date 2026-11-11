# Prepare shared query columns once per source Run

Control: merged branch `10588f41`. Scope: **standalone Cell CPU**. This is a
small follow-up to the branch integration, not another parallel backend or a
new timing checkpoint.

The previous full Raytrace execution has 1,131,289 partitioned Entry deliveries
through only 23,078 active mixed-rule pivots. `uncovered_expansion_entry` called
`activate_expansion` for every Entry; that method unconditionally called
`prepare_columns` before consulting its existing active flag. A stable table
avoids rebuilding its index, but each call still walks the compiled layout,
checks table versions and looks up the prepared column maps on the coordinator.

The same Cell plan is now prepared at its first activation only. Its fixed
layout remains valid while the source Run borrows the graph. Matching cannot
perform RHS writes or retire index columns; completion scopes and unsupported
query hosts remain excluded. `finished` and error `discard` reset the existing
active flag before another Run. Later Runs still prepare their own current
views. No persistent cache, fact graph, instance field or cross-Run certificate
is introduced. This does not grant any new Ripsat/Bake completion credit.

The retained first preparation stays at the same execution position, so later
queries see the same lazily created columns and reverse-selection options.
Two global counters report actual first preparations and active reuses. They
add 16 bytes per counter structure, not per Entry, and use no atomics/timers.
All original query, admission, publication, winner and effect work remains.

`results.json` records complete sum-bits/Raytrace work and input/report hashes.
The old executable has no dedicated preparation counter: its old call count
is explicitly reconstructed from the unchanged activation calls, equal to
new preparations plus reuses. It is not presented as an old measured counter,
an allocation count or a speedup. The equality checks require every graph
counter, total key reads, Sieve, Free Join, Entry schedule, known-result reuse,
neighbor work and non-timing publication count to remain unchanged, together
with exact final states and ordered Runs.

| Complete workload | Old calls, reconstructed | Actual first preparations | Repeated calls removed |
|---|---:|---:|---:|
| sum-bits | 3,253 | 2,342 | 911 |
| Raytrace | 1,150,684 | 42,473 | 1,108,211 |

All 1,428 / 16,883 ordered Runs and the listed work counters agree exactly.
The unchanged sum-bits acceptance returns `pass` / exit 0. These removed
calls previously checked already-built columns; they were not full index
rebuilds, and their count does not predict an equal fraction of runtime saved.

The native-checked mixed-Entry fixture verifies reuse and continues through
scalar changes, union, deletion and recreation for 1/2/4 workers; all four
residual-query integrations pass normally and with zero-bit fingerprints.
The first activation and reset paths remain covered by those real source Runs.
The merged branch's minimal/all-feature and README command checks are retained;
this follow-up changes only the optional residual-worker implementation.
The unchanged sum-bits native validator must return `pass` / exit 0. Raytrace
remains a relative regression check. No additional throughput campaign is run.

```sh
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test parallel_residuals
CELL_CPU_HASH_BITS=0 cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test parallel_residuals
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze the executable, run the same frozen programs with four workers,
# --repair-ports --entry-publications --cell-absorption
# --parallel-residuals --parallel-publication into fresh ROOT/sum and ROOT/ray.
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-run-column-preparation/check.py ROOT MERGE_ROOT RESULTS.json
```

Saved contract inputs are reused; `ROOT/semantic/run-values/state.json` is the
new sum-bits export. Raw artifacts remain under ignored
`out/cell-run-column-preparation`.
