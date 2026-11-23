## Shared training and native execution of variable-size higher Cells

A template contains source rule occurrences in execution order. Each occurrence has a relative Run group and one input per table atom. An input names either a shared external boundary slot or an earlier occurrence and the PC of its actual returned fact. Two uses may share one boundary slot. Multiple independently verified steps can run in one group, and a later step may consume several different earlier returns. Ordinary rule primitives, effects and visibility remain authoritative in Rust.

### Bake and supervision

The two training tapes come from sum-bits and dot-product. Starting at each committed request, the extraction follows its actual parent references backwards and grows a connected graph one producer at a time, up to ten rule occurrences in this study. It preserves the order within source Runs, repeated external addresses and their observed versions. Initial facts, repair-event inputs and merge outputs without a directly typed RHS PC remain explicit boundary inputs. A graph can be ready to issue when every independent port has its signed version at the initial boundary, and internal returns retain their first sealed versions at consumption. Run groups resume at the first subsequent source Run scheduling all their rules. The limit of ten belongs to corpus extraction. The shared heads and receiver operate on the compiled instruction graph for any supported size.

The exporter found 49,371 distinct observed layouts, including 3,044 with a recorded ready completion. The frozen catalog contains all 3,044, all 32 distinct chain layouts from the donor's original iterative joins, and additional frequently observed layouts, for 4,096 unique entries. Actual graph sizes range from two to ten. 2,880 templates contain a multi-producer join and 1,820 have multiple steps in one source Run. The extra layouts are mined from native execution and checked against source operations. This experiment supplies evidence for the specified derivations; it does not establish equivalence to every alternative derivation or local saturation of each fragment in the RipSat optimizer. The old 670-entry RHS-fragment archive did not supply any multi-rule templates to these counts.

One shared graph scorer uses frozen root-Actor instruction embeddings, labeled input edges and learned messages from producer steps. It estimates observed completion and root-ready completion. The separate shared port reader fills all independent slots beyond those named by the root. Each choice reads earlier named inputs and scores the full visible domain of its static type. It trained with sampled negatives and teacher-forced previous boundary slots. The catalog and both checkpoints are frozen before evaluation. Bake precomputes the graph vectors and deduplicated boundary-role vectors. The scorer has 7,362 parameters and the reader has 5,377; neither allocates a parameter row per layout. Both trained offline on MPS using supervised gradients. [Training records](study.json) · [Boundary pointer diagnostics](boundary.json).

Of the 4,096 entries, 534 hash-selected complete layout identities were excluded from both heads' gradient updates. 3,562 distinct layouts contributed to the scoring loss, including 3,552 with a positive training example. The held layouts were in the Bake catalog, and they can share component rules with training layouts. The three evaluation programs are development holdouts used in earlier studies. Catalog frequency and readiness were selected using only the two training programs. Unobserved paths in these tapes are weak negatives. Exact literal pointer recall can undercount valid aliases.

### Verification and deployment

Native replay reconstructed each internal request from its previously credited commit and returned PC. Across five programs, 3,055 distinct layouts completed at least one checked instance, including all 3,044 ready on training. In total, 24,682 step probes recovered their specified commits. Incrementing a final parent version caused rejection on 5,824 otherwise valid certificates. This is a reference-input replay check. [Replay results](replay.json).

Live assist starts from the frozen root Actor's own proposals, chooses a layout, and signs its full external boundary. Rust receives one root packet, checks every boundary's type and version, verifies each step by its named references, and acquires intermediate results at the first sealed boundary. It retires an instance if a group fails and preserves independently legal matches. No internal step enumerates a missing parent. The ordinary residual search remains enabled in assist. The native receiver tracks root groups that have already committed siblings and defers dependent groups until their next legal Run. A completion count requires all steps to commit and a subsequent sealed receipt. The active-root budget is the existing one-wave, top-32 root Actor. Each eligible root chooses at most one layout.

