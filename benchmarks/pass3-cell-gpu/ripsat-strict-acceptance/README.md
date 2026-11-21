# Independent RipSat admission counterexamples

There are two existing Cargo paths. The native Cell recipe registry reads completed exports through `RipSatEgraph::from_native_export`, distinguishes observed states and records actual initial/final slots. In the ordinary compiler, `bake-cell-completion` and `cell-iterate --objective ripsat-completion` already produce checked CPU handoffs and use the Cell e-graph to share complete structures. A new neural adapter has to bind a particular exported proof and its return ports to an authoritative source edge, then present that checked edge to the strict runtime. The status string and number of rows alone cannot identify the graph. [Recipe import](../../../src/cell_recipe.rs) · [Existing compilation](../../../tools/cell-compiler/src/completion_bake.rs) · [Previous native runtime tests](../../../tools/cell-compiler/tests/ripsat_completion.rs)

The source checks use a compiled Jacobi-1d Pass 3 donor and a small input compiled and executed by ordinary Cargo commands. The small case creates two distinct Pair rows. One pair's arguments become equivalent after a local union; the other pair still has distinct arguments. The ungated rule produces two outputs and the repeated-slot consumer produces one. The static candidate uses this same Pair template, so only the ungated consumer can be admitted without another equality check. [Small source](local-equality.egg) · [Source checks](source_cases.py) · [Recorded results](source-checks.json)

The Jacobi-1d example exercises independent premises. Rule 143's constructor at op 1 returns a Single row. It can supply rule 55's unary pivot. Rule 60 additionally needs an Add-Gets row; the same returned Single does not cover that independent parent. Conversely, the observed Get birth at rule 55 op 1 is a constructor-table Set. This adapter's returning-Let proof does not accept that operation as a static returned port.

The existing seven native completion tests also pass with the normal repository compiler.

```sh
cargo test --release --locked --offline -p eggfuse-cell-compiler \
  --features iterative-bake,view-ports,sparse-cells --test ripsat_completion
cargo cell-compile --source benchmarks/pass3-cell-gpu/ripsat-strict-acceptance/local-equality.egg --output "$EXP/local-equality-program"
cargo cell-run --program "$EXP/local-equality-program/program.json" --output "$EXP/local-equality-state"
python benchmarks/pass3-cell-gpu/ripsat-strict-acceptance/source_cases.py \
  "$EXP/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json" \
  "$EXP/local-equality-program/program.json" "$EXP/local-equality-state/state.json"
```


## Real default adapter acceptance

The full CLI compiled an isolated **dot-product 143, op 1 → 55, pivot 0** certificate for the held-out 3mm target. Local history record 0 writes token 6 at the producer's original Single constructor effect. Native history record 8 reads that exact token at the consumer; in this particular replay, the local result class is 5. For the NoAlias self-return the native history contains a producer but no later application reading that returned row. Its default library is empty, with one candidate confined to the separately labelled static-consumer library.

| Boundary under test | Measured evidence |
| --- | --- |
| Full adapter CLI with the independent trust index | 26 negative inputs produced zero default authorizations. All 26 also produced zero static-consumer paths. The ordinary, unmodified cross-workload certificate remained authorized. |
| Typed proof checks below the file-integrity layer | 13 independent corruptions lost their linked proof. Tests change the producer's required fact, exact returned class, the later consumer's required token or its link to the producer, graph observation flags, source incidence and original Run/version, among others. |
| Source premises and instance equality | The compiled fixture produces two Pair rows and one equality-guarded result. Source checks reject a missing independent Add-Gets parent, a returning-port claim on a Set and promotion of a local equality to a template-wide condition. |
| Previous normal CPU compiler and execution | The seven existing native completion tests pass. They cover prior registry/CPU execution responsibilities separately from the new adapter. |

The foreign-source control runs the **actual native RipSat exporter** on a copy of the grounded donor in which Single is replaced with ForeignSingle. Both runs reached native saturation with 15 values and 14 rows. A graph-only swap and a whole-source/export swap were each refused. Other tests alter an unrelated integer literal, change the original consumer from Run 135 to 136 while keeping it later than the producer, remove an explicit physical input, substitute an operation and the corresponding fact ID together, or forge a new native acceptance receipt and all editable per-sample checksums. The trust index used by the normal CLI is read from the independent checkout; the tests never rewrite it.

These checks distinguish provenance from the correctness of one static wiring. Checking only the returned Single incidence cannot detect an unrelated graph literal. Comparing only Run order cannot identify the measured donor occurrence. The native output receipt and the separate original-donor pin reject those changes, even though the local edge could remain structurally legal. The direct proof-layer controls exercise semantic checks without attributing a receipt-hash failure to the semantic checker. [CLI cases and rejection reasons](adapter-checks.json) · [Direct proof controls](proof-checks.json) · [Normal Cargo test output](cargo-reference.txt)

To repeat the acceptance run from this directory, use the frozen donor bundle matching the checkout trust index and a new external scratch directory.

```sh
root=/Volumes/EggFuseWorkspace/worktrees/eggfuse
exp=/Volumes/EggFuseWorkspace/experiments
evidence="$exp/ripsat-donor-evidence-v2/evidence.json"
sample="$exp/ripsat-donor-evidence-v2/samples/dot-product-p143-o1-c55-full"
cargo build --manifest-path "$root/Cargo.toml" --release --locked --offline -p eggfuse-cell-compiler --example ripsat_donor_graph
python foreign_export.py "$sample" "$exp/foreign-single-test" "$root/target/release/examples/ripsat_donor_graph"
mkdir -p "$exp/ripsat-negative-scratch"
python check.py --evidence "$evidence" \
  --donor "dot-product=$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  --donor "jacobi-1d=$exp/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json" \
  --target "$exp/extra-pass3-transfer-v1/3mm-1703/program.json" --foreign "$exp/foreign-single-test" \
  --unrelated-target "$exp/local-equality-program/program.json" --scratch "$exp/ripsat-negative-scratch" \
  --out "$exp/ripsat-negative-scratch/checked.json"
python proof_layers.py "$evidence" "$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" "$exp/ripsat-negative-scratch/layers.json"
python verify.py
```
