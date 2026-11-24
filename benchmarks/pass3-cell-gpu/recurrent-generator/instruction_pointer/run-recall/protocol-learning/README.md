# Learning Cell Communication Protocol v0.1

Exclusive Neural Execution in the standalone EggFuse Cell CPU executor. Each workload ran under four policies with four repetitions. All arms use the same frozen native verifier, protocol, field retrieval keys, LSH and recurrent Compose weights. No residual exact search supplies a proposal.

| Group | Computation and decisions |
|---|---|
| A | Published v0.1 hash-response policy and fixed source-Run seal. All arms use the existing chain routing checkpoint on strided fixtures. |
| B | A plus typed READ and COMPUTE observations, a shared value encoder, a learned residual on the final proof score, and a head that chooses the direct or computed-evidence retrieval bucket. A named READ observes column zero of a visited final-role port on demand. The port embedding is reused until version change or retirement. |
| C | B with a learned instruction/operand/STOP decoder. It sees individual primitive instructions, named fields, literals and earlier scalar outputs of compatible sort. It builds one program per rule role in the current stream and applies it to selected prefixes. The host packs the references. Only the offline imitation teacher constructs complete candidate programs. |
| D | C plus learned observation masks and an Observe/Submit/Seal controller. At a proof block, every 16 scheduled rules, and at exhaustion, the policy can submit buffered proofs, collect pending receipts, continue, or seal. A learned early seal gives up the rest of that source Run. Mandatory capacity flushes, operand waits, first-field READs, batch packing and the exhaustion fallback remain explicit. |

The value encoder takes exact tagged bytes. Features include type, length, eight positional bytes, and a position-sensitive pooled representation using the entire payload. Text, sets and structural keys enter through the same interface. Its finite embedding can have collisions. Separate projections encode static template metadata and dynamic status/freshness. The retrieval key continues to use the frozen field encoder. Only observed fields receive a dynamic decision embedding.

## Training and test separation

Training on Metal used four generated CYK grammars and EggCC loopfact. Native checks of complete training proposals supplied candidate-level supervision on autonomous training trajectories, including proposals the previous final score would have rejected. The instruction head imitated static recipes for rules observed in the training tapes. The operand head had only four ambiguous demonstrations. Boundary labels came from future admissions in the training Run, outcomes of buffered proofs and observed queue states. Observation scope used the measured difference in the trained query head's loss with and without a value. These supervised targets approximate policy utility. Generated handles were relabeled in the neural cache namespace. No numeric owner ID enters a learned head. [Training and validation counts](training.json)

Seed 25112473 was withheld from training and validation. Its two-instruction version shares a trained layout. The separate three-instruction split layout was withheld from program training. CYK801, fact and sum-divisors have prior project history. The new heads did not train on these three. The inherited Compose checkpoint had previously seen EggCC, including fact and sum-divisors.

## Independent endpoints

Coverage counts distinct, visible reference derived facts, excluding initial facts. The full endpoint SHA was checked separately. EPT below charges every READ, COMPUTE and PROVE plus neural control outputs, including decoded program STOP, Continue, Observe, Submit, Seal, and observation-mask choice. Cache hits, rejections and duplicates are paid. The JSON also retains request-only EPT and counts internal instruction and operand selections. The numerator is the signed native effective-operation ledger on the realized trajectory. Divergent EggCC trajectories can perform work outside the aligned reference endpoint. EPT alone does not measure how much of that endpoint was reached. EPS uses inclusive online elapsed time including inference, routing, native checks, encoding, communication, publication and memory maintenance. Checkpoint loading and offline alignment/replay are excluded.

