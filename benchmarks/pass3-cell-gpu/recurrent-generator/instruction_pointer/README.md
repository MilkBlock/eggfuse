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

### Selecting a rule from typed port reads

The previous Metal checkpoint selected a rule from the mean key of every port in the sealed snapshot. To test what information that mean lost, we froze every parameter of that checkpoint and added a learned correction to each scheduled rule's logit. The control receives the rule root, the global mean port key and port count. The experimental head reads the atom's table twice, once over all visible ports and once over the rule's legal delta. Each read pools port keys, includes a log count and uses the atom's GNN role in the rule summary. Empty tables and empty-LHS templates remain representable. Both heads have identical parameter counts. Both use the same unchanged Stop logit and parent decoder. Static typing and the source watermark determine the reads. The network still has to select a rule and name its parents.

We cached the frozen CPU representations on the 6,035 training snapshots and trained both residual heads on MPS. Each received the same shuffled snapshots, target draws, initialization and 756 updates over four epochs. Every reference binding contributes its rule to the draw pool. The objective marginalizes over assignments of up to four sampled rule labels to the lanes, including Stop for vacant lanes. The original backbone and all pointer weights were checked byte-for-byte after training.

| Metric | Previous mixed checkpoint | Retrained global read | Retrained typed read |
|---|---:|---:|---:|
| Busy reference Runs with a correct rule, fact + loopfact, out of 329 | 2 | 48 | 172 |
| Busy Runs on which all lanes stopped | 319 | 227 | 129 |
| Empty Runs on which all lanes stopped, out of 923 | 921 | 907 | 912 |
| Accepted / issued in complete exclusive executions, fact + loopfact | 4/4 | 16/52 | 31/103 |
| Certified reference prefix commits, out of 3,087 | 2 | 2 | 2 |
| Correct final graphs, fact + loopfact | 0/2 | 0/2 | 0/2 |

In the teacher-snapshot census the typed head chose a rule with a winner on 587/673 non-Stop lane decisions in busy Runs. The global head did so on 109/297. On the separate 16-busy-Run samples per held workload, the typed arm named a complete teacher parent tuple on 2/27 correct parent-requiring rule selections for fact and 6/34 for loopfact. In both exclusive runs the first discrepancy was Run 2. The required type-helpers rule has zero table parents. On the matching prefix every lane ranked it tenth. Correct graphs in the three synthetic groups were 48/48, 46/48 and 13/48 with the typed read; the held repair position remained 0/24. A third native program, sum-divisors, was evaluated after fitting. Its native teacher replay reproduced all 17,341 commits and the reference graph. The exclusive global and typed heads accepted 10/25 and 22/61 proposals; neither reproduced that graph.

All inference and verification above ran on CPU. There was one issuance wave per Run, with no residual search. Counts in the [paired report](rule-read-results.json) separate exclusive execution, shadow reads and oracle-rule diagnostics. No paired timing experiment was performed.

Reproduce the heads with `python train_rule_read.py "$root" "$epoch/mps-epoch.pt" "$out"`. Evaluate each `$out/global.pt` and `$out/typed.pt` with the same evaluate and rule-audit commands as the mixed epoch (use the output suffixes `-held.json`, `-rule.json` and `-census.json`). For the additional holdout save the native reference and replay audit reports and each arm's `online.py --field-pointer` output as `sum-divisors-{reference,replay,global,typed}.json`. Run `python rule_read_results.py "$out" mixed-epoch-results.json rule-read-results.json`. The per-atom reference reduction in `check_rule_read.py` agreed with the grouped read on 408 rule snapshots from nine sum-bits Runs, including 47 partially fresh atom windows and reversed port order.

### Run-frontier training and source arity

On the two native training programs the empty-query rules committed on all four first visits and zero of 412 later visits. The native verifier initializes an empty proof's epoch to zero. The optional rule mask applies the existing anchor visibility domain before selecting a rule. It admitted all 21,649 training bindings while excluding 87,566 of 103,813 scheduled rule/Run positions. It neither tests shared fields nor issues empty rules automatically.

Starting from the same typed model, uniform and stratified fine-tuning each ran for 756 MPS updates. The latter replaces one quarter of the Run draws with positive snapshots sampled across training origin and parent count. Rule selection and every parent still come from the Actor. With the mask only, and with uniform fine-tuning, fact, loopfact and sum-divisors first diverged on Run 2. With stratification, all three reproduced Run 2. On Run 3 each needed two bindings for the same two-parent rule and issued and committed one. Raising the frozen policy's wave budget to four left that first gap in place. None of the three exclusive final graphs matched. Synthetic final-state counts remained 48/48, 46/48 and 13/48. All native rollouts used one CPU thread and no independent search.

