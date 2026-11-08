# Checked cross-template port composition

This opt-in experiment extends `347e4aa3` in the **standalone Cell CPU**.
It is not an optimization of the native egglog runtime. The frozen sum-bits
catalog has 208 learned units; this iteration does not learn a new catalog,
rerun Raytrace, or remeasure the workload's union frequency.

**This candidate fails acceleration admission.** In 31 interleaved sum-bits
samples, inference is 13.5% slower than the ordinary fast baseline and full
process wall time is 23.8% slower. Cross-template bindings shrink, but the new
composition and instance-maintenance costs outweigh the benefit on this workload.
The backend remains opt-in; structural compression is not accepted as a speedup.

The previous execution already identified the opportunity: cross-stage consumers
kept distinct template-symbol bindings even when a checked Entry provided their
inputs directly from an owned producer. Ordinary typed propagation inspected
3,773 fields; the symbolic path inspected 2,098, but also created 8,909 bindings
and performed 12,430 attachment/retirement binding reads. Those maintenance
costs could outweigh the saved inspections. Exact congruence key probes and
ordered publication remain live obligations.

## Representation and obligations

`bake-cell-ownership` emits `eggfuse-ownership-markers/v3`. The artifact stores
port programs once, marker-to-program references, query-column source mappings,
and up to 4,096 composition recipes. The loader independently rederives the
complete descriptor; a recomputed checksum cannot authorize altered substitutions.

An Entry passes its checked query receipts to the RHS. Only the first actual
owned birth resolves these receipts into a composition. An all-hit RHS does not
resolve composition sources. A consumer input can then address its producer's
existing symbolic slot, sharing its binding and immutable repair expression.
Runtime eclass IDs do not identify the shared recipe. They remain values at its
instance boundary, and actual matching/committed equality supplies the proof.

For example, `G(F(x)) -> H(G(F(x))) -> Seen(H(...))` can extend one component
through three scheduled stages. The intermediate ports share symbols across
frames without adding root-directory subscriptions. The two-chain fixture keeps
exactly the two imported external input bindings throughout these stages.

This is bounded composition, not arbitrary merging of existing components.
Each component has at most 16 frames. Inputs from another component, overflow,
or an unavailable owned source retain external notifications. Deleted producer
frame addresses survive while a component still has live facts, so a late union
of the producer's result can reach its downstream consumers. Future explicit
union instructions are never assumed equal in advance.

The descriptor bakes compact one-hop recipes. Runtime caches deeper recipes
and materializes a dispatch shape at its first actual use. Port maps, untouched
slices, and existing column arrays share their allocations across shapes. Only
modified slices copy instruction handles. These cold builds are charged during
execution; this implementation does not claim that all rebuild work is baked.

On committed equality, already ordered slices feed a reusable heap merge.
Contributions to the same fact combine before its key/result decision. There is
no per-union temporary fact map, owner set, or destination-column sort/dedup.
The original ordering of exact key completion and result publication is preserved.
Lifetime owners now keep counts rather than redundant sets of member facts.
Full inventory validation reconstructs these counts outside inference.

External root-to-composed-symbol membership, binding lifetime counts, component
frame addresses, and the ordered pending-key queue still exist. These are
reported explicitly. Query candidate generation traverses the same expressions;
the sum-bits execution does not exercise this candidate-domain route, so its
completeness is covered by focused tests rather than claimed application savings.

## Evidence and admission

`monitor.json` records every publication barrier and the comparison with the
previous symbolic-slice experiment. `audit.json` retains exact state, ordered RHS,
effective-write, resume, schedule, and normalized Spine hashes. The new path
matches the same-binary ordinary control and the committed predecessor audit.
Logical matches are not treated as committed mutations.

`timings.json` retains every normal-build sample. `admission.json` compares the
candidate with the ordinary fast baseline at `8fffff65`, using
`--repair-ports --entry-publications`, and separately with the same-binary control.
The deliberately conservative admission gate requires the upper 95% paired
bootstrap ratio to be below one for both inference and full process wall time.
One workload cannot establish a general speedup.

Loading/parsing/descriptor validation was previously outside the setup clock.
New reports include `load_seconds` and `load_setup_inference_seconds`.
The external process clock also covers startup, reports and export. The archived
baseline has no separate load clock; its setup time must not be presented as a
cold-start total. Neither diagnostic reports nor loading are silently omitted
from the process comparison.

`allocations.json` comes from a separate `allocation-metrics` executable using
the same mimalloc allocator. It counts successful allocation/free/reallocation
requests during `execute`, requested/released bytes, and peak live requested
bytes. Reallocation counts the new request and released old size even if the
pointer does not move. These are not physical allocator bytes or RSS, and exclude
loading, setup and export. Atomic metering is absent from timing executables.

