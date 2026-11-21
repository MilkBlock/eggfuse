# A shared ordered effect program per source rule

This experiment runs the standalone Rust Cell CPU executor. After a source Run has sealed, verified and deduplicated its proposals, the existing scheduler visits rule groups in order. It still consumes the root recipe of each winning binding before executing its RHS. The experimental evaluator lowers the first encountered group of each rule to a reusable effect program *inside the timed RHS phase*. Every binding in the group receives the same immutable program. There are no speculative mutations or deferred commits.

* **Positions** compiles a successor position for each source operation and prefix counts of compiler-proved aliases. It jumps over lazy copies and previously certified omissions. Constructor prefix hits retain original source op numbers and receipts. A first miss reserves and promotes exactly the original physical Cell and resumes from the same source instruction. Hide can still stop a suffix after earlier effects have committed.
* **Wires** additionally substitutes the source of an immutable Copy directly into the using operand. The compiler excludes multiply defined, input, query, parent-projected and statically overridden slots. A binding which nevertheless supplies a materialized intermediate declines the wiring treatment. The stored Cell, its template, original op numbers and external port semantics remain unchanged. Audit reads each rewritten operand both ways before its source effect. The fault control substitutes a forged literal into the compiled stream and requires independent disagreement before applying that operation.
* **Single-function write microprogram** compiles a verified input/earlier result/literal source for every operand of an admitted pure arithmetic prefix and its final complete-key write. It works for multiple key columns and intermediate results. The existing sparse optional unary add projection has a narrower shape and is absent in the ordinary backend used here. The new path reserves the original Cell id, evaluates arithmetic with the native primitive semantics and reads the current function value through the ordinary merge. Only an effective change constructs and retains the original writer frame, including every computed result. A no-op avoids the transient header construction. Both arms have the same observable physical allocations. Parent-linked or unsupported bindings retain the ordinary writer.
* **Last-key receipt** remembers the most recent canonical tuple and function address only within its current rule group. A hit requires complete key, table, epoch, union and table generation equality. The original merge still consumes the *current* old value. The audit recomputes each reused physical index from the source table. Per-table counters separate saved probes from all writes.

The paired studies use frozen seed 1703, composed shared source headers and delayed arithmetic ports. An independent vanilla executor supplies the source oracle. Detailed checks compare the raw model stream, winners, source ordinals and parents, every physical Cell identity, ordered RHS and effective writes, actual Spine, union, schedule and final graph. Four rotated full resident samples follow warmup; the measured RHS interval includes block lowering on first use, reads, source mutations and per-binding ownership/Spine work. Setup, export and the separate detailed audit sit outside the resident interval. The static compiler and physical counters report the actual paths used.

## Full rule-group tape

| Source | Vanilla | Ordinary / positions / wires inference ms | Ordinary / positions / wires RHS ms | Skipped Copy dispatches | Rewired reads |
|---|---:|---:|---:|---:|---:|
| sum-bits | 21.82 | 33.20 / 33.25 / 34.51 | 6.63 / 6.87 / 7.14 | 4,133 | 3,930 |
| conjugate-gradient | 358.87 | 646.99 / 656.07 / 645.64 | 116.56 / 119.02 / 117.14 | 51,958 | 49,077 |
| 3mm | 935.78 | 1,979.37 / 1,978.99 / 2,008.86 | 318.85 / 323.38 / 326.31 | 141,270 | 132,208 |

The 3mm scheduler delivered 294,917 bindings in 6,377 rule groups. Of these, 293,504 bindings belonged to groups with at least two members. The compiled position cursor ran in 35,009 constructor prefixes and 164,187 dynamic suffixes. A promoted constructor can use both cursors, so those counts cannot be added as distinct source winners.