The [experiment record](anchor-results.json) includes source-stratified exposure, receiver ledgers and the per-Run decision census. Run `train_anchor.py ROOT TYPED_CHECKPOINT OUT`, then evaluate the three checkpoints with `anchor_audit.py`, `rule_audit.py --held-rule-census --field-pointer` and the four-split `evaluate.py` invocation above. Use the filenames consumed by `anchor_results.py OUT anchor-results.json`, including the four-wave stratified audit. Timings are observational.

### Per-Run teacher commit recall

For each sealed native Run, the denominator is its actual teacher RHS commit count. Each proposal passes the native receiver checks. The evaluator looks up the rule and exact bound input values in the Run's signed teacher bindings and credits each committed binding once. Alternate port addresses can prove the same binding. Duplicate submissions, rejected packets and valid off-reference bindings receive zero recall credit. The teacher alone advances the graph. The audit checks the replay's schedule, RHS, writes, resumes, events and final state against the captured trajectory. This is a shadow measurement; exclusive final graphs and prefix agreement remain separate.

The [per-Run CSVs and summary](run-recall/one-wave) give the numerator and denominator, including empty Runs, whose recall is undefined. The macro average covers busy Runs only. Micro recall counts all recovered commits over all required commits. For the single-wave stratified head, fact recovered 114/1,668 (5/163 busy Runs complete), loopfact 135/1,419 (6/166) and sum-divisors 595/17,341 (26/627). Using the [teacher itself as the control](run-recall/teacher-control.json) recovered every commit. To reproduce, build the release receiver with features `cell-token-replay slot-transfer-audit` and run `run_recall.py ROOT RECEIVER WEIGHTS OUT --workloads fact loopfact sum-divisors`. The control adds `--teacher-control`.

### One Stop per complete Run

The sequence experiment supervises every teacher request on a Run, in a shuffled order, followed by a single shared Stop. Four lane positions cycle until that Stop or an explicit 128-wave budget. A GRU consumes the selected template and its ordered parent port keys before the next lane chooses a rule. No new RHS entry becomes visible in the wave. In this experiment the receiver checks the batch at the Run boundary. The sequence sees its own issued requests before then; same-Run verifier verdicts are unavailable. The parent decoder remains frozen and uses its original lane state. Consequently the rule decoder can learn a different next action from issuance history while the same lane and rule can still pick exactly the same parents on the fourth subsequent decision.

Four MPS epochs covered all 21,649 teacher issues, including all targets of 508 Runs with more than four commits. Empty and busy Runs contributed 16,580 training visits each. Each Run contributes mean per-decision cross entropy and a coverage term for each distinct required rule in each four-position wave. The latter uses the probability that at least one lane selects that rule. Teacher-forced target sets are used only for supervision. Scheduled rules carry their watermark, its distance from the sealed epoch, and table-atom count alongside their typed port reads. No execution timing speedup is inferred.

The [complete-Run evaluation](run-recall/sequence) includes actual receipt-checked per-Run recall, budget stops, empty-Run proposals and separate exclusive results. On the two fact workloads the new model missed Run 2 again under exclusive execution. It reproduced zero final graphs across the three synthetic groups (previously 48, 46 and 13 of 48). Repeated proposals on a frozen snapshot are charged even when the issuer uses the whole wave budget. The checkpoint is experimental.

To reproduce, run `train_sequence.py ROOT STRATIFIED_WEIGHTS OUT`. For each native workload use `run_recall.py ROOT RECEIVER OUT/sequence.pt OUT/recall-WORKLOAD --workloads WORKLOAD`. Run it a second time with `--wave-limit 1` and output directory `OUT/capped-WORKLOAD` for the same-weight control. Run the three-program exclusive `anchor_audit.py` and four-split `evaluate.py` as above, and use `sequence_results.py OUT run-recall/sequence` to assemble the reports. Decoding uses the checkpoint's wave budget by default. This measures an autoregressive CPU issuer and a native CPU verifier with a Metal-trained head.

On the three teacher trajectories the recurrent policy recovered 113/1,668, 143/1,419 and 623/17,341 distinct commits. With identical sequence weights and only the first wave allowed, the counts were 111, 139 and 607. Subsequent waves therefore recovered 22 additional commits across the three workloads, for 158,942 additional issued requests (161,133 total vs. 2,191). On loopfact Run 79 the complete decoder issued 512 requests and recovered five of 74 teacher commits; the other 507 matched already credited commits.

### Receiving verifier outcomes between waves

