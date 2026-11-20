# Neural row ownership on the native Rust Cell runtime

The frozen CPU actor sees the same live typed addresses and ordinary source schedule in each arm. Each source Run allows eight proposal slots. An emitted macro is one certificate, with a possible second ordered RHS only when its actual winning root publishes the named port. Each lane retains its own generated token across waves and Runs. The 1/2/4-row comparison ties the original two learned lane embeddings modulo two; it measures placement of a frozen recurrent policy. All graph and certificate verification, commits and exact residual stay in Rust.

| Admission | Operation before source verification |
|---|---|
| Free | Concurrent rows can choose the same address, including one chosen in an earlier wave. |
| Free once | Earlier-wave issues are excluded; simultaneous rows can still collide. |
| Static owner | Assign (typed leaf, stable physical source address) to exactly one row. An issued task stays reserved until the source Run ends. |
| Transfer | Apply static ownership first. An idle row may rescore unclaimed tasks from busy owners, preserving the source address, source version and Run. Transfer only on an active neural choice. |

No hidden match labels enter the live allocator. A transferred task may still fail verification. The Rust implementation is sequential; it cannot estimate a parallel lock-stall cost. The per-Run admission cost and any additional scans are charged in the native timing. Eight total slots are held fixed across 1×8, 2×4 and 4×2. The main 2×4 comparison follows.

| Program / seed | Free neural RHS | Free once | Static | Transfer | Transfer offers / winning roots | Exact / static ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits/1703 | 80 | 234 | 325 | 325 | 5 / 1 | 27.79 / 34.87 |
| sum-bits/1709 | 76 | 248 | 355 | 355 | 5 / 1 | 27.03 / 33.79 |
| dot-product/1703 | 65 | 181 | 260 | 260 | 4 / 1 | 23.75 / 31.15 |
| dot-product/1709 | 55 | 187 | 285 | 285 | 5 / 1 | 24.12 / 31.05 |
| gemm-bias-relu/1703 | 59 | 185 | 293 | 293 | 1 / 0 | 48.46 / 60.42 |
| gemm-bias-relu/1709 | 57 | 196 | 312 | 312 | 2 / 0 | 52.36 / 62.18 |
| stable-argmax/1703 | 58 | 164 | 236 | 236 | 0 / 0 | 27.81 / 33.42 |
| stable-argmax/1709 | 47 | 167 | 264 | 264 | 0 / 0 | 27.93 / 34.47 |

Each credited root or child wins one unique global RHS ordinal. All assisted arms match ordered RHS, effective writes, Spine, union events and the final source graph. Without residual search the primary four policies miss initialization in Run 1. The reported post-run omission diagnostic uses the union of roots that actually won in any paired arm as a lower bound on visible opportunities. It never credits that cross-arm union to any online model. Per-wave duplicates and slots are physical issue counts. Sparse handoffs with no extra wins can still consume scoring work. [Complete paired results](results.json)

Static ownership also prevents simultaneous duplicates. The free-once control isolates exclusion of already issued tasks across waves. At eight slots per source Run neither the current catalog nor an ideal single-binding chooser can meet a 98% full-source target. [Full-program addressability and target](../coverage-target/README.md)

## Reproduction

Build the native CLI with `--release --locked -p eggfuse-cell-runtime --features action-units,slot-transfer-audit`. Pass the corpus root, frozen Pass 3 reference root, native binary, `../action-granularity` weights directory and a new output directory to `study.py`. PyTorch only participates in offline training of the frozen actor. See [the action interface](../action-granularity/README.md) for how a typed parent can supply a second ordered RHS.

## Which conflicts actually occurred?

In sum-bits Run 98, free rows 0 and 1 both issued leaf 3, native address 80, macro 32 in wave zero. Row 0 won RHS #413; row 1 added no RHS. Static ownership also exposed a different case in Run 544. Slots 0 and 5 (different rows) selected native addresses 693 and 678 for rule 424. The two winning source bindings (#3367 and #3365) have the same shared Expr argument, Cell(3530463117323), but different Get indices, 2 and 0. Deduplicating by the shared value alone would lose a valid binding.

Macro 32’s root #413 supplied effect port 2 from Cell 541, op 2. Its child won #536 in Run 102. The independent pre-union source log in Run 106 also lists an external Get reader, Cell 578, op 1, whose key column 0 reads that result class. This establishes a real ancestor and a live outside-reader obligation. The policy emitted rule tasks; the two-row duplication above establishes a duplicate rule task, not a pair of independently proposed repair mutations. The search found a different-row, same-join-key winner in three of four workloads, and the macro/external-reader pattern in all four. [Check the recorded streams](witness_audit.py)