| Development workload | Signed commits with root Actor | Signed commits with graph issuer | Reference commits | Fully completed graph instances |
|---|---:|---:|---:|---:|
| fact | 1,242 | 1,263 | 1,668 | 93 |
| loopfact | 1,040 | 1,053 | 1,419 | 63 |
| sum-divisors | 8,558 | 8,702 | 17,341 | 587 |

Across the three programs, the model issued 104 distinct layouts and fully completed 54, including five layouts held out of training. Of 743 completed instances, 733 had two steps, nine had three, and one had nine. The same trained model was used throughout. Each assist arm reproduced source schedule, ordered RHS, writes, resumes, events, final state and effective-operation ledger. The normalized per-workload exact candidate count was unchanged, totaling 26,148. Exclusive first diverged at Runs 7, 8 and 11, with a source panic on sum-divisors at Run 85. [Joint measurements](summary.json) · [Full native assist counters](assist.json) · [Search-free trajectories](exclusive.json).

| Live transport | Signed effective operations | Paid external packets | EPT |
|---|---:|---:|---:|
| Root Actor | 6,638 | 32,425 | 0.20472 |
| Same graph policy, materialize each step as an external packet | 6,736 | 39,398 | 0.17097 |
| One signed graph request with internal native steps | 6,736 | 32,401 | 0.20789 |

The two graph transports had identical distinct signed commits and effective operations on each workload. Signing a graph removed 6,997 external step packets. Every internal verification remains in the native work ledger. The previous side-fork study, using a different policy and receiver, recorded 10,974 signed commits and EPT 0.20611. The new graph policy reached 11,018 / 20,428.

Four alternating end-to-end CPU trials against the root-only control, ordinary exact search and the offline teacher oracle included loading the frozen policy, preparing the catalog, full inference, verification, IPC and residual work. Median signed operations per second went from 320.09 to 247.95 on fact and from 325.99 to 253.81 on loopfact. The graph arm lost all eight paired comparisons. The additional graph policy took a median 0.70 seconds on fact. No paired throughput measurement was performed on sum-divisors. Some semantic audit and disk activity overlapped the timing campaign. [Paired clocks and component costs](density.json).

### Reproduction

ROOT holds the exported programs, tapes and train/test manifest from the instruction-pointer study. WEIGHTS is its frozen opaque parent Actor. Use the Cargo feature cell-token-ept on the normal runtime and one CPU inference thread. The three development controls are root-only, expanded transport, and native graph transport. The code for both transports uses the same frozen decision heads.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay
python train_ripsat.py "$ROOT" "$ROOT/sum" "$WEIGHTS" "$OUT" --steps 10 --size 4096 --extra-eval sum-divisors
python ripsat_boundary.py "$ROOT" "$ROOT/sum" "$OUT" "$WEIGHTS" "$OUT" --cases fact loopfact sum-divisors
python bake_ripsat.py "$ROOT/sum" "$WEIGHTS" "$OUT"
python ripsat_replay.py "$ROOT" "$ROOT/sum" "$OUT/catalog.json" "$BINARY" "$OUT/replay.json" --cases sum dot fact loopfact sum-divisors
for name in fact loopfact sum-divisors; do
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BINARY" "$WEIGHTS" "$OUT" "$OUT/$name-control.json" --case "$name" --control
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BINARY" "$WEIGHTS" "$OUT" "$OUT/$name-expanded.json" --case "$name"
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BINARY" "$WEIGHTS" "$OUT" "$OUT/$name-native.json" --case "$name" --native
  python live_ripsat.py "$ROOT" "$ROOT/sum" "$BINARY" "$WEIGHTS" "$OUT" "$OUT/$name-exclusive.json" --case "$name" --native --exclusive
done
python ripsat_density.py "$ROOT" "$ROOT/sum" "$BINARY" "$WEIGHTS" "$OUT" "$OUT" "$OUT/density.json" --cases fact loopfact
```