For example, eggcc rule 249 recognizes a loop-invariant constant. Its first two source instructions copy slots 9→12 and 2→13. Instruction 2 constructs Const(7,10,3)→14. Instruction 3 constructs lsr-inv(13,14,12)→15. The compiled tape dispatches the same instructions 2 and 3, resolving the latter operands directly as (2,14,9). Rule 249 alone accounts for 24,896 skipped Copy dispatches and 24,896 audited operand substitutions on 3mm. Across that program, 88,024 already-certified static omissions were charged in addition to the Copy count. The compiler saved interpreter operations but did not reduce constructor or actual source effect counts. Wires improved zero of four 3mm wall-clock pairs. [All three source/phase and physical proof records](results.json)

The first matrix deliberately compiles the same positions and wiring metadata in both treatments so that the difference between positions and wires measures activating an already constructed operand projection. Its comparison to the off arm charges both kinds of plan construction. The reported rewired field count counts crossed Copy definitions only once per using operand, even for longer copy chains. The per-rule arrays in the archived block data contain dispatched source operations, skipped non-alias Copy positions, pre-certified omissions, and used rewired operands, respectively.

## Direct ordered writes

Each cell below shows RHS / full resident inference medians in ms. The original six configurations were interleaved with vanilla in one executable-paired matrix. Every enabled block arm charges plan construction in the source RHS interval, including the unused position/wiring metadata in the writer-only control.

| Program | Vanilla full | Source | Wires | Write only | Wires + write | Plus last key | Plus absorption |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.60 | 6.54 / 32.71 | 6.77 / 32.98 | 6.83 / 33.12 | 6.84 / 32.97 | 7.00 / 33.72 | 6.71 / 32.63 |
| 3mm | 915.15 | 326.86 / 2,017.38 | 322.56 / 1,992.29 | 319.62 / 1,922.17 | 304.29 / 1,898.15 | 305.23 / 1,872.49 | 313.90 / 1,945.74 |

On 3mm the writer program handled 102,108 source updates, including 13,030 multi-key writes and 4,634 scalar prefix instructions. It handed 93,530 complete key tuples to the original stage mechanism. There were 63,908 effective changes. The other 38,200 avoided initializing an unused transient Cell header. The original backend already avoided retaining a physical Cell on these unchanged writes. Expr-size accounted for 85,083 calls and 52,915 effective changes. The consecutive-key receipt saved 764 index probes. Extending it with the compiler-certified old/min/max predicate skipped 38,200 native merge calls, and preserved the ordered function result, original frame ids and source receipt on every operation. Checking this predicate on every existing key raised the median relative to last-key alone. Full inference for wires + write and last-key beat off in all four 3mm pairs. The absorbed and writer-only arms each improved three of four. On sum-bits every writer arm improved two of four pairs. The fastest observed 3mm learned configuration still took 2.05 times vanilla. The measured first-use lowering cost for the last treatment was 1.44 ms on 3mm and 0.21 ms on sum-bits. [Raw paired observations and per-table physical work](writers.json) · [Pinned backend and binary hashes](manifest.json)

The [independent multi-key fixture](multi-key.egg) computes Score(k, group) from (x + 1) − 3 under the native min merge, then unions two formerly distinct keys and reruns the rule. Seven ordered writes executed fourteen arithmetic steps, two changed the graph, four reused an actual previous function address, and five were proved absorbed. Every intermediate, key, value, change, source Run and Cell ID agreed across all five modes. [Fixture evidence](fixture.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/ordered-effect-blocks
python "$d/build.py" "$EXP/block-base"
python "$d/study.py" "$EXP" "$EXP/block-base/session" "$EXP/block-study"
python "$d/build.py" "$EXP/block-writes" --writers
python "$d/study.py" "$EXP" "$EXP/block-writes/session" "$EXP/write-study" --cases sum-bits 3mm --writers
python "$d/fixture.py" "$EXP" "$EXP/block-writes/session" "$EXP/multi-key-fixture"
python "$d/archive.py" "$EXP/block-base" "$EXP/block-writes" "$EXP/block-study" "$EXP/write-study" "$EXP/multi-key-fixture" "$EXP/block-archive"
python "$d/verify.py" "$EXP/block-archive"
```