The optional native `online-waves` protocol accepts proposals for the sealed source Run and returns the status of each paid request before the next wave. The receiver checks the named parents, the rule watermark, primitive guards and the native signed input key. It keeps the accepted Instance for the ordinary rule-order commit. Each request is checked once in exclusive execution, and no RHS effect is made visible early. The source dirty check remains authoritative. In `shadow-waves` separate model admission and teacher replay let the policy receive truthful verdicts on a fixed teacher trajectory. The diagnostic repeats the named proof check to match the proposal to a committed teacher binding. Shadow timing includes this additional work. Teacher identity is withheld from the actor. Streaming with a frozen actor reproduced the ordinary exclusive receiver's schedule, RHS, writes, graph hash, accepted/rejected/read counts and issuance on fact, loopfact and sum-divisors.

A residual layer was fit on MPS for 512 updates. At a full wave boundary it reads the prior recurrent state and counts of accepted, duplicate and rejected requests. It changes the continuation state used to select the next rule or Stop. The parent decoder and all earlier parameters are frozen. Training uses 432 snapshots from 50 training programs, with 1,014 model proposals individually checked on the corresponding native teacher prefixes. Branches interleave verified model requests, teacher requests and repeated certificates. Completion labels refer to the remaining distinct teacher bindings. Training examples include 4,274 waves with duplicates and work outstanding, and 1,014 with duplicates and the reference set already exhausted. Fitting uses one-step continuation loss on these branch states. It does not learn parent selection or identify which individual port caused a rejection.

The [per-Run recall and native results](run-recall/receipts) include the receipt-masking control, receiver parity, and separate exclusive and shadow outcomes. The masked fact trajectory reproduced the previous sequence policy's entire per-Run recall CSV. For the trained policy, three synthetic holdout groups still had zero correct final graphs. Free execution also continued to diverge on the two fact programs and sum-divisors. No paired speed measurement was made.

Build the release receiver as above and run `train_receipts.py ROOT RECEIVER SEQUENCE_CHECKPOINT OUT`. For each native workload run `run_recall.py ROOT RECEIVER OUT/model.pt OUT/live-WORKLOAD --workloads WORKLOAD`. The receipt checkpoint selects the streaming protocol by default. Run the fact control with `--mask-receipts`. Run the frozen sequence checkpoint on fact and loopfact with `--live-receipts --wave-limit 1`. The legacy batch protocol remains available for the sequence checkpoint. Use `anchor_audit.py` for exclusive results and `evaluate.py` for the four-split comparison. The snapshot-only parent-address diagnostic in the latter has no within-Run feedback; use the streaming recall evaluation to measure the feedback-conditioned policy.

For the input-selection ceiling, `run_recall.py ... --oracle-rules` supplies every rule that actually committed in the reference Run. It tries the frozen parent pointer once for every lane and rule and measures distinct native binding hits. This diagnostic receives privileged rule choices and is reported only as assist. For this architecture each lane's parent choice for a given rule depends exclusively on the sealed snapshot. Repeating waves can change the rule but cannot add a fifth parent tuple for that rule. The oracle measurement preserves the entire renamed port history, including empty Runs, so the pointer sees the same tie order. Generate the control under `OUT/oracle-complete-history`. Run `wave_parity.py ROOT RECEIVER SEQUENCE_CHECKPOINT OUT/native-parity.json --workloads fact loopfact sum-divisors` for the transport equivalence check, then `receipt_results.py OUT run-recall/sequence run-recall/receipts` to archive results.

For teacher protocol parity, run the same `wave_parity.py` command with `--teacher --workloads sum dot fact loopfact sum-divisors` and output `OUT/teacher-parity.json`. All 34,397 teacher requests were accepted and the audit matched the reference Run by Run, including the sum-bits repair event. Save the repository's sum-bits `choice_diagnosis.py` report as `OUT/sum-semantic.json`. The controls check transport parity for the frozen actor and reconstruction of the native reference graph by the teacher.

| Held native workload | Recovered / teacher before → after live feedback | Issued before → after | Frozen parent ceiling given oracle rules |
|---|---:|---:|---:|
| fact | 113 → 112 / 1,668 | 16,596 → 2,151 | 461 / 1,668 |
| loopfact | 143 → 148 / 1,419 | 19,905 → 3,757 | 483 / 1,419 |
| sum-divisors | 623 → 665 / 17,341 | 124,632 → 17,812 | 2,355 / 17,341 |

The number of completely recovered busy Runs stayed at 6, 19 and 53, respectively. In exclusive execution all three still first diverged on Run 2. On loopfact Run 79, live feedback recovered six of 74 and spent 512 proposals, of which 440 were duplicates and 66 failed verification. The frozen parent ceiling for that Run was 19/74 even when each correct rule was supplied.

### Sequential parent-history control

