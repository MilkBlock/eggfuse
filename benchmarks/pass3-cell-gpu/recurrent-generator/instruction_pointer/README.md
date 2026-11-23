# CPU instruction pointers over runtime-issued repair ports

The native capture now exports each materialized merge event, its static template, ordered old/new references, hashes of the two exact operands, actual result PCs and earliest visible Run. The optional memory exporter observes the full set of named, visible return ports at pre-write Run boundaries and transmits changes. Scanning the address space and transporting the deltas cost time. This diagnostic exporter is used on random programs and by the online Actor. Oracle timings in the [native replay study](../../token-replay/README.md) use the ordinary uninstrumented memory path.

The Actor uses two rounds of message passing on the compiler's slot/instruction graph. Input, generated and repair keys share the graph encoder, role-dependent parent projections, rotary result position and dynamic receipt fields. Ordinary tokens optionally accept an extra lane latent. The current trained checkpoint uses the structural inputs alone. Merge operand positions are ordered even for a noncommutative merge. A token handle is used to return a selected address; its numeric value never enters the network. Handles and port order are randomized during training and evaluation.

Each lane selects a scheduled rule or Stop, selects an anchor role and a named port from that rule's visible delta, and then chooses each remaining port conditioned on its earlier reads. Type and source-Run visibility are the only masks. Primitives run in the native verifier. Four lanes issue up to four complete requests in one wave in this evaluation. Frozen snapshots for training and interactive inference both pass through the same history reader. The online verifier receives a complete request for each proposal and accounts for acceptance, duplicate, or classified rejection, including rules already known to be untriggered. It never asks the teacher for a missing parent. The optional diagnostic transport exchanges JSON, so its timings include serialization, discovery and communication overhead.

## What the frozen weights actually did

Training used 16 random programs (eight collision/no-collision pairs), 48 Run snapshots, seed 1703, and 500 AdamW steps with backpropagation on Apple MPS. Eight snapshots naturally required event references; one quarter of sample draws select that stratum, the other three quarters draw uniformly from all snapshots. Random programs supply all labels. Neither EggCC program entered training. Inference and all native checks below ran on CPU. A CPU gradient sanity check earlier in development made no weight updates.

Each held-out group contains 16 fresh random seeds and both collision arms, yielding 32 programs. The held-program group retains the training merge shape. In the second group an unseen outer operation wraps the merge result; the consumer still reads the inner result at PC 0. In the third group an unseen operation wraps the old operand; the required result is now at PC 1. This last intervention changes operand context as well as position. Its failure cannot be attributed solely to positional encoding.

| Held out | Initial parent | Generated parent | Repair parent | Complete reference requests on teacher snapshots | Exclusive runs with reference final state |
|---|---:|---:|---:|---:|---:|
| Programs | 247/272 | 90/128 | 8/16 | 191/240 | 4/32 |
| Outer merge operation | 248/272 | 86/128 | 10/16 | 191/240 | 4/32 |
| Inner operand and result PC | 234/272 | 82/128 | 0/16 | 173/240 | 0/32 |

Address accuracy compares against one committed teacher certificate using one-to-one assignment of complete requests. An alternative valid certificate may differ from that label. Exclusive final-state equality is measured against a fresh native run. In these three groups the random-weight control selected 0/48 required repair parents. The trained exclusive actor elicited two repair events in the outer-merge group and zero in the other two groups.

The prefix intervention replays the exact history up to each decision, then verifies only that Run's model proposals. Starting immediately before the collision on the 48 positive holdouts, the model triggered 1/48 expected events. Rust rejected 47 proposals for incompatible bindings. In 43 of those 48 trials the model named the same port for roles whose reference parents were distinct. In the negative arm a self-union is legal, which makes the superficially similar action a poor predictor of success on the positive arm. Starting immediately after a real event, the model submitted 8/16, 10/16 and 0/16 verified required consumers across the three groups. This separates choosing the colliding parents from using an available system result. The data point to independently learning both roles of the collision and varying the position of the needed output during training.

On actual EggCC, free execution with the same weights diverged from both reference graphs. Sum-bits issued 130 proposals and received 10 acceptances, 5 duplicates and 115 rejections. Dot-product issued 126, with 9 acceptances, 5 duplicates and 112 rejections. The majority of the rejections were for untriggered rules. A shorter divergent schedule cannot establish saturation, search replacement, EPT or acceleration. Full counters, build/weight hashes, timings and mode-specific denominators are in the [experiment record](results.json). Timings are diagnostic and no model speedup is claimed.

## Reproduce

Use the native compiler and receiver from the [replay build](../../token-replay/README.md). The trainer requires a functioning CUDA or MPS device, the evaluator uses one CPU thread, and the Python sources require Python 3.10+ with PyTorch. The generator expects a fresh output directory.

```sh
tools=benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer
compiler=target/release/eggfuse-cell-compiler
bin=target/release/examples/cell_token_replay
python "$tools/generate.py" "$compiler" "$bin" /tmp/pointer-corpus --count 8 --held-count 16 --extra-family
python "$tools/check_structure.py" /tmp/pointer-corpus/train-100-1
python "$tools/train.py" /tmp/pointer-corpus /tmp/actor.pt --steps 500
python "$tools/evaluate.py" /tmp/pointer-corpus "$bin" /tmp/random.json
python "$tools/evaluate.py" /tmp/pointer-corpus "$bin" /tmp/trained.json --weights /tmp/actor.pt
python "$tools/prefix_probe.py" /tmp/pointer-corpus "$bin" /tmp/actor.pt /tmp/prefix.json
```

The initial job queue and two PyTorch installations in the agent session both returned Metal compiler service error 141. The same external workspace and trainer succeeded from the logged-in macOS session. Dataset expansion, CPU inference, negative controls and native validation completed through the local job queue once the weights were available.