| Workload | Arm | Coverage | Signed ops | Requests | Neural controls | EPT incl. controls | Median EPS | Median wall, s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| [grammar-25112473](grammar-25112473.json) | A | 200/200 | 200 | 330 | 0 | 0.6061 | 4,006.7 | 0.0499 |
| [grammar-25112473](grammar-25112473.json) | B | 200/200 | 200 | 402 | 0 | 0.4975 | 3,733.7 | 0.0536 |
| [grammar-25112473](grammar-25112473.json) | C | 200/200 | 200 | 402 | 50 | 0.4425 | 3,588.4 | 0.0558 |
| [grammar-25112473](grammar-25112473.json) | D | 200/200 | 200 | 402 | 97 | 0.4008 | 3,480.1 | 0.0575 |
| [grammar-stride2-25112473](grammar-stride2-25112473.json) | A | 200/200 | 200 | 616 | 0 | 0.3247 | 4,298.3 | 0.0466 |
| [grammar-stride2-25112473](grammar-stride2-25112473.json) | B | 200/200 | 200 | 704 | 0 | 0.2841 | 3,725.9 | 0.0537 |
| [grammar-stride2-25112473](grammar-stride2-25112473.json) | C | 200/200 | 200 | 704 | 50 | 0.2653 | 3,770.5 | 0.0531 |
| [grammar-stride2-25112473](grammar-stride2-25112473.json) | D | 200/200 | 200 | 704 | 95 | 0.2503 | 3,539.2 | 0.0565 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | A | 256/256 | 256 | 984 | 0 | 0.2602 | 4,681.2 | 0.0547 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | B | 256/256 | 256 | 1,100 | 0 | 0.2327 | 4,198.3 | 0.0610 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | C | 256/256 | 256 | 1,372 | 50 | 0.1800 | 4,209.4 | 0.0608 |
| [grammar-stride3-split-7300147](grammar-stride3-split-7300147.json) | D | 256/256 | 256 | 1,372 | 89 | 0.1752 | 4,067.1 | 0.0630 |
| [cyk801](cyk801.json) | A | 6,567/6,567 | 6,567 | 50,257 | 0 | 0.1307 | 2,105.6 | 3.1189 |
| [cyk801](cyk801.json) | B | 6,567/6,567 | 6,567 | 55,201 | 0 | 0.1190 | 1,950.3 | 3.3676 |
| [cyk801](cyk801.json) | C | 6,567/6,567 | 6,567 | 55,201 | 254 | 0.1184 | 1,970.4 | 3.3338 |
| [cyk801](cyk801.json) | D | 6,567/6,567 | 6,567 | 55,201 | 583 | 0.1177 | 2,027.3 | 3.2394 |
| [fact](fact.json) | A | 363/1,120 | 562 | 9,954 | 0 | 0.0565 | 289.1 | 1.9446 |
| [fact](fact.json) | B | 227/1,120 | 387 | 1,121 | 0 | 0.3452 | 323.3 | 1.1973 |
| [fact](fact.json) | C | 227/1,120 | 387 | 1,121 | 690 | 0.2137 | 320.1 | 1.2091 |
| [fact](fact.json) | D | 182/1,120 | 330 | 885 | 1,001 | 0.1750 | 526.1 | 0.6279 |
| [sum-divisors](sum-divisors.json) | A | 1,404/8,018 | 2,024 | 376,873 | 0 | 0.0054 | 218.4 | 9.2670 |
| [sum-divisors](sum-divisors.json) | B | 770/8,018 | 1,044 | 4,676 | 0 | 0.2233 | 361.4 | 2.8891 |
| [sum-divisors](sum-divisors.json) | C | 770/8,018 | 1,044 | 4,676 | 877 | 0.1880 | 360.7 | 2.8945 |
| [sum-divisors](sum-divisors.json) | D | 670/8,018 | 926 | 3,203 | 1,315 | 0.2050 | 627.6 | 1.4757 |

The counterbalanced orders were ABDC, BCAD, CDBA and DACB. A wall win below is relative to A in the same repetition, at the arm's own achieved coverage. The exact and oracle columns are whole-process reference and teacher replay times. Divergent EggCC endpoints preclude a same-task speedup claim.

| Workload | B / C / D wall wins vs A (of 4) | Exact, median s | Oracle, median s |
|---|---|---:|---:|
| grammar-25112473 | 0 / 1 / 0 | 0.0103 | 0.0102 |
| grammar-stride2-25112473 | 0 / 0 / 0 | 0.0102 | 0.0103 |
| grammar-stride3-split-7300147 | 0 / 0 / 0 | 0.0114 | 0.0109 |
| cyk801 | 0 / 1 / 1 | 0.1463 | 0.0632 |
| fact | 4 / 4 / 4 | 0.1445 | 0.1475 |
| sum-divisors | 4 / 4 / 4 | 0.2306 | 0.2444 |

