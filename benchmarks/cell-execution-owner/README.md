# Own a Cell continuation across source effect boundaries

Scope: **standalone Cell CPU**, not native egglog. Control: `c7ad29e9`.
The full objective remains the [execution refactor](../../docs/CELL_EXECUTION_REFACTOR.md).

The preceding executions already prepared every observed later scalar segment
in the query invocation. They still executed 11,160 / 2,503,393 constructor
boundaries and 3,774 / 1,428,463 write boundaries in sum-bits / Raytrace. More
scalar dispatch cannot address that remaining work. Actual completed applications
and typed result-source/completion plans remain the input to subsequent Bake
composition; this checkpoint does not claim those shared effects are redundant.

The ordinary RHS continuation was bound to one `apply_owned` call: local
instruction cursors, a borrowed handoff slice, result storage and the started
Cursor had to survive in that stack frame. The runtime now returns an owned
`Execution` after existing specialized start/completion paths. It contains the
original Cursor, demanded query evidence, actual result buffer, immutable code
references and existing handoff inputs. It adds no binding, instruction list,
runtime fact graph or effect log. The graph Cell retains its slot allocation.

`advance_cell` stops at an unresolved source instruction, `resolve_cell_boundary`
executes it once, and `finish_cell` consumes the existing results into the
original completion/Entry path. `Cell.completed_prefix` is the sole instruction
position; duplicate loop positions and the worker-returned position are removed.
Repeated boundary observation does no lookup or effect. Stale deliveries cannot
replay an instruction. Failed execution cannot commit its suffix, and source Hide
termination remains distinct from successful completion. Specialized single
writes, direct completed transitions and complete constructor prefixes retain
their existing fast paths.

Per-execution accounting accumulates the actual work of each resolved boundary.
A global counter difference across a pause would incorrectly charge another
Cell's work to this one. The new counter reads and boundary checks are costs,
not speedup evidence. The source driver still resolves frontiers in order.

## Separate joint results from the shared publication arena

`begin_effects` previously moved the entire pending-publication buffer into every
executing RHS. Even joint history/publication frames, whose retained outputs
already have their own array, borrowed that global prefix for transient receipts.

Joint frames now borrow empty private scratch. Their original result array is
still transferred directly into history and Entry projection. Finishing or
aborting a joint frame returns only private scratch, without overwriting other
Cells' pending publications. One empty spare buffer reuses capacity, retaining
the larger spare if multiple owners return buffers. There is no per-producer
consumer list or copied result array. Ordinary output spans still use the old
arena and remain a scheduling boundary.

Admission retains the existing typed proof: permanent publication positions are
direct effect donors with history slots, and the current capture covers the
whole compiled joint layout. This proves that the retained outputs need no
position in the global publication arena. Actual returned witnesses, union
forwarding and publication visibility still retain their existing checks.

## Complete work and semantic verification

[check.py](check.py) produces [results.json](results.json) from frozen binaries
and saved complete exports. Final states match byte-for-byte, all 1,428 / 16,883
ordered Run summaries match, and checked graph, query, RHS, history and publication
work is unchanged. Per-worker chunk assignment differs; both distributions are
recorded and totals must agree. Wall-clock durations are excluded from work
equality. No semantic conditions were relaxed. Native sum-bits acceptance is
`pass`, exit 0. Raytrace is a relative check, not a native equivalence proof.

| Ownership work / additional storage | sum-bits | Raytrace |
|---|---:|---:|
| Shared arena borrows, before to after | 4,372 to 3,957 | 742,571 to 699,784 |
| Joint frames with independent scratch | 415 | 42,787 |
| Additional scratch growth events / bytes | 1 / 64 | 1 / 64 |
| Owned continuation header bytes | 448 | 448 |
| Instruction-position bytes in existing Cell | 8 | 8 |
| Remaining later scalar worker segments | 0 | 0 |

The 448-byte owner collects previously stack-local state. It is not a new heap
allocation per operation, nor a measurement of total memory saved or bytes moved
by compiled code. Slots, Rc/Arc storage and result buffers are outside that size.
An empty spare Vec adds a runtime header; capacity excludes allocator overhead.
Logical graph operations and result-copy counters have not decreased. This
change reduces exclusive ownership of unrelated publication storage. No new
throughput, utilization or stall improvement is claimed.

120 runtime unit tests and 47 selected forced-collision integration tests pass.
New cases retain slot addresses and receipts across returned boundaries, exclude
another write while paused from this Cell's work, reject stale deliveries, stop
suffix effects after Hide/Panic, and retain two independent joint result frames.
Existing cases cover Run states, winner/delta behavior, union, foreign reuse,
first-miss fallback, deletion/recreation and real Entry publication. The joint
integration checks that every joint frame uses independent scratch. All-feature
and no-default-feature checks pass. README compile/run/bench repeat 1 is a
minimal-path smoke check, not a performance campaign.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals --test joint_results
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-owner/check.py ROOT PRIOR_ROOT RESULTS.json
```

Use fresh directories and freeze the feature binary before default Cargo smoke
commands. Raw logs/exports are in ignored `out/cell-execution-owner`;
`out/cell-execution-deferred` is the frozen control.

## Remaining scheduling obligations

Owned control makes the continuation returnable, but not all graph/context
resources independently schedulable. `active_rhs` and its writer-origin hint
are single-owner; sealed-input trust is current-frame state; ownership Entry
rule/anchors/template still belong to the enclosing apply scope. Ordinary result
spans still borrow the global arena. These owners must move together before
multiple effectful Cells can be parked safely. Run query barriers, effect order
and required completion remain authoritative.

Bake must then compose the same execution/result layouts to remove proved
lookups, handoffs and publication. A D-to-U switch across Runs retains its entry
and liveness proof and scheduled visibility; storage reuse does not authorize
early execution of the later Run. Independent scheduling, broader local
completion and actual throughput/utilization gains remain unfinished.
