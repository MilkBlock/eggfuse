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

### Field pointers with frozen weights

The optional `--field-pointer` head retains each receipt field's 64 signed hash bits. After a lane selects a parent port, its selected fields become queries against the other ports' field vectors. Bake determines the column pairs from repeated query variables. The model adds scaled dot products to its existing pointer logits. The host never enumerates pairs of candidate ports. The shared field representation and attention bias are architectural choices. The original trained weights remain frozen for this comparison. Scores do not prove equality, and the same port may be issued for two roles.

On the same 96 held-out programs, correct exclusive final states increased from 8 to 28. Given the exact history before collision, accepted distinct-endpoint actions increased from 1/48 to 46/48, and 46/48 same-endpoint controls were accepted without producing any repair event. On the held-out changed-operand/PC task the event read remained 0/16 on correct history. The field changes do not address the first unconditional port choice. These CPU comparisons measure semantic outcomes; no throughput improvement is established. The [mode-separated record](field-results.json) retains model, verifier and issuance counts. Reproduce with the original checkpoint and corpus by adding `--field-pointer` to the evaluate and prefix-probe commands above.

### Recurrent issuance within a source Run

`online.py --wave-limit N` reuses one immutable memory snapshot for all waves. Lanes receive a pooled representation of their just-issued templates and ordered parent keys before their next decision. Every complete proposal, including duplicates, reaches the verifier. The issuer reports Stop, an incomplete request, a repeated wave or budget exhaustion; these are local decoding outcomes. Source execution can still diverge from saturation.

Counting the reference tapes gives a four-lane single-wave ceiling of 1,583/7,265 RHS bindings for sum-bits and 1,594/6,704 for dot-product with one binding per proposal. With fixed weights trained only on single waves, changing the limit from one to eight on sum-bits raised paid proposals from 130 to 234 and native acceptances from 10 to 12. Dot-product went from 126 to 221 proposals and 9 to 10 acceptances. Both final graphs still diverged. The increased budget mostly added duplicate or rejected work. [Raw counts and timings](wave-results.json)

### Mixed EggCC epoch on Apple Metal

The field-pointer Actor trained with AdamW/backpropagation on MPS for 8,930 updates from the earlier checkpoint. It visited all 1,026 training programs and all 6,035 source Run snapshots. The random portion grew from 16 programs and 48 snapshots to 1,024 and 3,072. Its three merge shapes gave 170, 171 and 171 training programs with a consumed repair output at PC 0, 1 and 2 respectively. The native portion contributed 13,969 committed bindings on 2,963 Runs of sum-bits and dot-product. Fact and loopfact were held out. Each independent native tape was replay-checked before inclusion. Both checkpoints used the same pointer architecture, rotary frequencies, four lanes and one issuance wave. The trained key and first-parent conditioning checks passed on collision examples from each of the three training merge shapes.

| Held programs | Exact final states before → after, exclusive CPU | Required repair parent correct before → after, teacher snapshots |
|---|---:|---:|
| Fresh random programs | 16 → 48 of 48 | 15 → 24 of 24 |
| Held merge template | 19 → 46 of 48 | 10 → 24 of 24 |
| Held result position and template | 9 → 13 of 48 | 0 → 0 of 24 |
| Fact and loopfact | 0 → 0 of 2 | No required repair references on sampled snapshots |

On the complete 1,252-Run native holdout census, the trained rule head stopped all four lanes on 319/329 Runs with teacher commits and 921/923 Runs without commits. Before training the corresponding counts were 0/329 and 2/923. Among busy Runs, the number with at least one correct free rule choice fell from 39/163 to 1/163 on fact and from 56/166 to 1/166 on loopfact. In an offline diagnostic on stopped lanes of busy Runs, the trained Actor's highest-scoring non-Stop rule had a winner on 200/647 and 238/659 lanes respectively. Removing Stop alone would still leave most of these rules wrong.

With the teacher naming a winning rule on 16 sampled busy Runs per program, exact full parent tuples improved from 20/176 to 30/176 lane/rule trials for fact and from 49/256 to 65/256 for loopfact. In free exclusive execution, both models used single-thread CPU inference and the actual native verifier with zero independent searches. Together the held EggCC programs went from 17 accepted of 258 issued to 4 accepted of 4 issued; the certified prefix fell from four reference commits to two out of 3,087. These measurements evaluate proposal semantics. Wall times include the experimental JSON transport and have no paired speed control.

The [paired experiment record](mixed-epoch-results.json) includes the hashes, split ledger, every sampled rule-audit Run, the separate full rule census, shadow parent accuracy and exclusive receiver outcomes. To reproduce using a sealed corpus at `$root`, the previous checkpoint at `$initial` and its receiver at `$receiver`, run the following from this directory. The reporting helper expects the existing initial-weight evaluations in `$root/baseline-eval.json` and `$root/rule-head-baseline.json`, produced with the same evaluation commands and initial weights.

```sh
mkdir -p "$epoch"
python train.py "$root" "$epoch/mps-epoch.pt" --device mps --field-pointer --steps 8930 --initial-weights "$initial"
python rule_audit.py "$root" "$epoch/mps-epoch.pt" "$epoch/rule-head.json" --field-pointer --samples 16
python evaluate.py "$root" "$receiver" "$epoch/held.json" --weights "$epoch/mps-epoch.pt" --field-pointer --split held_eggcc --split held_program --split held_merge --split held_result_pc --snapshot-count 16
python rule_audit.py "$root" "$initial" "$epoch/census-before-with-ranking.json" --field-pointer --held-rule-census
python rule_audit.py "$root" "$epoch/mps-epoch.pt" "$epoch/census-after-with-ranking.json" --field-pointer --held-rule-census
python mixed_results.py "$root" "$epoch" mixed-epoch-results.json
```