The parent pointer reads counts of its own pending requests and native verdicts at
the candidate port and, for subsequent roles, at that port with the selected
prefix. The rest of the receipt checkpoint is frozen. Run
`train_parent_history.py ROOT RECEIVER RECEIPT_CHECKPOINT OUT` then
`run_recall.py ROOT RECEIVER OUT/model.pt OUT/live --workloads loopfact fact`.
MPS fitting used 4,577 history-sensitive pointer reads. On sealed teacher Runs
the CPU policy recovered 148/1,668 commits on fact (8 complete busy Runs)
and 158/1,419 on loopfact (19 complete). Loopfact Run 79 rose from 6/74 to
13/74 at the same 512 issues, with 357 duplicates and 142 rejects. The remaining
61 commits and the long decision chain motivate the parallel-anchor experiment.
These [two shadow trajectories](run-recall/parent-history) measure the trained
sequential control. They do not establish an exclusive final graph or a speedup.

### Parallel anchor decoder and symbol ablation

Each scheduled rule reads its sealed, typed port snapshot. Train a binary issuance
score at every delta anchor, then multilabel pointers conditioned on the entire
selected prefix. The first fresh atom in source order owns the witness tuple.
Non-seminaive rules use their first table atom and zero-parent rules have a
separate issuance decision. All complete requests still pass named native
verification. Test one batch per Run, with no current-Run facts or verifier
search. Report per-Run teacher commit recall, completed busy Runs, duplicate
and rejected requests, and exclusive divergence. On loopfact Run 79 also measure
remaining **complete tuple** precision and recall with correct rules and anchors
supplied, separately from the end-to-end result.

The symbol experiment holds the decoder, declaration graph, splits, seeds, optimizer,
sampling, compute budget and decision thresholds fixed. Compare three treatments:

* **Named** adds a learned hashed user-name embedding to each table and opaque sort declaration.
* **Renamed** uses the same number of parameters, consistently pseudonymizing user
  names on every training exposure. Include fresh, fixed renamings at evaluation.
* **Structural** omits that embedding. Preserve anonymous same-table and same-sort
  links, ordered parameter and result positions, primitive identity, literal
  contents, operation and sort kinds. The vocabulary comes from training data.
  Tables with identical types can still differ by how rules use them. A symmetry
  of the encoded graph can leave two declarations indistinguishable to the GNN.

Export parameter counts, bucket exposure and collisions, rename sensitivity and
the program/merge/result-position holdouts. Compare the two EggCC held programs
separately. A static exposure audit or invariance under renaming alone cannot
establish that removing names improves recall. The existing hash Actor has a
different graph and serves as a historical reference outside the matched ablation.

Three arms used seed 1703 and the same 242 training and 50 calibration snapshots
from 48 generated programs plus sum-bits and dot. Each made 348 AdamW updates
on MPS. All three used 60 semantic categories and the same initialization of
common parameters. Named and renamed have 284,454 parameters each, structural
has 22,310. Each CPU evaluation used one batch per Run and native named-port
verification with independent search disabled. Each non-anchor role reads the
prefix selected so far, so the batch contains successive layers for higher arity.

| Symbol treatment | Held program, calibrated / fixed | Held merge, calibrated / fixed | Held result position, calibrated / fixed |
|---|---:|---:|---:|
| Named | 23 / 45 | 27 / 43 | 0 / 26 |
| Renamed each exposure | 0 / 29 | 0 / 27 | 0 / 16 |
| Structural | 37 / 26 | 42 / 14 | 18 / 7 |

Each entry counts correct exclusive final graphs out of 48 in that split.
The fixed control uses a logit cut of zero (sigmoid 0.5) at all levels.
The calibrated control uses the same training-only F1 selection procedure on
the same reads, yielding different cuts for the three treatments. The ranking
reverses between these controls. This single-seed result supports name
invariance and a smaller model. It leaves the generalization advantage open.

On loopfact Run 79 each calibrated treatment recovered 0/74. At the common fixed
cut, named recovered 3, renamed 9 and structural 5. Supplying every actual
multi-parent anchor still yielded no complete packet for the 56 multi-parent
teacher commits under either threshold choice. Precision is undefined with zero
packets. For structural, even with every correct intermediate prefix supplied
and the count of true children given at each read, only 10 of 64 next-parent
labels ranked in those top positions. This teacher-only ranking diagnostic gives
no issuance credit. On loopfact, renaming the declarations changed 12,210 of
13,565 node embeddings in the old receipt Actor. The trained structural model
changed none of its 13,666 node embeddings. Its two GNN steps assigned only 296
distinct embeddings to 401 table declarations. That tie count applies to the
declarations; dynamic port keys and static type masks retain other distinctions.

