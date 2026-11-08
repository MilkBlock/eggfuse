# Runtime repair as executable Cell templates

This experiment extends `ac9d0cab` on the **standalone Cell CPU runtime**.
It does not modify or time native egglog. Focused programs also run against
native egglog as a semantic oracle.

## Opportunity and live obligations

The preceding 208-unit sum-bits and 316-unit Raytrace catalogs still performed
1,496 / 479,589 dependency repairs with result-port propagation enabled.
Sharing Entry ownership left those counts unchanged, and four tested ordinary
continuation additions per application failed the measured-work gate.

The new opportunity is invalidation of an already decoded scalar constructor
body after a committed equality changes a key port. Its complete port layout
is statically known. Keeping that body canonical can discharge later recipe
decoding, including reads by other exact-key candidates. The body persists
across source Runs; no future equality is assumed to hold.

Remaining obligations include exact whole-key equality, original collision
survivor order, delayed union commitment, hidden-state propagation, receipt
forwarding, retirement, reverse subscriptions, and source Run publication
barriers. Functions, custom merges and container keys keep residual repair.

## What is executable and shared

`--repair-cells` enables a checked catalog derived from table schemas. Each
schema has key-port and result-port blocks, their dataflow composition, an
ordinary `Template` containing `Op::Union`, and an exact-key completion block.
Synthetic typed `Rule` queries use the same `Block` lowering as source entries.
Both execute the same argument binder and result checker. `Block::then`
substitutes output ports into the next block, avoiding an intermediate row or
variable map.

Tables with identical schemas bind the same reference-counted shape. Class
and row IDs are runtime inputs; they never appear in template descriptors.
Bake registers source continuation units and repair units together in the
existing native Cell egraph. Sharing and composition describe executable
blocks, rather than retrospective trace labels.

1. An actual union commits to connectivity, then supplies displaced/current
   roots and a cached canonical constructor body to the delta Cell.
2. Its composed block replaces affected ports with copy-on-write. A result-only
   singleton may publish immediately if no earlier key repair is pending.
3. A key change retains the canonical body and enters the original ordered dirty
   queue. The completion Cell hashes and compares the entire key, preserving
   candidate order and skipping only itself.
4. A collision executes the template's actual `Op::Union`. It enqueues a request;
   it is not yet a committed equality. A checked publication capability forwards
   and retires the duplicate, or reindexes and publishes a vacant key. The next
   committed union activates further delta Cells through reverse incidences.

For covered bodies the old cache invalidation and subsequent recipe decoding
are removed. The exact-key result is consumed directly; no second legacy lookup
follows a successful Cell. Residual and Cell paths share the terminal publication
kernel. Its refactor also removes the old temporary bucket copy from the residual
path; timing includes the parent binary and a same-binary control to distinguish
that change from Cell activation.

There is no all-pairs application join or additional equality-closure graph.
Union-find, the interning directory, reverse incidences, ordered dirty queue and
Run publication machinery remain. Current composition is within a typed repair
entry. Arbitrary repair-to-source-RHS compositions and automatic fusion of
successive union waves are **not implemented**. This is the first scalar
constructor family, not elimination of all rebuild maintenance.

## Admission and credit

`bake-repair` profiles actual executions, then compares the current selection
against bounded candidate selections from the identical initial state. The
complete family is one proposal; observed high-frequency singleton shapes are
additional proposals. Whole-family credit is measured directly, never obtained
by adding independent singleton credits. At most one positive selection wins
each round. An empty accepted selection disables Cell dispatch and preserves
the result-port backend even with `--repair-cells`.

Every replay must preserve final graph, semantic schedule, ordered RHS inputs,
effective function writes and continuation resumes. The existing measured-work
ledger now also counts actual recipe decode calls/ports, old result-port
attempts/checks/copies, and repair Cell attempts, matching/effect instructions,
port writes and row copies. Failed dispatch is charged. A Cell hit or union
request receives no intrinsic reward. Each observed operation has weight one;
this is neither a complete hardware model nor calibrated latency. Compilation
and replay/export-hashing time are recorded separately.

The full application audit additionally compares normalized Spine traces, with
Entry publication ownership both disabled and enabled. Timings use a normal
executable without audit instrumentation. Builds and training do not overlap
with timing runs; background workstation load remains uncontrolled.

## Results

Both applications have 241 eligible constructor tables and 178 distinct typed
schemas, represented by 890 template nodes alongside the existing 208 / 316
source units. Only 33 / 41 shapes execute on these workloads. These are template
catalog counts, not allocated runtime frames or committed mutations.

All six application lanes (control, cells, cells plus Entry ownership for each
case) pass final-state, schedule, ordered RHS, effective-write, resume and
normalized-Spine comparisons. The repair counts remain **1,496 / 479,589**.
Within those repairs, 1,046 / 224,478 constructor key completions execute through
templates; other dependencies retain residual repair. Templates issue 844 /
161,769 collision union requests. Actual committed unions remain independently
counted by the existing runtime, and are unchanged.

| Actual work, control → all cells | sum-bits | Raytrace |
|---|---:|---:|
| Constructor recipe redecodes | 1,890 → 0 | 386,247 → 0 |
| Ports rebuilt by those decodes | 5,859 → 0 | 1,179,030 → 0 |
| Equality-delta Cell executions | 0 → 1,988 | 0 → 430,871 |
| Cell matching instructions | 0 → 7,490 | 0 → 1,669,032 |
| Cell effect instructions | 0 → 1,890 | 0 → 386,247 |
| New cache port writes | 0 → 2,098 | 0 → 457,480 |
| Copy-on-write rows, old ports / cells | 530 / 1,154 | 140,973 / 301,310 |

