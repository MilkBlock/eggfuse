# EggFuse: Exploiting Locality in E-Graphs

EggFuse is an experimental Rust compiler and standalone CPU executor for egglog programs. It explores how related rule applications can share query work, execution state, and storage across scheduled runs.

## Architecture

A **Cell template** describes typed slots, query atoms, and an ordered instruction block (`Copy`, `Let`, `Set`, `Union`, `Hide`, `Panic`). Its instances hold concrete bindings and actual result witnesses. **Shared Entry** projects those existing slots into later queries. **Iterative Bake** uses observed applications and compiler proofs to compose reusable Cells and eliminate covered queries, handoffs, and maintenance.

Original Run boundaries, effect ordering, equality repair, and residual matching remain authoritative. A Cell is not an e-class or an automatic guarantee of conflict-free parallel execution. Full egglog compatibility is still a work in progress.

## This branch

This branch develops **Cell-oriented parallel execution**: workers borrow Entry ranges, continue queries, and perform eligible completion work. Table completion events release dependent conditions in the same pool. Ordered effects and visibility still constrain execution; stable end-to-end parallel speedup has not been established.

Recent checkpoints: [shared completion slots](benchmarks/cell-completion-slots/README.md), [producer-owned constructor registration](benchmarks/cell-fused-registration/README.md), [independent constructor registration](benchmarks/cell-independent-registration/README.md), [continuous worker Cell runs](benchmarks/cell-worker-runs/README.md), [worker constructor roots](benchmarks/cell-root-births/README.md), [in-place Cell fact leases](benchmarks/cell-fact-lease/README.md), [per-Cell registration return](benchmarks/cell-local-registration/README.md), [registration completion events](benchmarks/cell-registration-events/README.md), [stable Unit reservations](benchmarks/cell-unit-reservations/README.md), [constructor registration owners](benchmarks/cell-constructor-registry/README.md), [task completion payload](benchmarks/cell-event-payload/README.md), [rule-local Entry coverage](benchmarks/cell-query-coverage/README.md), [borrowed Entry ranges](benchmarks/cell-selected-entries/README.md), [in-place condition state](benchmarks/cell-condition-borrows/README.md), and [table completion events](benchmarks/cell-table-events/README.md).

It also integrates [cross-stage completion and structural compression](benchmarks/cell-structural-compression/README.md), with [merge validation and integration limits](benchmarks/cell-bake-merge/README.md). Shared-owner storage and selected Unit specialization remain opt-in; storage measurements do not establish a parallel speedup.

The [structural Bake refresh](benchmarks/cell-bake-refresh/README.md) adds pooled catalogs, a shared compiled transition directory and completed scalar projections, while retaining the parallel scheduler.

The latest [root continuation checkpoint](benchmarks/cell-root-continuation/README.md) consumes existing constructor results during Cell admission, removing repeated parameter preparation while retaining exact lookup and source ordering.

[Prepared Cell continuation](benchmarks/cell-prepared-continuation/README.md) consumes valid worker witnesses before conflict/key preparation and releases completed instances that have no publication responsibility.

## Quick start

Requires Rust/Cargo and the vendored dependencies in this repository. From the repository root, use fresh output directories:

```sh
cargo cell-compile --case sum-bits --output out/sum-bits
cargo cell-run --program out/sum-bits/program.json --output out/run
cargo cell-bench --program out/sum-bits/program.json --repeat 5
```

Use `--case raytrace` for the larger example, or `--source app.egg` to compile a supported custom program. See the [compiler documentation](tools/cell-compiler/README.md) for more options.

## eggcc comparison

![Single-thread eggcc inference: EggFuse versus native egglog 2.0 and 3.0](docs/images/eggcc-comparison.png)

Figure 7 from the [working paper source](https://github.com/MilkBlock/eggfuse/tree/codex/primitive-compatibility-paper/paper): 96 workloads × 3 captured pass inputs on one Apple M3 Max, one runtime thread. Totals are sums of per-input medians: **140.860 s** (egglog 2.0), **97.805 s** (egglog 3.0), and **53.789 s** (EggFuse). The two same-machine batches repeat the unchanged 2.0 binary as a control; its aggregate time differs by 0.37%.

These are historical frozen-pass execution results for EggFuse `8450e627`, **not current-branch or multithreaded performance**. They exclude 727.05 s of offline preparation; memory use is higher, and suite-wide semantic equivalence has not been established. The image is rendered directly from the paper, without changing its data. The paper is an AI-generated working draft under revision; implementation and experiments are extensively AI-assisted.

## Development

- [Parallel execution](https://github.com/MilkBlock/eggfuse/tree/codex/cell-parallel-admission)
- [Structural compression and cross-stage completion](https://github.com/MilkBlock/eggfuse/tree/codex/cell-structural-compression)

See [AGENTS.md](AGENTS.md) for development and semantic acceptance requirements. The reviewed sum-bits contract uses [choice diagnosis](benchmarks/marker-handoff/choice-diagnosis.md); final-state checks do not replace Run-boundary validation.
