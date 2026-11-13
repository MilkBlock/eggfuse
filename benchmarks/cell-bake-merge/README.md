# Integrate structural Bake into Cell parallel execution

This is the full merge of `codex/cell-structural-compression` at
`8c73ff8434ed3410108b3a36278da9adaa4c195b`, with parallel control `a011785f`.
It includes the source branch's committed history, experiments and compiler
changes. Uncommitted work in its separate worktree is not included.
The measured runtime is the actual standalone Cell CPU, not native egglog.
This is a work/semantic checkpoint, not an elapsed-time comparison.

## What the merge preserves and replaces

The incoming branch compiles completed-slot lifetimes, parent projections,
matched handoffs, selected Unit facts and observed cross-stage closure plans.
Its representation changes also store a functional row once and compare hash
candidates against that actual row. The sparse runtime no longer stores a
second per-witness forward dependency directory; replacement derives the
reverse-incidence difference from the actual old/new row fields.

The parallel branch keeps Run-owned queues, worker-produced rows, table-index
ownership, source-prefix adoption, duplicate invalidation and completion events.
The merge adapts those owners to the new representation instead of restoring
the removed key/decoded/dependency copies:

- Unit candidates and adopted Functions share one immutable field allocation.
  Dead reservation slots share one placeholder allocation per reservation task.
- Scalar table keys remain direct indices. General table workers own the hash
  directory and exact winner selection. Preparation pins only old row handles
  from requested hash buckets; workers also compare their newly accepted rows.
  `unit_registry_key_candidates` and `unit_registry_key_handles` charge this
  extra preparation; temporary capacities enter `unit_registry_bytes`.
- Rollback removes reverse edges using discarded rows before releasing them.
  It does not reintroduce the deleted forward map. Forced collisions test old
  rows, new rows, duplicates and every tested source-abort prefix.
- Effect plans remain immutable `Arc` owners. Unique result buffers move with
  the executing Cell; incoming mutable history slots do not become shared
  mutable state between workers. Entry inheritance is attached when an
  individual query completion event is accepted, retaining its visibility test.
- Both branches had logical-write auditing. They now use one ordered event
  path, enabled explicitly; incoming specialization diagnostics enable it too.
  Physical-address auditing remains a separate diagnostic.

## Opportunity and live obligations

The preceding catalog has actual application/handoff evidence. This merge
preserves every existing evidence field on the frozen inputs; the added
`uncompiled_root_events` counter is zero. It brings the source branch's
training/selection tools but does not silently retrain these workloads or
claim that an unused closure removed runtime work.

Typed original operations still prove lifetimes, Entry projection, eligible
Unit membership and local constructor effects. A scheduled switch may reuse
completed results only within those proofs. Residual enumeration, late union,
visibility, generations, ordered mutable effects and source error prefixes
remain live obligations. Template wiring is shared; no second binding graph or
per-producer internal consumer list is added.

An important remaining integration limit: `local_jobs_supported()` excludes
the composed ownership/local-union modes. Thus the optional completed-owner
compression mode does **not** automatically gain the constructor worker path.
The default parallel configuration uses the merged row/index representation;
optional physical ownership compression and Unit specialization keep their
existing explicit configuration and fallbacks. Expanding concurrent completion
under that ownership needs a separate proof and implementation.

The old Run-queue report also attributed extra execution frames to disabled
direct/iterative completion without evidence. That paragraph is corrected:
matched/closed completion counts were unchanged and direct Ripsat completions
were zero. Ordinary constructor-prefix reuse under a pending queue remains
the next specific path to inspect; this merge does not claim to fix it.

## Actual work against the current branch

Same frozen programs, catalogs, runtime flags and four workers, one execution
per workload. `results.json` contains both controls and all added costs.

| Work, control → merged | sum-bits | Raytrace |
| --- | ---: | ---: |
| RHS dispatch regions | 135 → 135 | 6,599 → 6,604 |
| Source execution frames | 5,195 → 5,195 | 1,024,706 → 1,024,593 |
| Ordinary key lookups | 12,910 → 12,910 | 3,825,375 → 3,825,417 |
| Forward dependency headers | 4,045 → 0 | 1,034,514 → 0 |
| Live reverse edges | 10,262 → 10,262 | 2,796,816 → 2,796,816 |
| Subscription value visits | 18,239 → 21,423 | 5,764,142 → 6,341,718 |
| Unit candidate capacity bytes | 130,480 → 71,720 | 46,892,416 → 25,702,832 |
| Unit registration capacity bytes | 19,904 → 19,680 | 12,982,320 → 14,823,640 |
| Added hash-bucket candidate visits | 46 | 43,157 |
| Added pinned old-row handles | 18 | 28,198 |

Deleting duplicate storage trades against more field reads and candidate
preparation. The two Unit capacity rows have distinct scopes and must not be
treated as total allocation/peak-heap figures. Event fragmentation and temporary
capacity can depend on worker completion order. There is no established speedup
or resolution of the preceding slowdown here; full timing remains at the
agreed five-implementation checkpoint.

## Validation and reproduction

201 runtime unit tests and 181 integration tests passed. Separate forced
hash/Bloom-collision checks cover worker construction, registration and rollback.
All-features, sparse-only, legacy and merged compiler examples compile.
Incoming integration coverage includes completed-owner retirement, parent
lifetimes, late-input matched handoffs, union, deletion and selected Unit facts.
README compile/run and a one-repeat bench pass as smoke checks.

The frozen workloads have exact final-state hashes, all 1,428 / 16,883 ordered
Run summaries, logical effects, live reverse occupancy and existing iterative
evidence. This is not a claim that every intermediate graph was exported: the
targeted integration tests separately check per-Run graphs and binding order.
The reviewed native sum-bits choice validator returns `pass`, and its saved CPU
export hash equals the freshly merged runtime export. Raytrace is differential
validation against `a011785f`, not a newly extended native semantic contract.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-bake-merge/run.py out/cell-run-queue FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-bake-merge/check.py out/cell-run-queue FRESH_OUTPUT RESULTS.json
```

Use the successful `validation.json` / `readme-checks.json` commands recorded in
`results.json`. One initial debug link ran out of disk space; after removing
regenerable build artifacts, the same check and all remaining checks passed.
Sources, frozen binaries, logs and exports remain under ignored local output.
Exports may be losslessly gzipped; the checker hashes decompressed contents.