Zero recipe redecodes does **not** mean zero row reads or zero global index
maintenance. In particular, the graph's existing `decoded_rows` counter measures
other materializations and is distinct from the new `fact_decode_calls` and
`fact_decode_ports` counters.

Bake tests the whole family and two observed singleton proposals per case:

| Case | Selected shapes in proposal | Net observed operations saved |
|---|---|---:|
| sum-bits | All 178 | −580 |
| sum-bits | 54 | −1,601 |
| sum-bits | 27 | −1,948 |
| Raytrace | All 178 | −290,907 |
| Raytrace | 124 | −481,929 |
| Raytrace | 5 | −382,375 |

All six candidates are rejected. Each search stops at its three-trial budget,
with 176 singleton proposals untried, including the zero-frequency tail. This
is not a convergence result or evidence that every subset is unprofitable.
The accepted repair selection is empty; source catalogs stay at 208 / 316 units.
`credit.json` retains every counter delta and complete-replay audit digest.
No held-out generalization is claimed.

After one warmup per lane, inference uses 31 sum-bits samples and seven Raytrace
samples, interleaved across parent, same-binary control and all-cell lanes:

| Case / lane | Median inference | Median peak RSS through inference |
|---|---:|---:|
| sum-bits / parent | 21.139 ms | 167.578 MiB |
| sum-bits / control | 21.200 ms | 169.078 MiB |
| sum-bits / cells | 21.547 ms | 169.078 MiB |
| Raytrace / parent | 7.896 s | 1,875.703 MiB |
| Raytrace / control | 7.943 s | 1,860.938 MiB |
| Raytrace / cells | 8.093 s | 1,865.281 MiB |

There is **no demonstrated application speedup**. Cell/control median inference
increases 1.64% / 1.88%; within-round paired medians increase 1.86% / 0.56%.
Raytrace's control and cell ranges overlap (7.864–8.102 s / 7.915–8.124 s).
Its repair phase increases from 547.086 to 584.014 ms; sum-bits increases from
1.347 to 1.496 ms. These are descriptive measurements on a shared workstation,
not statistical confidence bounds. The entire per-sample record and executable
hashes are in `timings-sum.json` and `timings-raytrace.json`.

The useful outcome is the executable representation and elimination of a
specific old path. Generic instruction dispatch, port materialization and
additional copy-on-write now have visible costs. The experiment does not
establish that keeping more cells, or an inherently sparse input egraph, alone
will make this implementation faster. Compiling these checked blocks into
cheaper kernels and composing consecutive equality deltas remain separate work.
The feature stays opt-in.

## Reproduction and checks

Use the frozen input catalogs documented in `../entry-publications/README.md`.
The `parent` lane is its archived `ac9d0cab` executable, with the same normal
build features. Rebuild it at that commit when the archive is unavailable.
All paths below are relative to the repository root; output directories must
be new. Build and save normal, audit and learner executables separately:

```sh
mkdir -p out/repair-cells
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cp target/release/eggfuse-cell-runtime out/repair-cells/runtime
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes
cp target/release/eggfuse-cell-runtime out/repair-cells/audit-runtime
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake
cp target/release/eggfuse-cell-compiler out/repair-cells/compiler

python3 benchmarks/result-port-repair/audit.py out/repair-cells/audit-runtime benchmarks/repair-cells/audit-manifest.json out/repair-cells/audit
out/repair-cells/compiler bake-repair --program out/producer-receipts/learn-sum-bits/program.json --output out/repair-cells/learn-sum --rounds 1 --trial-limit 3
out/repair-cells/compiler bake-repair --program out/producer-receipts/indexed-audit-learn-raytrace/program.json --output out/repair-cells/learn-raytrace --rounds 1 --trial-limit 3
python3 benchmarks/leaf-completion/measure.py benchmarks/repair-cells/timing-sum-bits-manifest.json out/repair-cells/timing-sum --repeat 31
python3 benchmarks/leaf-completion/measure.py benchmarks/repair-cells/timing-raytrace-manifest.json out/repair-cells/timing-raytrace --repeat 7

python3 benchmarks/repair-cells/collect.py out/repair-cells benchmarks/repair-cells
python3 benchmarks/result-port-repair/collect.py out/repair-cells/timing-sum/samples.json benchmarks/repair-cells/timings-sum.json
python3 benchmarks/result-port-repair/collect.py out/repair-cells/timing-raytrace/samples.json benchmarks/repair-cells/timings-raytrace.json
```

The audit and measurement helpers hash each generated state export before
removing that export. No binary streams, executable archives or build products
are tracked. Validation includes the full all-feature workspace suite, focused
non-sparse repair/query tests, and a runtime build without default features.
New tests cover multiport completion over several Runs, derived union chains,
batched unions, ordered custom merges, deletion/subsumption/reinsertion,
container fallback, duplicate initial buckets, allocation renaming, template
corruption, empty selections, shared registration and measured admission.

Final checks: **187 workspace tests pass**, with four pre-existing ignored tests;
**15 focused non-sparse tests pass**; the no-default-features runtime check passes.
The `egglog-baseline` tag remains `62ae6baa5539af4468a8f1a94d6e108de4dcd2df`.
