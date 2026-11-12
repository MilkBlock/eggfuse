# Construct fresh local Cell suffixes without global interning

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `4088086e`. This extends opt-in `--cell-execution-grain`; it does not
implement independent parked scheduling or concurrent graph registration.

## Opportunity and compiled proof

The preceding actual Raytrace execution still resolves 2,006,052 constructor
boundaries on the coordinator. Query-time preparation can only return existing
constructors; a query miss does not prove absence at source commit time. It is
therefore insufficient to prepare more speculative lookups or queue the already
eliminated scalar suffix work.

One source-time resolution can establish a stronger fact. If `F(a)` genuinely
creates a fresh result `u`, no earlier external constructor key can contain `u`.
Until a shared effect, external birth or union interferes, `G(u)` needs only exact
comparison with preceding local `G` sites after the birth of `u`:

```text
source interning: F(a) -> genuinely new u
worker:           G(u) -> v; H(v) -> w
source:           register those actual rows in the original order
                  continue at Set / Union / another unresolved dependency
```

`cell_births::Plan` derives constructor regions, producer anchors, canonical
static aliases and per-operator candidate ranges from the existing typed Cell
definition. Operator-site lists are shared, rather than copied for each step.
A compiled continuation mask suppresses freshness maintenance where no later
operation can use it. This is additional source-derived Bake information; it
does not introduce a runtime fact graph or producer-to-consumer lists.

The ordinary source constructor remains responsible for the first unresolved
result. The local path requires its actual returned row to contain this Cell's
fresh implicit ID and checks that the ID is still a union-find root. Merely
owning a fact does not prove freshness: a Set/alias may install an old result.
Freshness uses validated source SSA and the original Cell identity allocator;
it does not cover external callers fabricating references to future Cell IDs.
The existing birth and union counters delimit the exclusion window. New local
rows extend it; external mutations invalidate it and leave the original
unfinished operation live.

The candidate key is exact, including every scalar and Eq field. A digest or
matching operator name is never a proof. A repeated local key returns its actual
earlier witness. A new key uses the original source Cell/destination identity,
computes its hash once, and constructs the final `RowFields` allocation once.
The coordinator adopts that allocation directly; it does not repeat the lookup,
key construction, hash or row copy. Subscription/index/change registration is
still ordered and retained. Worker construction is not yet committed mutation.

The worker writes reused values and demanded receipts into the original Cell
slots and `Effects` layout. Fresh implicit results need no extra explicit value
write. An `EffectWriter` borrows the existing immutable layout and uniquely owned
arrays; its `Rc` owner remains on the coordinator. The pending list contains only
actual new rows awaiting registration, not a second binding or full RHS log.

## Equivalence and live boundaries

- Regions contain only eligible virtual constructors, Copies and proven static
  aliases. Scalar computation, mutable effects, Union, Hide and failures cut
  the proof. The path stops before an existing compiled history handoff.
- Input rewrites, aliased/parent-projected constructor destinations and missing
  operands retain ordinary execution. The first key can use the ordinary parent
  projection reader; its actual values move into the worker once.
- Canonical interning is currently required. Stable-port, union-digest,
  ownership/local-union backends, structural-depth and keeper-proof paths remain
  outside this takeover because their birth-time behavior needs further proof.
- No shared effect occurs during the synchronous worker piece. Source registration
  then commits the same new facts in the same order. The source position advances
  only after registration. Panic/Hide and subsequent effects retain their order.
- Query snapshots, accepted bindings, winner/delta rules, actual returned results,
  repair and Run publication remain authoritative. A new result cannot be made
  visible to a later Run merely because worker preparation completed.

At a source position, exact local comparison yields the same answer as global
interning: all possible earlier keys containing the fresh input are in the
compiled local range. All other candidates predate that input. The proof is
limited to the admitted source-ordered region; it does not justify executing
several Cells concurrently against a changing graph.

## Costs and remaining scheduling problem

The initial implementation's actual Raytrace execution built 139,448 local rows
in 76,904 pieces, averaging about 1.81 constructors per piece. It made 77,070
pending-vector growths. The final pending storage keeps four row handles inline;
larger pieces still spill and report their heap growth. Row allocations remain
necessary; only their construction moves to the worker.

The final result file records **all admission/continuation probes**, exact local
comparison work, operand reads, hashes/row fields, pending and slot growth, plan
storage, the larger execution header, worker batches and source waiting time.
Pending heap bytes mean cumulative capacity added, not peak memory. The inline
pending object exists per executing piece, not per stored Cell.

