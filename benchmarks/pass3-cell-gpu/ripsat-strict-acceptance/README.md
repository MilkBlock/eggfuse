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


## Does a signed Single continue?

For each of the two authenticated donor cards, the **local RipSat replay** contains a genuine three-application history: records 0 → 8 → 12 run 143 → 55 → 143. The next record names a fact token actually produced by the preceding record. These are local tokens (6 then 10 in dot-product, 6 then 9 in jacobi-1d). In the **default portable catalog**, two donor cards authorize the same single edge 143[1] → 55 and zero authorize a second edge. Before imposing source schema, the native-directed sample edges give four same-donor ordered pairs of adjacent rule labels; none share the same actual middle occurrence. The 446 self-return stays in the static-consumer-only library. A function-level test uses one synthetic connected positive and ten independently altered receipts to verify the actual adapter join, including donor, serial, commit ordinal, Run, schema, atom, FactRef cell/op and version. Synthetic inputs never enter the published library.

| Source donor | First signed internal 55 roots | op 0 `let Single` elided by native static alias | Fresh op 1 `set Get` facts | Distinct later paid 143 reads of those identities/versions | Free second steps executed |
| --- | ---: | ---: | ---: | ---: | ---: |
| dot-product | 44 | 44 | 44 | 36 | 0 |
| jacobi-1d | 192 | 192 | 192 | 153 | 0 |

The observation hook records pre-existing constructor returns only when the native operation actually returns a witness. At op 0 the existing compiler elides the operation as the statically known old input slot; no newly returned op-0 fact was recorded. The fresh facts at op 1 are concrete constructor-table **Set** births. The default adapter's returning-constructor certificate requires **Let**. All detected later 143 reads above were ordinary external proposals. The table therefore measures opportunities for a different publication ABI, not extra program steps or saved packets.

The exact middle of the selected **dot-product** card matters. Serial 1,737 in Run 131 supplies Single to internally signed serial 1,822 (ordinal 843) in Run 135. That very invocation of 55 creates Get at **Cell 971, op 1, version 135**. Later paid rule 143 serial 2,625 (ordinal 1,288, Run 139) reads the same original fact at atom 0. The companion's producer is the original accepted card's consumer byte-for-byte. In **jacobi-1d**, serial 5,314 feeds signed middle 5,598 (ordinal 2,959, Run 229); this precise middle creates Get at **Cell 3,087, op 1, version 229**. There are zero later 143 reads of that particular identity/version. Other productive jacobi middles cannot be substituted for it.

Separate ordinary-leaf and signed executions check equal source Run schedules, RHS, effective writes, Spine, root ledger, complete event stream, physical allocations and final graph. The observer records output identities and executes no matching or inference on behalf of the runtime. No timing is claimed. The jointly pinned files include the original evidence origin and native-acceptance hashes, full three-root compiled slots/references where present, true source birth event, consumed input port and donor ground terms. The companion is evidence for authorizer tests; it does not change the default library.

[Catalog/guard counts](catalog-chains.json) · [All signed-middle operations](chain-audit.json) · [Pinned companion source receipts](companion-pins.json) · [Dot-product witness](dot-product-same-middle.json) · [Jacobi counterexample](jacobi-1d-same-middle.json)

```sh
python build_chain_audit.py "$exp/chain-return-observer"
python chain_audit.py "$exp" "$exp/chain-return-observer/session" "$evidence" "$exp/chain-run" \
  --donor "dot-product=$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  --donor "jacobi-1d=$exp/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json"
python companion.py "$exp" "$exp/chain-return-observer/session" "$evidence" "$exp/chain-port-receipts" \
  --donor "dot-product=$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  --donor "jacobi-1d=$exp/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json"
python chain_catalog.py "$evidence" "$exp/extra-pass3-transfer-v1/3mm-1703/program.json" "$exp/catalog-chains.json" \
  --donor "dot-product=$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  --donor "jacobi-1d=$exp/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json"
python verify_chain.py
```


## Separate fresh-Set publication ABI

The optional typed Set-publication program has a different contract from the default library above. We independently reproduced the publication authorizer's exact artifact for dot-product and tested its actual persistent native entry point. Its program executes the previously paid terminal serial **2,625** internally at Run 139 with the actual Get fact **Cell 971, op 1, version 135**, issued by the same signed middle serial 1,822. The ordinary endpoint and signed trail are independently pinned. The default returning-Let path continues to reject Set as a return source.

Fifteen direct authorizer counterexamples check the identity of the middle occurrence, both physical input ports, publication version, freshly activated Set birth, assigned fields, native history dependencies, terminal witness, and the distinction between constructor-table Set and returning Let. The additional eight native cases cover wrong ABI kind, pivot, operation, target, coordinated substitution of both request and authorization digests, actual assigned fields, withheld receipt, and stale receipt. The persistent decoder now compares both target fields with the SHA-256 of the actual loaded bytes. Using an identical fake SHA in both fields rejects. Withholding or staling receipts produces zero second internal steps and restores exactly 36 separate external terminal packets. This is an audit-only run, not another performance measurement.

[Source and local-history publication obligations](publication-proof-checks.json) · [Persistent native corruption and fallback results](publication-native-checks.json)

```sh
python publication_proofs.py "$evidence" "$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  "$exp/ripsat-publication-authorized-v1/dot-product.json" "$exp/publication-proof-checks.json" \
  --donor "dot-product=$exp/compact-holdouts-20261121-v1/dot-product-1703/program.json" \
  --donor "jacobi-1d=$exp/compact-holdouts-20261121-v1/jacobi-1d-1703/program.json"
python publication_controls.py "$exp" "$exp/ripsat-set-receipt-pinned/session" "$exp/publication-native-checks.json" \
  --authorization "$exp/ripsat-publication-authorized-v1/dot-product.json"
```