Reproduce with `train_anchor_set.py ROOT OUT`. For each treatment directory
`MODE` run `run_recall.py ROOT RECEIVER MODE/model.pt MODE/live --workloads fact loopfact sum-divisors`
and `anchor_audit.py ROOT RECEIVER MODE/model.pt MODE/exclusive.json`. Use
`evaluate.py` with the three generated holdout splits and `--snapshot-count 3`,
saving `held.json` and then `held-fixed.json` with `--fixed-threshold 0`.
Run `anchor_set_audit.py ROOT RECEIVER MODE/model.pt MODE/run79.json --case loopfact --runs 79`;
repeat with the common fixed cut as `fixed.json`. For `plain-probe.json` and
`rename-probe.json` use `--case loopfact --case random/held_merge-40536-1 --runs 3 79`
and add `--rename 993` to the second invocation. Use `symbol_symmetry.py ROOT MODE/model.pt MODE/symmetry.json --cases loopfact fact random/held_merge-40536-1`
for declaration ties and `anchor_set_results.py OUT run-recall/parallel-anchors`
to assemble the matched per-Run ledgers. These are model-quality experiments.

The training BCE uses the ports named in the teacher proofs. A different
certificate for the same binding may have been labeled negative. Native recall
credits such a certificate once. For the calibrated structural treatment,
9 of the 53 recovered fact commits and 5 of the 54 recovered loopfact commits
were recovered only through an alternate certificate. This is a measured
mismatch between pointer supervision and the verifier's acceptance criterion.

Across the 20,428 held EggCC reference commits, the calibrated single batches
recovered 405 named, 457 renamed and 484 structural. The structural model
completed 5/163 busy Runs on fact, 4/166 on loopfact and 5/627 on sum-divisors.
All nine exclusive EggCC trajectories first diverged on Run 3. The previous
multi-wave receipt policy recovered 925 commits on those same teacher snapshots.
The [per-Run counts and matched controls](run-recall/parallel-anchors/summary.json)
include mode-specific receipts and diagnostic timings.

### Native credit for alternate parent proofs

The offline miner varied one named parent of a teacher packet at a time. Each
substitution had to verify as the same distinct native commit at the same source
Run. On the sampled training trajectories 1,098 of 1,827 commits admitted at
least one such substitution, giving 38,701 verified alternatives. All retained
their first fresh atom, and all changed the learned port key. Live decoding sees
the ordinary sealed port memory. Mining and receiver verdicts provide training
labels only.

The following CPU single-batch shadow measurements cover every teacher Run of
fact, loopfact and sum-divisors, with 20,428 total commits and 956 nonempty Runs.
Training used MPS. A positive address can prove the same commit as many other
addresses. Expanded BCE credits each positive. The grouped loss awards a
commit its strongest verified positive. The last treatment starts from the
expanded model, freezes all weights and thresholds, and fits one nonnegative
coefficient on the worst shared-field discrepancy using exact verdicts on
training-program substitutions. Its 10,784 supervised reads include 3,285
positive reads, all with agreeing shared fields, and 925 rejected reads with
agreeing fields. Field agreement alone cannot certify a packet.

| Supervision or treatment | Distinct commits | All proposals | Complete nonempty Runs |
|---|---:|---:|---:|
| Canonical proof | 484 | 523 | 14 |
| All verified addresses | 1,509 | 30,771,180 | 63 |
| Grouped by committed binding | 1,054 | 22,889 | 71 |
| Expanded model with learned field penalty | 1,509 | 64,604 | 63 |

On sum-divisors Run 709, the expanded model issued 3,293,096 complete packets.
The field penalty reduced issuance to 27, yielding 6 distinct commits and 21
duplicate matches out of 26 required commits. On loopfact Run 79, giving the
correct multi-parent anchors recovered 18/56 with either treatment. Natural
issuance recovered 1/74. All three held EggCC exclusive rollouts of the
corrected model diverged at Run 3. On generated exclusive holdouts the
corrected model reproduced 46/48 program graphs, 47/48 merge graphs and 44/48
result-position graphs.

Two negative controls locate the remaining uncertainty. A linear-attention
anchor read over sibling domains recovered 264 and 230 distinct commits on
fact and loopfact, compared with 258 and 224 under the matched blind control.
Training one positive path per observed template entry increased entry exposure
from 145 to 372 but recovered only 609 held EggCC commits and reproduced zero
of the 144 generated holdouts. A separate threshold calibration on 50 reserved
training Runs raised calibration F1 from 0.138 to 0.203, recovering 50 of 332
commits versus 72 before calibration. These controls have separate held
measurements, thresholds, and costs in the [native report](run-recall/alternate-proofs/summary.json).
Coverage measures distinct teacher commits. These runs supply no EPT or paired
end-to-end speed result.