Binding creations count logical records, not allocator calls. Substituted ports
count static substitutions selected for composition, not actual eliminated
allocations. `composition_shape_steps` counts instruction handles copied/appended
when a shape materializes; `composition_materializations` includes both baked and
new recipes. Heap growth counts capacity changes, not total allocation traffic.
The equal-weight work ledger charges the new operations and explicitly marks
its score as an unvalidated time proxy. It cannot admit a performance claim.

| sum-bits median | Fast baseline | Same-binary control | Composed |
|---|---:|---:|---:|
| Inference | 21.960 ms | 21.879 ms | 24.934 ms |
| Full process, including reports/export | 148.774 ms | 167.743 ms | 184.218 ms |
| Load + setup + inference | unavailable | 109.077 ms | 121.212 ms |
| Peak RSS through inference | 169.781 MiB | 169.547 MiB | 175.906 MiB |

Each measured process took less than 0.2 seconds. The bootstrap ratio intervals
against the fast baseline are 1.123–1.157 for inference and 1.216–1.251 for process
wall time. Relative to the same-binary control, inference regresses 14.0%.
Even the disabled control's process wall is 12.8% above the archived baseline:
this branch still prepares and reports composition descriptors unconditionally.
Its near-identical inference time does not erase that cold-process regression.

| Structural diagnosis | Previous symbolic slices | Composed |
|---|---:|---:|
| Live external symbol memberships | 4,922 | 3,434 |
| Binding records created | 8,909 | 6,873 |
| Live binding records | 6,976 | 5,488 |
| Binding attachment/retirement reads | 12,430 | 12,430 |
| Typed propagation field checks | 2,098 | 2,098 |
| Exact key completions | 1,046 | 1,046 |
| Result-only publications | 878 | 878 |

The ordinary control still checks 3,773 fields and performs 1,046 exact key
probes. The additional boundary reduction does not reduce this required repair
work further. New execution costs include 6,256 checked source reads, 1,790
composition requests, 1,348 shape materializations and 21,618 copied/appended
instruction handles. Only 178 requests hit baked recipes; 1,306 need new recipe
keys. Shapes depend on accumulated component context, so removing root bindings
does not yet provide broad reusable cross-stage compositions.

The reusable dispatcher performs 2,816 heap comparisons and four scratch
capacity growths, retaining 544 scratch bytes. The allocator diagnostic nevertheless
records **116,981 → 174,940 allocation calls**, **18,727 → 25,409 reallocations**,
and **27,015,078 → 31,460,554 requested bytes** from ordinary control to composed
execution. These total execution costs are why a boundary-count score is not
an adequate optimization objective. They do not isolate all extra allocations
to one function; per-site attribution would require further instrumentation.

The next architectural constraint is to reuse compositions without making each
receiver depend on the complete accumulated component shape, and to remove
duplicate instance bookkeeping. Cached shapes currently remain for the entire
execution; the 16-frame limit bounds each shape, not the number of cached shapes.
Widening composition coverage alone is therefore not an admitted improvement.

The workspace passes **210 tests**, with four preexisting ignored. All **17**
ownership tests pass with and without sparse cells; the no-default-feature build
also passes. Cases include cross-stage chains, foreign inputs, deleted origins,
dynamic aliases, capacity cuts, candidate completeness, corrupt descriptors and
unaltered source-order unions. A storage test proves that appending one receiver
does not copy the 199 unrelated slices in its producer.

## Reproduction

Use new output directories. The frozen catalog is produced by the
[producer-receipts experiment](../producer-receipts/README.md).
Rebuild the ordinary baseline at `8fffff65` if its archived executable is absent.
Build compiler and runtime separately: compiler feature unification changes
JSON object ordering, which would invalidate exact exported-file hash comparisons.
The release feature sets below keep audit and allocation instrumentation out of
timing. No published site or native egglog benchmark is involved.

```sh
mkdir -p out/ownership-composition
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test cell_ownership -j 2 -- --nocapture > out/ownership-composition/focused.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test cell_ownership -j 2
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake -j 2
cp target/release/eggfuse-cell-compiler out/ownership-composition/compiler-final
out/ownership-composition/compiler-final bake-cell-ownership --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-composition/baked-sum-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/ownership-composition/audit-runtime-final
python3 benchmarks/result-port-repair/audit.py out/ownership-composition/audit-runtime-final benchmarks/ownership-composition/audit-manifest.json out/ownership-composition/audit-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics -j 2
cp target/release/eggfuse-cell-runtime out/ownership-composition/runtime-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics -j 2
cp target/release/eggfuse-cell-runtime out/ownership-composition/allocation-runtime-final
out/ownership-composition/allocation-runtime-final --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-composition/allocation-control --repair-ports --entry-publications
out/ownership-composition/allocation-runtime-final --program out/ownership-composition/baked-sum-final/program.json --output out/ownership-composition/allocation-composed --cell-ownership
python3 benchmarks/leaf-completion/measure.py benchmarks/ownership-composition/timing-manifest.json out/ownership-composition/timing-final --repeat 31
python3 benchmarks/ownership-composition/collect.py out/ownership-composition benchmarks/ownership-composition
```
