# Local port equivalence from typed eggcc rules

A certificate identifies two concrete ports of the same sort on one bound producer instance, the source `union` instruction and the condition `producer_committed`. The neural fixture's stage 0 reads before that producer completes. Stage 1 reads the published equality after the producer and its repair. Physical port references still identify their original port and owner. No unconditional rule follows from the spelling or sort of the surrounding expressions.

## Provenance and admission

The sum-bits and Raytrace typed programs rebuilt for the preceding port study carry the same relevant rule bodies. Neither installed program contains a `local_union_cells` selection. The actual union instructions and their producer scope provide the evidence here. The previous corpus's 19 baked boundaries divide into 11 with no explicit producer union, two whose selected publication omits both union operands, and six whose published result is one endpoint. All six refer to the same producer, eggcc rule 143. It constructs `Single(Get(expr,i))` and `SubTuple(expr,i,1)` and then unifies their two `Expr` results. The `Get` argument, the owners and their physical witness handles have separate meanings.

To test generalization beyond that one body, the corpus reuses more typed source rules from the two frozen Pass 3 programs. Of the ten modeled bodies, rule 143 is a previously selected composed producer. Rules 266, 267 and 317 also occur as Spine leaves. The six remaining bodies are source-recipe extensions. Their presence in eggcc and their replay are verified separately from Bake selection. The `provenance` fields list the recipe hashes and the relevant selection in each catalog. This corpus uses real rule bodies with small controlled Runtime inputs rather than a full workload replay.

`replays.py` builds a minimal fixture with the original textual eggcc rule, the relevant typed table declarations and probe relations. The exporter requires its observed query and effect instructions, including operand order and all slot sort/definition pairs, to equal the original typed body. A physical observation records each distinct same-sort value by its original typed operand or constructor expression. Repeated `Copy` operands and exact duplicate constructor applications resolve to that same value. Each admitted union then identifies its two original SSA operands in this observed interface. The graph still contains the original operations and SSA slots, with edges recording their provenance.

The suite tested 17 rule bodies. Two lacked a third distinct observed port of that sort; five more had a third port that was an already-shared zero-argument constructor across the two test instances. They remain in the replay evidence and do not enter training. Ten bodies have two certified endpoints `p,q` and a control port `r` with six actually independent pre-commit values across the two instances. The API lists `public_ports` in physical order. Model code must obtain the local alias pair from `certificates`, never from a `p,q,r` convention inferred from list positions.

## Whole-family split

The split holds out rule 143's two-sibling-output union and the mirrored rules 134/135 from `Concat` and `Empty`. The remaining seven rules form five training families. All three held-out rules belong to two wholly withheld structural families. The family signature uses directed role and edge labels while dropping node numbers, source names, literal values, sort names and port ordinals. Its color refinement may group extra non-isomorphic graphs on the same side. `check.py` explicitly permutes every rule's nodes, types and ordinals and verifies the same family. The neural graph retains typed slots and local operand order. Neither numeric rule IDs nor template family hashes occur among its numeric features.

## 135 semantic replays

The first 35 actual Cell CPU programs compare the full finite partition of the tagged ports and all downstream observer reads. Each of the 17 producer bodies has an executed and a withheld schedule. Rule 145 adds another control: `SubTuple(expr,0,len)` and `expr` remain separate when `tuple-length(expr)` does not equal `len`, even if the producer ruleset is scheduled. In positive examples both instances match and publish the intended union. In the withheld programs the ruleset is absent from the schedule. The trimmed compiler may omit unreachable rules from those outputs. The actual executed positive source matches the typed production body.

The 100 additional replays cover every modeled body. In one case per body, only owner 1's source facts are available when its producer runs. A later `reveal` Run creates owner 0's facts before the observer executes. This verifies a snapshot with two visible instances and a local certificate active on just one. It does not claim that the native scheduler selectively skipped a fully visible matching producer binding. The remaining nine cases per template enumerate every `p/q/r` pair across two locally committed owners, execute an additional real external union, and then execute the observer. Independent source checks compare the full six-port partition and the consumer output on each boundary. The offline checker also closes actual same-table constructor signatures from the previous boundary, then compares the result with the real post-union graph.

Nine of the 90 external events cause additional congruence. For both delayed-union rules 266/267, joining either local endpoint on each side makes the two sets of `Delayed…Union` constructor operands equal. Consequently the two constructor results `r0,r1` merge as well. For `TypeListRemoveAt` rule 580, joining the two `TCons` results (`r0,r1`) makes `TypeListRemoveAt(r0,0)` and `TypeListRemoveAt(r1,0)` congruent; the preceding rule had unified each with its respective list tail. An update that only unites the external edge's two endpoints misses these cases. The derived closure and `secondary_congruence` belong to the offline audit/oracle. Model inputs can use the raw external event only.

## Reproducing the evidence

Use the external workspace's runtime executable `target/release/examples/real_completion_dataset` built with Cargo. Supply the two validated programs from the [prior Bake corpus](../../port_ablation/corpus/README.md). Run each executable step via the shared compute queue, waiting for completion before its dependent verification step.

```sh
base=benchmarks/multi-row-generation/eclass_ablation/corpus
art=/Volumes/EggFuseWorkspace/experiments
sum=$art/port-ablation-program-sum-20261119/program.json
ray=$art/port-ablation-program-ray-20261119/program.json
python3 "$base/replays.py" "$sum" "$art/eclass-rule-replays-input-v2.json"
target/release/examples/real_completion_dataset "$art/eclass-rule-replays-input-v2.json" "$art/eclass-rule-replays-v2.json"
python3 "$base/export.py" "$sum" "$ray" "$art/eclass-rule-replays-v2.json"
python3 "$base/instance_events.py" build "$sum" "$art/eclass-all-events-input.json"
target/release/examples/real_completion_dataset "$art/eclass-all-events-input.json" "$art/eclass-all-events-output.json"
python3 "$base/instance_events.py" verify "$art/eclass-all-events-output.json" "$base/extra-events.json"
python3 "$base/check.py" "$sum" "$ray"
```

`replay-evidence.json` records 35 source/program hashes and before/after classes. `extra-events.json` records 100 actual dynamic cases, their physical endpoints, any secondary congruence and observer rows. In these audit files only, a physical port is encoded by `owner * 16 + template-local port`. `validation.json` records split, admission, replay counts and file hashes. Original large Rust outputs remain on the external volume. Successful producer jobs were 1056 and 1060.