Reproduce the labels with `alternate_proofs.py ROOT RECEIVER LABELS`. Train
with `train_anchor_set.py --help` for the verified-alternative and grouped
credit options. Run `train_disagreement.py ROOT RECEIVER EXPANDED_MODEL OUT`
for the frozen-pointer treatment. Use `block_recall.py` for streamed native
scoring of all requests, `anchor_set_audit.py` for supplied anchors,
`prefix_fanout.py` for the per-layer widths and `anchor_audit.py` for exclusive
execution. `alternate_results.py EXPERIMENT BASELINE OUT` checks weight and
receiver hashes and combines the per-Run ledgers.

### Bounded frontiers, optional native prefix verification, and the anchor gate

The frozen disagreement Actor scores each typed, seminaively eligible extension
of a prefix. `--top-k 32` keeps at most 32 passing prefixes per scheduled rule,
anchor role and depth, across all score tiles for that frontier. A tie crossing
the budget is dropped as a group, which makes the choice independent of memory
order. K=32 is an experimental budget. Every independent input in a completed
request still names a token, instruction position and version.

`online.py --verify-prefix` enables the optional native check after selection.
The receiver resolves exactly the addresses supplied and binds fields using the
same native Values and operand checker as complete certificates. Its reply is
one Boolean per proposed extension. A false reply ends that prefix. Scoring of
any surviving prefix receives the frozen snapshot and its chosen parents.
Partial checks cannot sign a binding, return another parent, look up partners or
expose new Run facts. Complete requests still go through ordinary admission.
The report separates partial address reads, complete packets and diagnostic times.

| Three held EggCC teacher trajectories | Full proposals | Distinct of 20,428 | Complete of 956 nonempty Runs |
|---|---:|---:|---:|
| Learned field penalty, unlimited frontier | 64,604 | 1,509 | 63 |
| Same, K=32 at every depth | 3,980 | 1,428 | 46 |
| Same K, native partial checks enabled | 3,952 | 1,428 | 46 |

The per-Run identity differences attribute 3 lost fact commits, 4 lost loopfact
commits and 74 lost sum-divisors commits to K. Native partial checks removed
1/2,444, 86/1,937 and 46/16,123 selected partial prefixes respectively. The
sets of recovered commit identities were identical with the native check on and
off. Across 2,461,303 scored partial extensions on the K=32 trajectories with
checking disabled, 746,628 had at least one conflict between the exported
64-bit hashes of statically shared fields. Zero crossed the model threshold.
This diagnostic includes only visited frontiers and measures hash disagreement.
The native partial check also covers literals, repeated slots and row validity.
Exclusive EggCC trajectories in both bounded arms first diverged at Run 3.
The two arms reproduced 46/48 generated program graphs, 47/48 held merge
graphs and 44/48 held result-position graphs.

On sum-divisors Run 709 the old field scorer let 2,590 of 34,450 shared-field
conflicts pass its threshold on the frontiers it visited with K and native
checks. After K, the receiver pruned 279 of 472 partial prefixes. Under the
learned penalty it saw 35,102 conflicting extensions on its own frontiers,
passed zero of them, and the receiver pruned 0/203. The original five-parent
branch went from 7 anchors and 321 first extensions to 7 anchors and a single
first extension before applying K. The unbounded corrected model and both
bounded treatments recovered the same 6/26 commits on Run 709.

The loopfact Run 79 anchor diagnostic attributes the first miss in 73/74
canonical teacher certificates to the anchor threshold. With K=32 the
unchanged policy issued 8 packets and recovered 1 commit. Opening only the
anchor threshold while retaining learned ranking, the same K, parent scores
and normal final verification produced 97 packets and 37 distinct commits.
This selected-Run intervention received no teacher anchors. The separate
teacher-anchor control recovered 18 of 56 multi-parent commits. At Run 3,
two commits depend on one canonical anchor scoring -0.448 against a 1.001
threshold. Supplying that anchor recovers only one of the two commits.

Build the receiver with the same Cargo features as the alternate-proof study.
Use `prefix_study.py ROOT RECEIVER WEIGHTS OUT --case NAME` for live, teacher
shadow replay. Add `--top-k 32`, then `--verify-prefix` for the two treatments.
On targeted Runs add `--runs R --audit` to classify the entire scored matrix
after scoring, including rejected choices. For the anchor intervention select
`--runs 3 79 --top-k 32 --open-anchor-gate`. `prefix_field_audit.py` records
post-score conflicts over the full capped workload. `prefix_exclusive.py`
runs the bounded Actor on its own three EggCC and 144 generated held trajectories.
`anchor_gate.py` traces the first missed choice of each canonical proof.
`check_prefix_policy.py` checks budget ties, unknown addresses, stale versions
and the absence of graph effects from a partial check. The
[per-Run measurements](run-recall/prefix-policy/summary.json) include hashes,
receiver reads, rejections, duplicates and diagnostic time. No paired speed
measurement was made.