## Equal-coverage costs

For each **shared absolute reference-fact target**, the plot gives the costs of the first sampled Run boundary meeting it. Tokens, visits and wall seconds have separate axes. The first five Runs, up to twelve spaced boundaries and the endpoint were independently replayed and aligned. A sampled crossing gives an upper bound on the earliest possible crossing cost. The final point includes teardown. Across repetitions each arm reproduced its own endpoint, paid tokens and verdicts. [Cost curves](matched-coverage.pdf) · [Thresholds and raw costs](matched-coverage.csv)

## Feedback interventions

The weights are frozen in each intervention. In B the same-type substitution preserves observation availability and the tag, replacing a value with the preceding value of that type, when available. The other B control erases the typed input entirely. In D the control heads lose the latest value embedding and recent acceptance signal while retaining live queue information; its proof/value heads still see normal responses. Each number below is a final reference-fact count from one independent rollout. [Control measurements](interventions.json)

| Workload | B | B erased | B same-type replacement | Changed values | D | D control feedback erased |
|---|---:|---:|---:|---:|---:|---:|
| grammar-25112473 | 200 | 0 | 200 | 222 | 200 | 200 |
| grammar-stride2-25112473 | 200 | 0 | 200 | 99 | 200 | 200 |
| grammar-stride3-split-7300147 | 256 | 0 | 256 | 112 | 256 | 256 |
| cyk801 | 6,567 | 0 | 6,567 | 18,801 | 6,567 | 6,567 |
| fact | 227 | 32 | 232 | 257 | 182 | 181 |
| sum-divisors | 770 | 101 | 764 | 795 | 670 | 642 |

On CYK801, replacing 18,801 typed observations with earlier same-type values preserved every reference fact. Erasing all typed features reduced B to zero derived facts. This separates reliance on the observation channel from evidence of dependence on the specific value. The replacement also changed fact coverage from 227 to 232 and sum-divisors from 770 to 764. Erasing control feedback in D changed sum-divisors from 670 to 642. These interventions show some causal sensitivity and no consistent advantage over A.

C issued 74 native local edges on the unseen input with a two-instruction layout. On the unseen three-instruction layout it issued zero. The ordinary stream still reached the grammar's reference endpoint. The program builder conditions individual instruction choices on the static role and available operands. Typed feedback subsequently influences retrieval, proof scores and D's controls. This experiment does not establish general response-conditioned program synthesis.

Both EggCC workloads lost reference coverage under B, before autonomous boundaries were enabled. D lost additional coverage. On fact, B/C issued zero primitives on their own trajectories; their computational requests were named READs. Reaching schedule end on these divergent graphs did not reproduce the reference fixed point.

## Why historical CYK EPT increased

The numerator stayed at 6,567 signed effective operations. The older LSH baseline paid 1,072,213 proofs. With the computation route it paid 32,563 proofs plus 17,694 primitive requests, or 50,257 in total. EPT rose from 0.006125 to 0.13067. Computing the end of the left span before retrieving the right span reduced complete tuple scores from 1,072,460 to 32,810. The transport-only control reproduced the same proof tapes and EPT while changing the communication cost. Always-compute and random-projection controls captured most of the saving on this workload. The present typed-value model did not produce that historical gain. [Previous matched controls](../transactions/README.md)

## Reproduction

Use the frozen CCP release binary and existing recursive experiment artifact root. Run these commands from instruction_pointer. Rollouts use a single CPU Torch thread. Plotting needs matplotlib and NumPy.

~~~sh
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --extra-blind 25112473 --cases grammar-25112473 grammar-stride2-25112473
python train_protocol_model.py "$ROOT" "$OUT"
python protocol_experiment.py "$ROOT" "$OUT"
python protocol_intervention.py "$ROOT" "$OUT"
python protocol_curves.py "$OUT" grammar-25112473 grammar-stride2-25112473 grammar-stride3-split-7300147 cyk801 fact sum-divisors
python -m unittest discover
~~~

Each arm's JSON includes artifact digests, native verdicts and phase timings, candidate visits, complete tuple scores, index work, response encoding, named reads, cache hits, control decisions, synchronization counts and transaction size histograms.

[计算时机的反事实训练、同快照退化诊断与独立执行](../computation-benefit/README.md)
