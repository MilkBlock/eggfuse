# Typed transactions and computed field evidence

**Neural Execution, exclusive.** Single-thread CPU Torch inference, native Rust execution, offline PyTorch/Metal training. The experiment separates transport from candidate discovery. The control uses the previous shared 8-bit LSH with rule-watermark-aware postings and dense recurrent scoring inside each bucket. The new policy still enumerates the selected postings.

The measurements below use the original CTX1 transport. The current typed client defaults to [CCP v0.1](../../../../../../docs/CELL_COMMUNICATION_PROTOCOL_V0_1.md).

## Execution contract

The CPU decoder emits an integer tensor of selected positions per proof role. The typed client gathers owner/op/version columns, packs an i64 operation matrix and a separate i64 reference matrix, and submits both buffers through a synchronous pipe to Rust. One header declares matrix lengths. The normal online path has no per-proof Python dict or list conversion. The JSON control and the offline accepted-proof export retain their original object format.

Each operation names a rule and either a proof or a primitive instruction. Named field operands include a column and version. A local operand can refer to an earlier successful computation of the expected sort in the same transaction. A failed dependency rejects that operation. The transaction batches requests against one sealed Run snapshot. Each operation has its own status; proof effects become visible at the usual native commit boundary. It is possible to submit a mixture of proofs and computations in one buffer.

The immediate contiguous result matrix contains the request token, status, instruction and result hash. Status columns supply success and failure masks. On Run commit, the next frame publishes typed address/table/version/field-offset, hash, retirement and accepted-owner buffers. A small JSON header still carries the schedule and repair event metadata. Python maintains address maps and views into the received buffers; Rust still checks every proof. This is a copied, typed interprocess protocol. It is neither shared memory nor a GPU kernel submitting directly to Rust. [Wire encoder and CPU receiver](../../cell_transaction.py) · [Tensor issuance loop](../../transaction_native.py)

## What the model decides

Bake enumerates possible reads from the static rule: which primitive is legal, which already selected ports can supply its operands, and which later field can consume its result. The trained router estimates whether fetching that evidence will save bucket visits, considering the size of the direct bucket and plan shape. The baseline reads a shared field's 8-bit bucket. The computation route asks Rust for a named primitive result first, embeds the returned **hash**, and uses six learned projection bits alongside the original eight to read a smaller bucket. The recurrent Compose scorer then evaluates surviving candidates. All occupants of a selected bucket remain enumerable; the issue threshold is the same as in the LSH control. A failed computation falls back to the direct bucket. The code performs no raw-value equality join, candidate search in Rust, full-memory attention, or fixed top-K.

On CYK this lets the generator obtain the left child's end before it reads possible right children. Rust evaluates the addition specified by the template. The router chooses when to request it; the network does not learn arithmetic or synthesize arbitrary instructions. Only schema layouts with an existing direct link and available primitive operands expose this route. [Network and retrieval code](../../txn_policy.py)

Training used four generated grammars with disjoint seeds, renamed token addresses and teacher-accepted prefixes. The single-step head used 192 plan examples, 402 contrast pairs and 500 optimizer updates, fitting projected-address separation and a lookup savings target with a two-visit cost for computation. This is supervised training on an offline cost proxy. Validation used grammar 17122. The separate chained head added two grammars with two-primitive layouts. A third, withheld layout requires three primitives. Validation, evaluation and native outcomes are separate from the online neural observations. [Single-step checkpoint and training](single/training.json) · [Chained training](chain/training.json)

## Independent execution