### Calibrating anchors and assigning credit to the final named parent

A nonempty anchor of a one-parent rule immediately issues a proof. A
multi-parent anchor starts a read that can still fail. The calibrated Actor
adds one scalar bias to each of these two decisions. It selects the pair on
50 reserved Runs of training programs using native distinct-winner F2,
`5 * recovered / (4 * required + issued)`. The parent scores, zero-parent
gate and K=32 frontier budget remain fixed. Complete requests include all
independent parents. The partial verifier is off throughout this comparison.

On training-program data, the new terminal head sees 523 sampled teacher
prefixes and 199 perturbed prefixes. Each training matrix contains the whole
typed, visible domain of its last parent. The native replay receiver checked
221,770 complete named requests, including 14,624 verified matches, 207,126
binding rejections and 20 guard rejections. Several ports can certify the same
commit. Training rewards its highest-scoring proof, charges other likely proofs
of the same commit, and trains against the highest-scoring actual rejections.
MPS fits the terminal head in 512 updates. The preceding gates, template and
port encoders remain frozen. Inference runs on one CPU thread.

The opaque encoding removes absolute e-class hash bits from address-local
content vectors for both current and inherited port fields. The compiler's
column sorts determine these positions. Scalars keep their existing content
encoding, and shared-column comparisons still use the separate 64-bit fields.
Both terminal treatments use the same sampled prefixes, native labels,
optimizer budget and input checkpoint. A common XOR mask applied to every
opaque hash preserves all same-sort binary field dot products. Across five
programs, five chosen Runs and three masks, the raw terminal Actor changed
its named proof set in 51 of 75 interventions. The opaque model changed zero.
This measures invariance to a simultaneous bitwise change of coordinates.
In a stronger intervention, an invertible permutation also changes distances
between unequal class codes. That changed 6/75 issued sets for the recalibrated
opaque Actor. Its field scorer still uses those distances.

The calibrated root increased conditional reach while leaving terminal
quality fixed. On loopfact Run 79, supplying correct roots recovers 18/56
multi-parent commits before terminal training and 53/56 after it, with 50
and 175 full requests respectively in this supplied-anchor diagnostic. The
trained raw model's natural K=32 issuance recovers 65/74 on that Run.
Independent verification gives one credit for each distinct committed binding.

Across all 20,428 held EggCC commits on the teacher trajectory, the controls gave:

| Policy, K=32 | Full proposals | Distinct commits | Complete nonempty Runs of 956 |
|---|---:|---:|---:|
| Frozen field scorer | 3,980 | 1,428 | 46 |
| Anchor calibration | 16,108 | 5,008 | 119 |
| Add native terminal-parent training | 33,917 | 9,923 | 256 |
| Matched terminal training with opaque content | 28,226 | 9,928 | 243 |
| Recalibrate anchors with the opaque terminal scorer frozen | 32,056 | 10,824 | 347 |

The last model recovered 1,248/1,668 fact, 1,031/1,419 loopfact and
8,545/17,341 sum-divisors commits. Its anchors activated 3,054/3,095
productive rule/Run pairs among 13,911 activations. Only 13,946/20,428
commits retained their canonical teacher anchor. Alternate addresses may
also prove a commit. Free execution first differed on Runs 7, 8 and 11
respectively. The last trajectory then hit an original source panic on
Run 85. There was no successful final export for this trajectory.
At its first difference, 28/36 distinct commits were proven by 35 actual
packets. Raising K to 128 gave the same 28. On the same private state,
relaxing only the anchor threshold gave 34/36 from 44 packets. Relaxing
both pointer thresholds gave 36/36 from 146 packets, including 109 binding
rejections. This selected-Run intervention is charged separately.
The raw trained terminal treatment reproduced all 144 generated exclusive
final graphs, and the recalibrated opaque treatment reproduced 143/144.

The [native ledger](run-recall/parent-credit/summary.json) separates pre-completion
rule selection, exact teacher anchor addresses, recovered bindings by arity,
full proposals, duplicates, rejections and complete nonempty Runs. The CSVs
compare actual winner identities at each source boundary. Exclusive rollouts
use the policy's own generated ports with independent search disabled. A
source panic fails the rollout; its costs are recorded separately from replay
of the completed prefix preceding the failure. The sum-bits choice contract
and the five-program teacher receiver control remain those of the preceding
prefix study. The quality ledgers supply no paired speed or EPT measurement.