The equal-weight work reader charges new probes and worker operations needed to
prepare storage, without granting extra credit for coverage, committed-row or
worker-operation totals. Some transferred operations, such as row construction,
were not separately instrumented in the control; their new charges make this a
conservative, uncalibrated proxy, not a complete before/after CPU-work model.
No speedup follows from its value or from fewer global queries alone.

[results.json](results.json) records the final executable, program and state
hashes. Final states are byte-identical, all 1,428 / 16,883 ordered Run summaries
match, and native sum-bits acceptance is `pass`. Logical effects, LHS query work,
repair and publication counters are unchanged.

| Work/storage | sum-bits | Raytrace |
|---|---:|---:|
| Global lookup calls, before → after | 14,579 → 14,054 | 4,176,557 → 4,037,109 |
| Actual local rows built, then source registered | 525 | 139,448 |
| Coordinator constructor boundaries, before → after | 8,837 → 8,288 | 2,006,052 → 1,866,039 |
| Plan eligibility checks | 20,215 | 4,969,038 |
| Local resumption checks | 668 | 156,535 |
| Freshness-window checks | 1,423 | 399,977 |
| Exact candidate probes / field comparisons | 48 / 75 | 100,948 / 114,022 |
| Source / worker operand reads | 593 / 451 | 153,293 / 127,654 |
| Worker batches | 299 | 76,904 |
| Accumulated synchronous worker wait, diagnostic | 2.13 ms | 507.25 ms |
| Pending-list heap growths, initial → final | 309 → 10 | 77,070 → 166 |
| Final cumulative pending capacity added | 4,480 B | 780,160 B |
| Compiled local plan payload | 119,838 B | 3,327,560 B |
| Net saved equally weighted operations | -27,249 | -7,015,059 |

Some eliminated constructor dispatches were already static aliases, so the
boundary reduction exceeds the removed global queries. These are not added
together as independent savings. The final compiled mask reduces initial
window checks from 6,719 / 2,108,549, but its own applicability checks above
remain real work. The large admission count and short pieces are unresolved
costs; the negative proxy is not presented as improvement.

The Instance header stays 152 bytes; the execution owner grows 456 → 488 bytes
for its exclusion window. The pending object is 168 bytes per active piece,
with 40-byte row handles and four inline entries. The local path adds no explicit
value writes or slot growth on these two workloads. The dynamic-equal-key fixture
does exercise reuse and exports the actual earlier witness. Total compiled
execution storage grows 515,512 → 677,254 and 2,447,928 → 5,817,392 bytes, including
plan headers as well as payload. None of these counts establishes a speedup.

The coordinator still waits in `pool.install`, then registers rows. Public Cell
and parent borrows prevent overlapping arbitrary graph writes. The next required
takeover is a ready-owner batch with a stable ownership/read contract, so a
parked Cell releases its worker and another useful Cell can run. Simply starting
later bindings early is unsafe: their start paths may already commit effects or
allocate source identities. This feature does not solve that problem.

## Validation and reproduction

[check.py](check.py) checks exact final graphs, all ordered Run summaries, unchanged
logical effects, query totals, maintenance and publication work. It also proves
that removed global lookups equal completed local constructor operations. Per-worker
assignment can vary; the checker compares conserved total work. Targeted runtime
and compiler tests cover each Run state and binding, including actual foreign
reuse, dynamic equal keys, later Entry consumption, external births/unions, mutable
cuts, partial existing prefixes and failure after earlier committed rows.

Native sum-bits uses the unchanged reviewed choice validator. Raytrace is exact
regression against the control, not an expanded native equivalence contract.
Programs and saved native exports are those of
[the preceding checkpoint](../cell-scalar-boundaries/README.md). Raw evidence lives
under ignored `out/cell-local-births`; `initial` preserves the first pending-vector
execution. Freeze the feature executable before README default builds.

This is the third implementation since the last five-change timing checkpoint.
Complete workload runs here measure work and semantics; no new timing campaign
or throughput improvement is claimed. The required README repeat-1 bench is a
smoke check only.

Validation includes 133 runtime tests, 102 compiler/integration tests with
forced hash/Sieve collisions, all-features/no-default-features checks and the
README compile/run/repeat-1 bench smoke. Only rebuildable runtime/compiler Cargo
products were cleaned before the README build; frozen controls and evidence
were preserved.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-local-births/check.py ROOT PRIOR RESULTS.json
cargo cell-compile --case sum-bits --output ROOT/readme-program
cargo cell-run --program ROOT/readme-program/program.json --output ROOT/readme-run
cargo cell-bench --program ROOT/readme-program/program.json --repeat 1
```