| Workload / policy | Reference derived facts | Paid proof + compute | EPT | EPS (single run) |
|---|---|---|---|---|
| grammar-7300147 / typed-lsh | 256/256 | 1,214 + 0 | 0.2109 | 4,202.6 |
| grammar-7300147 / learned | 256/256 | 228 + 242 | 0.5447 | 4,062.8 |
| grammar-layout-832749 / typed-lsh | 151/151 | 611 + 0 | 0.2471 | 3,747.7 |
| grammar-layout-832749 / learned | 151/151 | 211 + 98 | 0.4887 | 3,080.9 |
| fact / typed-lsh | 363/1,120 | 9,947 + 0 | 0.0565 | 234.1 |
| fact / learned | 363/1,120 | 9,947 + 7 | 0.0565 | 267.1 |
| loopfact / typed-lsh | 449/1,112 | 16,629 + 0 | 0.0315 | 201.9 |
| loopfact / learned | 449/1,112 | 16,629 + 28 | 0.0315 | 251.2 |
| sum-divisors / typed-lsh | 1,404/8,018 | 376,781 + 0 | 0.0054 | 200.1 |
| sum-divisors / learned | 1,404/8,018 | 376,780 + 93 | 0.0054 | 198.3 |
| cyk801 / typed-lsh | 6,567/6,567 | 1,072,213 + 0 | 0.0061 | 1,323.3 |
| cyk801 / learned | 6,567/6,567 | 32,563 + 17,694 | 0.1307 | 1,640.5 |
| grammar-stride3-split-7300147 / typed-lsh | 256/256 | 1,214 + 0 | 0.2109 | 4,596.0 |
| grammar-stride3-split-7300147 / learned | 256/256 | 1,214 + 0 | 0.2109 | 4,761.1 |
| grammar-stride3-split-7300147 / chain | 256/256 | 720 + 264 | 0.2602 | 4,160.2 |


The JSON and typed LSH controls have identical accepted request tapes (including named parents, versions and repair events), proposal and verdict counts, recurrent score counts, signed operations and endpoint SHAs across all seven cases. Thus their cost difference isolates the transport and memory adapter. The learned arm uses the same typed runtime and frozen Compose scorer. EPT counts signed effective native operations divided by **every paid proof and compute instruction**, including rejected requests. EPS divides the same numerator by inclusive online wall. Derived coverage aligns visible reference facts; signed operations on divergent trajectories may include other work. A source schedule ending does not certify reference saturation. All reported trajectories reached schedule end.

**Chaining.** On withheld grammar-stride3-split-7300147 the two-step-trained model used 88 three-instruction chains to obtain right-span starts. Rust counted **176 successful local reads**. The policy paid for 264 computations and 720 proofs (152 accepted, 568 rejected), reaching all 256 reference facts. The one-step-only policy used no computation there and issued 1,214 proofs. Chaining increased EPT from 0.211 to 0.260; the extra work still cost time on this small input.

**Controls for the value of training.** On CYK801 the always-compute control paid 50,069 tokens and a fixed random six-bit projection with the learned route paid 48,173, versus 50,257 for the trained policy. All produced the reference SHA. On blind grammar 7300147 the ordering reversed: learned 470, always 500, random projection 492. The robust gain on these cases comes from acquiring evidence before combining parents. A consistent advantage from training the route or the address geometry has yet to be measured. For fact, loopfact and sum-divisors the learned route issued only 7, 28 and 93 computation requests respectively. Their coverage remained at the LSH control's level. Those EggCC programs participated in previous frozen Compose training and are in-domain.

## Measurement

Phase measurements below are single-rollout observations in seconds. The client's wait for a reply overlaps native decode, execution and encoding. Persistent index maintenance is part of memory update. Rule-local posting construction is charged separately. Timing includes startup, publications, routing, buckets, neural scoring, issue, transfer, verification and commit. It excludes checkpoint load, offline tape serialization and semantic alignment. Pipe time includes IPC and scheduling. All computation stayed on CPU during rollout. See [per-arm counters](results.json) for packet/byte counts, batch-size histograms, per-verdict counts, index writes/removes, postings touched, scored prefixes and complete tuples, wall and boundary costs. [Four interleaved measurements with exact and oracle controls](cyk801-pairs.json)

