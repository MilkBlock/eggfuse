# Two adjacent ports from iterative Bake

This corpus starts with the frozen sum-bits and Raytrace eggcc Pass 3 catalogs. `cargo cell-compile` rebuilt each typed program on the external worktree (jobs 1010 and 1011). Both `recipe.sha256` values and both installed Spine and iterative catalog objects match their shipped catalogs. The compiler's slot/effect order, the published fact table, the consumer pivot and the Spine column map determine each example's matching checks and projected outputs. See the [frozen workload provenance](../../../../workloads/pass3/README.md).

Each catalog contains 32 Spine leaves plus 32 iterative binary compositions. Leaf order and join construction follow `Catalog::parse` and `Catalog::combine` in [iterative.rs](../../../../engine/cell-runtime/src/iterative.rs). The output index on a join selects the **producer effect operation**. Its table must match the next consumer's pivot table. The Spine `inputs`, `port.key` and `port.check_result` describe the ordered consumer arguments. The Rust wire format and its translation to internal fields are in [cell_query.rs](../../../../engine/cell-runtime/src/cell_query.rs).

The bounded task exercises the following boundary of a compiled continuation.

1. The earlier Run supplies candidate producer operand frames and candidate committed fact rows from the selected effect table. For a construct, match the actual constructor key arguments (including repeated slots and literals); its returned Eq reference comes from the witnessed fact. For a `set`, this contract requires the observed row's result to equal the proposed value. A merged value different from that proposal is outside the contract. The generated token can project all columns of the selected fact.
2. A subsequent Run supplies candidate consumer observations. Each holds the consumer's RHS input vector and, for a residual port, the observed key and returned value. The new rule matches that vector against the generated anchor, its pivot literal/repeated-slot constraints, and its actual residual port checks. Its output is the Spine block's ordered input vector. These observed frames give the model multiple possible witnesses to connect.

For example, sum-bits unit 33 publishes `SubTuple(expr,index,1)` from producer rule 143. Its consumer rule 145 has pivot `SubTuple(expr,0,len)` and an additional `tuple-length(expr)` result equal to `len`. Consequently this continuation requires `index=0`, `len=1` and the observed length to agree. Other templates read a residual result as `PortResult` and pass it into the RHS. The consumer can therefore require a different lookup and different port ordering when two templates produce the same table.

The selected unit is a real baked two-leaf continuation. Concrete synthetic frames begin **after** the producer's earlier operations/reads and carry bounded scalar or canonical Eq identifiers. The consumer's frame supplies observations, including successful residual lookup values where applicable. This tests matching and argument delivery at the two boundaries. It does not replay the actual graph, prove every synthetic frame globally reachable, perform implicit merge/rebuild, or execute the consumer's remaining RHS effects. Catalog entries identify allowed compositions. They do not identify unique Run ordinals for these synthetic records. The catalog and source rule hashes carry provenance, and no new full Raytrace inference run was needed.

## Manifest and holdout

`manifest.json` contains 19 semantic templates from 30 original two-leaf joins. Identical directed contracts with identical rule identities are unified across catalogs. For each template:

- `rule_ids` holds two stable hashes of source rule text plus its ruleset for the per-rule comparison. `atomic_seen_in_training` records stage-specific training exposure.
- `stages` contains ordered `left_sorts`, `right_sorts`, `output_sorts`, equality `checks` and projection `outputs`. Each operand `[side,column]` reads a left (0) or right (1) column. `[2,k]` is a literal integer. `Unit` has only the value 0. Committed fact rows form a functional table by their key columns before the final result column.
- `graph` supplies directed edges, nodes with structural role, kind of sort and local ordinal, plus a `[stage][side]` readout-node map. It carries actual shared, literal, publication and projection edges. The node features have no global rule IDs, table names or workload labels.
- `provenance` names the original workload, numeric rule/pivot/operation IDs, ruleset, actual source rules, installed unit and ancestry for audit. The template family split uses only structural information.

For the split, twelve rounds of isomorphism-invariant color refinement group the graph after discarding names, **all sort labels**, literal values and column ordinals. The initial colors preserve stage and input side; directed edge types and output roles are semantic. This is a conservative grouping: an indistinguishable non-isomorphic pair is kept on the same side. Even a simple port-column relabeling or changing an Eq column into an integer cannot put the same topology on opposite sides. The model itself may still use the genuine types/ordered columns. `verify.py` permutes node and column identifiers, reverses edge enumeration and changes all sort labels before rechecking every family key.

Eleven groups remain. The split holds out two entire groups, maximizing the number of held-out templates with both atomic heads already seen in training, then minimizing cold heads. Hash-based tie breaking is fixed; no measured neural outputs enter selection. Twelve templates train and seven are held out. Four held-out templates contain both rules in their respective training stages. Three have a consumer rule never seen in training. In one of the three, the producer was also unseen in the producer stage but its rule did receive updates in the consumer stage. The private scorer is indexed by rule across stages. Guarded per-head cold-start scores must be reported separately. All 34 longer composition units are excluded from the samples, including all 14 whose lineage touches the held-out structures. An atomic rule can legitimately appear in both splits; the composed family is the unit of generalization.

`verify.py` compares both exported stages against direct source-effect and raw Spine program interpretation using 480 positive two-stage witnesses plus single-column perturbations of each witness. The result file lists separately the number of producer/consumer comparisons. Synthetic post-publication checks do not attest actual end-to-end Pass 3 correctness or speed.

Rebuild the programs with a fresh output directory for each cargo invocation, then export the manifest and check it. Submit the compiler jobs through the shared compute queue in the mounted workspace. Supply the two resulting `program.json` paths to both Python commands.

```sh
cargo cell-compile --case sum-bits --output /Volumes/EggFuseWorkspace/experiments/port-ablation-program-sum-20261119
cargo cell-compile --case raytrace --output /Volumes/EggFuseWorkspace/experiments/port-ablation-program-ray-20261119
base=benchmarks/multi-row-generation/port_ablation/corpus
sum=/Volumes/EggFuseWorkspace/experiments/port-ablation-program-sum-20261119/program.json
ray=/Volumes/EggFuseWorkspace/experiments/port-ablation-program-ray-20261119/program.json
python3 "$base/export.py" "$sum" "$ray"
python3 "$base/verify.py" "$sum" "$ray"
```