Reproduce the calibrated model with `calibrate_anchor.py ROOT RECEIVER BASE OUT`
and train the terminal model with `train_final_parent.py ROOT RECEIVER OUT/model.pt TERMINAL`.
Repeat terminal training with `--opaque` for the matched representation ablation.
Run the same root calibration on the frozen opaque model. For each model,
`prefix_study.py --case NAME --top-k 32` and `prefix_exclusive.py --top-k 32`
provide shadow and exclusive execution. `rule_issuance.py` measures activity
immediately after anchor selection. `eq_hash_intervention.py` changes only
opaque field coordinates. `first_boundary.py` remaps actual, earlier native
results to corresponding teacher commits to audit the first exclusive failure.
`boundary_gates.py` varies the root threshold, parent threshold or frontier
size on that same reached snapshot. All these proof-correspondence and
counterfactual checks run offline.

### Live neural assistance and the cost of residual matching

The evaluated checkpoint is the recalibrated opaque Actor (weight SHA beginning
`13e209c6`). Both root-offset sweeps used the same 50 reserved Runs of 21
training programs. The terminal heads used the two training EggCC programs
and 48 random training programs. Of 221,770 receiver-labelled extensions per
treatment, 100,599 came from sum-bits, 120,502 from dot-product and 669 from
random training programs. [The split audit](run-recall/assist-cost/training-split.json)
checks compiled and source identities, tape digests, checkpoint ancestry and
snapshot membership. Fact, loopfact and sum-divisors have been consulted
throughout architecture development. They measure development holdout performance.

In the live `assist` receiver a wave issues complete named proofs on the
pre-write snapshot. The receiver verifies their actual premises. The source
executor retains rule order and orders the RHS bindings. For rules with at
most one table atom, the number of distinct verified projections can prove
that all possible outputs are covered. A nonempty certified frontier skips
the exact query and resumes the usual Cell continuations. Other rules perform
ordinary matching and retain source continuations, with named certificates
supplying the witnesses for overlapping bindings. Exact-only bindings receive
separate token IDs and actual result receipts. Both kinds of completed token
are visible to the following Run. This treatment uses the real native graph,
a single CPU policy thread and no teacher tape during assist execution.

On the three full programs the receiver accepted 10,840 distinct neural
requests and the residual contributed 9,588 commits. There were 18,833
duplicate proposals, 2,752 rejections and 4,763 named reads on the rejected
requests. Exact queries still returned 20,100 bindings. Only 73 rule
invocations certified complete coverage. The exact residual-candidate
counter totaled 26,167 in both native paths. A signed commit and an avoided
search have different denominators. Each program passed comparison of its
ordered schedule, RHS, writes, resumes, events and final state.

`assist_cost.py ROOT BINARY WEIGHTS OUT --cases fact loopfact sum-divisors`
runs full semantic audits followed by alternating end-to-end comparisons.
The process wall includes native startup, parsing, final export and transport.
The Python service and PyTorch runtime are warm, and the model is loaded
anew for each trial. The inference column covers model encoding and proposal
generation. The assist search timer covers calls to the native matcher.
Costs outside those intervals include the pre-write memory export, Python
snapshot maintenance, IPC and ordinary execution. The receiver also times
duplicate and rejected requests inside verification. The native oracle series
uses the original `token-replay/study.py` in-memory timer, which excludes
program and tape decoding and final export.

The [training controls](run-recall/assist-cost/policy-ablations.json) use the
policy's own history. A first experiment fitted the existing root bias and
final pointer on the first incomplete private snapshot of each training EggCC
program. The native receiver labelled 1,394 named requests across 91 possible
anchors. These included alternatives for all 11 missing commits. After 64 MPS
updates, full held snapshot recall fell from 10,824 to 10,131 of 20,428.
Exclusive execution also diverged earlier on two of the three programs.
The cost comparison retains the original checkpoint.

A second experiment collected live assist receipts on the first 128 Runs of
each EggCC training program. Each rule uses its frozen template embedding,
typed visible and fresh port counts, and the time since its previous confirmed
commit. The following Run supplies labels for the preceding predictions.
A shared MPS-trained head screens scheduled rules before parent decoding.
Across the first 128 Runs of each held EggCC program, productive activations
were 833/4,226 without the screen and 833/4,056 with it. The counts of checked
proposals, duplicates, rejections and signed commits stayed the same on each
workload. All 144 generated holdouts passed complete native assist comparison.
This one round of training on actual assisted states excluded 170 fruitless
starts and provided no reduction in verifier traffic on the measured prefix.

The [paired CPU timings and native work counts](run-recall/assist-cost/README.md) cover all three full EggCC workloads.

The [sealed-domain assist experiment](run-recall/assist-domains/README.md) compares full-run signed streams, complete-domain checks, residual search costs and independent rollouts with the frozen Actor.