| CYK801 | JSON + LSH | Typed + LSH | Typed + computed evidence |
|---|---|---|---|
| Median wall from four pairs (s) | 9.874 | 4.846 | 3.304 |
| EPS using median wall | 665.1 | 1,355.2 | 1,987.7 |
| Bucket entries returned | 1,238,594 | 1,238,594 | 198,944 |
| Compose positions scored | 1,240,039 | 1,240,039 | 200,389 |
| Complete tuples scored | 1,072,460 | 1,072,460 | 32,810 |
| Native proof rejections | 1,067,222 | 1,067,222 | 27,572 |
| Operations per nonempty batch (mean) | 254.4 | 254.4 | 175.7 |
| Synchronous data batches + Run seals | 4,257 | 4,257 | 329 |
| Tensor/path conversion | 0.7210 | 0.2367 | 0.1296 |
| Request construction / binary packing | 2.1230 | 0.0499 | 0.0116 |
| Request pipe write | 0.0535 | 0.0193 | 0.0052 |
| Pipe wait/read for result | 1.4049 | 0.6958 | 0.1223 |
| Response decode and audit | 0.2920 | 0.0957 | 0.0192 |
| Published memory update | 0.2139 | 0.1952 | 0.1881 |
| Persistent field index update | 0.2051 | 0.1779 | 0.1702 |
| Rule-local postings, incl response index | 0.1335 | 0.1201 | 0.1571 |
| JSON request encoding | 1.7937 | — | — |
| Native operation decode | — | 0.0202 | 0.0019 |
| Native operations incl named proof checks | — | 0.6101 | 0.0421 |
| Native immediate result encoding | — | 0.0130 | 0.0011 |
| Native published-port encoding | — | 0.0006 | 0.0007 |

The four paired wall medians were 9.874, 4.846 and 3.304 seconds. Both improvements won four of four matched rounds on CYK801. Native exact execution took 0.128 s, oracle replay 0.045 s. Even the fastest of the three neural policies in these pairs took 25.8× the time of native exact execution. Small-workload EPS in the table is a single observation.

## Reproduction

Use the recursive experiment artifact root with the native compiled programs, captures, teacher tapes and frozen Compose/field weights. Build the cell_token_replay release example with cell-token-ept. Run from the instruction_pointer directory. Install the provided checkpoints into txn-study/model.pt and txn-chain-study/model.pt or regenerate with the training commands.

```bash
cases=(grammar-7300147 grammar-layout-832749 fact loopfact sum-divisors cyk801 grammar-stride3-split-7300147)
out=run-recall/transactions
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --extra-blind 4691132 7300147
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --cases grammar-stride2-17118 grammar-stride3-17119 grammar-stride2-17122 grammar-stride3-split-7300147
python train_txn_policy.py "$ROOT"
python train_txn_policy.py "$ROOT" --chains
for arm in json-lsh typed-lsh learned; do
    python transaction_bench.py "$ROOT" "$out" "$arm" "${cases[@]}"
done
for arm in always random-address; do
    python evaluate_txn_policy.py "$ROOT" "$arm" cyk801 grammar-7300147
done
python evaluate_txn_policy.py "$ROOT" chain grammar-stride3-split-7300147
python transaction_bench.py "$ROOT" "$out" pairs cyk801
python transaction_bench.py "$ROOT" "$out" report "${cases[@]}"
python transaction_dependency_check.py "$ROOT/unified-scale/build/release/examples/cell_token_replay" "$ROOT/recursive-agent/grammar-4691132"
```

The native release library passed 89 tests and Python discovery passed 37. A mixed batch regression replays all 43 proofs of a small reference grammar and exercises successful, stale, forward and failed computation dependencies. Its audit includes a deliberately rejected local read. Saved sum-bits semantic acceptance returned pass. [Native dependency audit](dependency-check.json) · [Build and checkpoint digests](digests.json)
