# Bake the single-parent verification dataflow to Rust functions

The existing Rust Cell query compiler determines which anchor column, earlier result or literal supplies each point-read key, primitive operand, equality guard and RHS input. The interpreter consumes this list for every proposed parent. The new offline compiler emits a Rust function for each distinct instruction shape. Operand sources and instruction order become local expressions in that function. Source table identities, primitive names, literal values, slot numbers, witness atom indices and the original Run watermark come from the validated serving plan. Rules with the same shape share machine code even when they have different names or tables.

The bootstrap native executable accepts `--emit-verifiers PROGRAM.json OUTPUT.rs SHAPES.json`. It uses the same singleton planner and Query::compile as the executor. The measured executable then links the generated functions. Installation computes the descriptor from the actual serving program and binds a function only on an exact structural match. Expansion operands and unrecognized shapes retain the general verifier. Anchor identity, visibility, source version and repeated/literal anchor constraints are checked before entering either verifier. The generated body performs every original point read and primitive in source order, materializes the matching input slots and retains each source witness. Generated source contains fixed indexing and call kinds; no symbols from a workload become Rust source identifiers.

The donor is the static sum-bits Pass 3 program, with no execution trace or training feedback. Its 226 eligible rule entries yield 67 shapes. Shapes used by at least two rules cover 191 entries. The build emitted 108,096 bytes of Rust source. The linked binary grew from 6,347,232 to 6,579,952 bytes. In this offline build the source-only emission took 0.45 s and emission plus release relinking took 17.54 s. These costs are outside inference.

| Source | Vanilla | Joint model baseline | Interpreted projection | Native shared shapes | Native all shapes, ms | Native calls, shared / all |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.23 | 33.59 | 33.72 | 32.73 | 32.89 | 4,797 / 7,592 |
| conjugate-gradient | 360.92 | 656.45 | 650.43 | 666.08 | 652.54 | 188,455 / 239,114 |
| 3mm | 964.08 | 1,994.03 | 1,972.17 | 1,938.25 | 1,908.90 | 716,791 / 831,251 |

One default exact CPU and four learned arms were timed in rotation for four samples after warmup at seed 1703. The projected, shared-shape and all-shape arms perform the identical number of source root constraints, typed point reads, native primitive evaluations and successful matches on every workload. Every learned stream keeps its original parent identities, ordered RHS, effective writes, union, Spine, final graph and directly constructed physical Cell IDs. These measurements concern the standalone Cell CPU, not upstream egglog. [All paired samples and dynamic counts](results.json)

In a separate instrumented replay the median single-parent validation and winner-assembly interval on 3mm was 327.03 ms for the joint baseline, 287.60 ms for interpreted projection and 258.40 ms for the baked body. On conjugate-gradient these figures were 93.22 / 83.10 / 75.60 ms. These intervals include packaging an accepted binding, and they are not added to the uninstrumented inference measurements. Direct instruction generation lowers interpreter overhead; the large residual cost of full-key table access and the rest of the source schedule remains. [Native phase samples](phases.json)

The second source defines new table names, mutable min-merged integer functions and a 14-atom arithmetic rule. A donor kernel registered for one of its three non-null-pivot plans, ran four times and the general verifier handled the remaining shapes. Both paths agreed with the source oracle through a missing-key activation, an actual equality merge and a later value change. Rule 5 of this fixture, with 14 atoms, still committed on the final Run. [Fixture source](../run-result-certificates/change.egg) · [Source/physical evidence](transfer-fixture.json)

```sh
d=benchmarks/pass3-cell-gpu/native-verifier-bake
python "$d/build.py" "$EXP/compact-holdouts-20261121-v1/sum-bits-1703/program.json" "$EXP/baked-verifier"
python "$d/study.py" "$EXP" "$EXP/baked-verifier/session" "$EXP/baked-verifier-study"
python "$d/phases.py" "$EXP" "$EXP/baked-verifier/session" "$EXP/baked-verifier-phases"
python "$d/verify.py"
```
