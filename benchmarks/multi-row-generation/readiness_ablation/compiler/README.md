# Reference schedule and visible state for Figure 07

The fixture has three independent source fact relations and two consumer rules. `C(k,x,y)` reads the visible witnesses `P0(k,x)` and `P1(k,y)` with the same key. `V(k,z)` reads `U(k,z)`. Using named source witnesses matters because different keys can carry equal values. The Rust compiler emits the key equality and ordered projection maps in `plan.json`.

There are **four source Runs**. In Run 1, ruleset `wave0` publishes wave 0's P0/P1/U facts from annotated ingress tables. Runs 2 and 3 do the same for waves 1 and 2. `finish` in Run 4 reads the complete producer snapshot and publishes both consumer relations. The ingress tables `InP0`, `InP1`, and `InU` are part of the reference harness and include future waves. The experimental GPU receives only the released event buckets. Global waiting, private candidate evaluation and any scheduling ticks between publications do not change the four source Runs. Until `finish` the source's public C and V tables are empty. Explicit seal/pending bookkeeping on a device stream is separate metadata and has no implicit `.egg` effect in this finite schedule.

The following witnesses were compiled and actually executed by the standalone Rust Cell CPU engine.

| Source fixture | Facts newly published in `wave0` | `wave1` | `wave2` | `finish` |
| --- | ---: | ---: | ---: | ---: |
| delayed | 3 | 1 | 1 | 3 |
| absent | 3 | 1 | 0 | 2 |
| overlap | 3 | 2 | 1 | 4 |
| duplicate-publication | 2 | 0 | 1 | 2 |
| empty | 0 | 0 | 0 | 0 |
| reversed-arrival | 3 | 1 | 1 | 3 |

For `delayed` and `absent` the first two waves have identical public facts. `P0(0,5)` and `P1(1,5)` already have equal payloads but fail the join. `U(2,1)` can support its private V projection immediately. Only the third wave of `delayed` supplies `P1(0,5)`, enabling `C(0,5,5)`. The independent V obligations are identical in the two final source graphs. In `reversed-arrival`, P1 arrives first and P0 appears in the last wave. Its public result equals `delayed` for every output tuple. In `duplicate-publication` the second source Run executes one binding with an already-live RHS row. Its effective publication count is zero.

`source.py` looks up every bound query row by its full data values **and opaque returned fact identity** in the preceding runtime graph. The machine-readable recipe supplies the ordered RHS column map. An independent source-level join checks projected RHS tuples. The checker then compares the newly present rows, previous reference identities, full visible table contents and original runtime anchors at every boundary. `final_semantic_sha256` covers the workload relations; `final_physical_sha256` additionally covers input rows, physical returned refs and the complete anchor map. Within-Run insertion order is unobservable in this fixture and is excluded from these set comparisons. Logical matches, executed RHS bindings and effective published rows have separate counters.

In the full panels, identical normalized source programs may arise from repeated arrays or seal-only variants. `panel_replay.py` compiles and executes every **distinct source schedule** once, then maps each neural example to its program. The map retains original rows, per-Run hashes of all observed operands/projected values, effective deltas and final graph evidence. Within one wave, ingress facts form a set; the source scheduler does not assign different identities to duplicate deliveries of the same tuple. A later duplicate can cause a new logical binding without creating another public row. Source projections allow multiple keys to be ready in the same wave. Each neural fixture assumes one scalar value per relation/key across the run, which the panel checker verifies.

Reproduce from the repository root using the shared queue. Binary outputs and large detached reports stay on the external experiment volume.

```sh
base=benchmarks/multi-row-generation/readiness_ablation/compiler
bin=target/release/examples/real_completion_dataset
# If the binary is missing, build it with the existing locked Cargo workspace.
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse cargo build --offline --locked --release -p eggfuse-cell-compiler --example real_completion_dataset
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse python "$base/source.py" "$bin"
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse python "$base/panel_replay.py" "$bin" /Volumes/EggFuseWorkspace/experiments/readiness-source-replay --splits iid heldout
```

The formal IID and held-out source audit covered 768 input rows. Their 576 distinct source programs executed 2,304 actual Cell CPU Runs. Held-out alone contains 512 rows (384 source programs). Across those 512, `wave0`, `wave1`, `wave2` executed respectively 2,920, 1,536, 1,864 projected producer bindings, making 2,920, 1,324, 1,564 newly visible facts. `finish` published 1,720 C and 2,040 V rows. The checker also compares `(producer kind, key, value, first published wave)` for every finish parent with the data module's independent witness record. Counts for both panels and their hash-qualified disk evidence are in [panel-audit.json](panel-audit.json).
