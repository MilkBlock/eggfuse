# Share unconditional Cell reads within a source Run

Baseline: `aeb059e0`. This is the standalone Cell CPU query executor, not native
egglog. Query workers remain opt-in. This change is the fifth implementation in
the current measurement batch. The [full speed checkpoint](checkpoint.md)
finds no demonstrated throughput win against the parent or historical fastest.

## Opportunity and proof

The saved query-sharing audit found 734 repeated cross-Entry reads in the first
128 Raytrace Runs, 679 with literal keys. Its physical-producer grouping found
all of those in the large initialization Cell. That grouping is not a proof
that other Cells cannot share work. Ordinary typed Cell instructions prove a
narrower and useful property: a first point read whose key is entirely literal
is independent of the Entry's binding. Empty keys qualify as well.

The compiler assigns identical `(table, literal key)` reads a common slot.
At the first activated Entry in a source Run, the coordinator reads the current
table once. Later Entries borrow that result and skip both key binding and the
physical query. A missing result rejects the Entry before queueing, grouping,
frame preparation or worker dispatch. A positive result retains the original
per-Entry result predicate, epoch/watermark handling and actual witness. A
cached error still travels through the existing source-ordered error reduction.
Later instructions are never hoisted across guards or prior reads.

The finite slot layout and touched-slot capacity are allocated at setup. There
is no runtime key cache, producer subscriber list or second copy of bindings.
Every Run clears activated slots, including all-negative Runs and worker errors.
No values, missing results or mutable reads are inherited across source Runs.
This therefore does not discharge a cross-Run validity obligation. Residual
query enumeration and existing history-based continuations keep their hosts.
The explicit `cell-query-sharing-audit` build observes unshared reads to discover
opportunities and is not a production timing build.

## Actual work against this branch

| Work, before → after | sum-bits | Raytrace first 128 Runs |
|---|---:|---:|
| Total key lookups | 18,692 → 18,633 | 88,737 → 87,361 |
| Worker-path physical reads | 2,082 → 2,023 | 21,229 → 19,853 |
| First-read Entry probes | 0 → 97 | 0 → 1,418 |
| Shared slot fills and clears, each | 0 → 38 | 0 → 42 |
| Reads reusing an initialized slot | 0 → 59 | 0 → 1,376 |
| First-read key fields bound | 5 → 2 | 235 → 1 |
| Queued Entries | 1,907 → 1,907 | 21,186 → 21,186 |
| Chunks | 203 → 203 | 417 → 417 |
| Winner comparisons | 3,045 → 3,045 | 22,073 → 22,073 |

The real workloads have no negative first reads on this path: no queue or
winner work was eliminated there. The new regression fixture exercises that
case, followed by insertion, changed mutable values and fresh source Entries.
Sharing spans physical Cells, so the saved physical-group audit was a lower
bound, not a cap on this optimization. The change removes 1.55% of total
Raytrace-prefix lookups, not half the workload. It is no general sparsity proof.

New per-Entry slot probes and positive result reads, per-Run slot writes/clears,
canonical key binding, compiled code growth and fixed storage are all exposed.
The work ledger charges these operations and charges the physical table lookup
only once. Hits and rejected Entries earn no additional synthetic credit.
Equal-weight work scores remain unsuitable as latency predictions. Detailed
memory and constructor work are retained in results.json. The original
coordinator RHS, publication, union and repair boundaries remain live.

## Validation and reproduction

95 runtime unit tests, 39 integration tests (query workers, query receipts,
Entry publication, stable ports), and five work-credit tests pass. The new
fixture checks every source Run's graph and ordered bindings with workers off,
inline one and pool four, both backends, small and large grains. Existing
fixtures cover forced collisions, unions, visibility loss, deletion/recreation,
residual enumeration and late inputs. A unit test verifies that a shared read
retains its result predicate without rebuilding the key and cannot move a later
read before a guard.

Saved canonical sum-bits, stable sum-bits, completed sum-bits and Raytrace-prefix
runs preserve their exact graph and ordered Run records. The completed catalog
retains all 165 direct completions. The required native sum-bits choice diagnosis
returns pass / 0. Minimal compilation and README compile/run/bench pass; the
single bench repetition is a smoke check, not a performance result.

Freeze the executable paths from Cargo JSON output before running:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_PREFIX 128 4 64 canonical
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-fixed-reads/semantic out/cell-fixed-reads/semantic-acceptance.json
python3 benchmarks/cell-fixed-reads/collect.py out/cell-fixed-reads benchmarks/cell-fixed-reads/results.json
```

Use the identical artifacts in cell-canonical-queries, and repeat with one
worker. The stable lane uses `--local-congruence`; the completed lane uses the
regenerated cell-completion-portability program. The collector reads saved
exports and launches no workloads. Generated binaries and exports stay ignored.
