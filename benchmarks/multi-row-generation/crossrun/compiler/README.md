# Rust compiler projection for two Runs

`rules.egg` declares two ordered rulesets. The producer joins A and B on key and publishes `Pair(i,j,k,x,y)`. The consumer joins that Pair and Request on the two parent identities and publishes `Result(i,j,t,x,y)`. The full source program appends input facts and `(run-schedule (seq (run make) (run finish)))` to the shared rules.

`plan.json` contains one copy of the projected column map per rule. Each entry is `[input_atom, column]`, with zero-based indices in the order given by `inputs`. `outputs` lists the sources of RHS constructor arguments. `equalities` records the LHS shared slots as pairs of source columns. An address prediction still has to identify a valid correlated binding. Only offline compilation and audit read LHS equality constraints or graph exports in this directory.

`extract.py` derives each route from query-slot reuse in the typed compiler recipe. It accepts direct i64 slots, two complete relation atoms and one relation construction. Unsupported effects, primitive conditions, computed RHS values and equality-sort output references cause an error. The exporter rechecks every binding's concrete parent identity against the immediately preceding graph. It checks every post-Run relation before reporting the visible rows.

Three small witnesses in `fixtures.json` include a change to just one requested parent. Both versions publish the same five Pairs, including four Pairs with identical `(k,x,y)` and distinct `(i,j)`. The two consumer runs publish different requests as three rows each. The third fixture publishes no Result. `runtime-audit.json` records the two graph boundaries and source, recipe and compiler output hashes for each case.

`check_panels.py` additionally runs the real binary on all 768 evaluation inputs. It compiles each source, verifies the direct column map, looks up each traced parent in the preceding graph, and aligns the two published relations with their respective source-derived labels. The recorded nonempty consumer counts are 162/256 IID and 256/256 in both parent-collision holdouts. The independent reference uses the CPU offline. GPU inference consumes the compact plan.

Rebuild the offline evidence on the mounted research worktree. The inputs and compact output files are reproducible. Large intermediate compiler exports can stay in the external experiment directory. Run the Rust and full-panel steps via the shared job queue.

```sh
base=benchmarks/multi-row-generation/crossrun/compiler
artifacts=/Volumes/EggFuseWorkspace/experiments
python3 "$base/build_request.py" "$artifacts/multi-row-crossrun-compiler-input.json"
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse cargo run --offline --release --locked -p eggfuse-cell-compiler --example real_completion_dataset -- "$artifacts/multi-row-crossrun-compiler-input.json" "$artifacts/multi-row-crossrun-compiler-output.json"
# After the Rust export completes
python3 "$base/extract.py" "$artifacts/multi-row-crossrun-compiler-output.json" "$base/plan.json" "$base/runtime-audit.json"
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse python "$base/check_panels.py" target/release/examples/real_completion_dataset "$base/panel-audit.json"
python3 "$base/test_extract.py"
```
