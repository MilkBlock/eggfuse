# Capacity, ranking and repeated computation in the EggCC Cell generator

We varied two parts of the generator independently on the same whole-program validation workloads. The first comparison widens the number of prefixes retained at each read without changing the weights. The second fixes that width at 32 and changes the number of shared hidden-state updates inside the recovery pointer. The native receiver and the higher Cell catalog are identical. The two validation programs have 4,215 and 6,118 reference rule commits. The signed-commit recall denominator counts distinct rule applications with their input bindings. Final e-node recall requires a different measurement.

## How many correct bindings fit?

The offline allocation control takes each recorded teacher proof, assigns it to its rule and first fresh atom position in that Run, and keeps up to the given budget in each group. Since every retained prefix has at least one retained leaf, no intermediate level requires more slots than the number of retained leaves. Native replay checks each chosen request against its original distinct binding. This establishes the capacity of the output format on complete teacher histories. It gives the allocator the answers and preserves the full teacher history, even when it measures a subset.

| Maximum retained per anchor role | Verified teacher proofs on affine-twins | Verified teacher proofs on gated-state | Actual signed commits from native assist, pooled | Paid external proposals | Duplicate verdicts | EPT |
|---:|---:|---:|---:|---:|---:|---:|
| 32 | 4,146 | 5,939 | 7,835 (75.83%) | 25,389 | 16,784 | 0.2118 |
| 64 | 4,212 | 6,083 | 8,173 (79.10%) | 34,620 | 25,277 | 0.1604 |
| 128 | 4,215 | 6,118 | 8,358 (80.89%) | 43,443 | 33,569 | 0.1294 |

The native assist columns include contributions from higher Cells. Duplicate counts include internal proposals. EPT divides signed effective operations by paid external proposals. Widening the frontier increased signed coverage at the cost of more redundant work. With independent search disabled the exact source prefix stayed at 14 Runs on affine-twins and 10 on gated-state. All exclusive final states differed. The four candidate configurations were diagnostic and did not replace the deployed policy. [Capacity controls](capacity) · [Paired program summaries](summary.json) · [Existing width-32 control](../connected-reads/validation/source)

## Where the original root pointer lost bindings

A separate root-only shadow run uses the original width of 32 on teacher snapshots. All complete proposals are checked against the native reference binding, including alternate certificates. For every binding with no matching proposal, the pointer receives the teacher's preceding ports. We record the first step at which neither ordinary nor recovery score clears its issuance threshold. If the recorded path clears the thresholds at every step, its loss is assigned to bounded frontier selection, including tie handling and the recovery quota. This attribution describes the recorded proof for each missed binding. Other unobserved proofs could behave differently.

On the two validation programs, root-only proposals covered 7,460 distinct commits. Of the 2,873 misses, 208 failed first at the anchor, 1,143 first at a later parent, and 1,522 had qualified paths that were dropped during selection. Within each group of proposals proving the same native commit, every one of the 15,484 surplus valid proposals had the same ordered parent-field hash tuples as another proposal in its group. This diagnostic used all declared parent fields and made no claim about different commits or proposals failing visibility or version checks. No field comparison prunes proposals in the generator or receiver. [Per-program pointer audits including both training programs](root)

## Does additional recurrent depth help?

Both new recovery heads have 3,121 parameters and use the same initialization and sampling seed. Their input is the frozen Actor's context, candidate port and existing read evidence. The initial state is tanh of the projected input. Each refinement reuses a 24-by-24 learned matrix and the original input; the final readout scores the candidate. Both heads were trained independently on Metal using the same training-program data and reserved-example threshold rule. At deployment they score below-threshold reads with the same width-32 budget and four recovery slots. These hidden updates read the same candidate and prefix. They do not provide the pointer with competing requests or evidence from a new Run.

| Trained shared updates | Distinct signed commits on validation | Duplicate verdicts | Paid external proposals | Exact source prefix on affine-twins / gated-state |
|---:|---:|---:|---:|---:|
| 1 | 7,623 (73.77%) | 16,344 | 24,558 | 14 / 10 |
| 3 | 7,706 (74.58%) | 16,518 | 24,897 | 12 / 10 |

Three refinements recovered 83 more commits than one. Both trained variants trailed the existing recovery head. This single-seed comparison tests depth in one pointer component. The head thresholds were fitted separately on reserved training examples. All native assist runs reproduced ordered execution, final state and the effective-operation ledger. The reports include held-layout completions, neural decision counts, rejection reasons, residual search and individual execution times. No paired speed benchmark was performed. [Training data and checkpoints by hash](training) · [Assist](validation) · [Search-free exclusive trajectories](exclusive)

## Reproduction

Use the program partitions, frozen checkpoints, native receiver and higher layouts from the [connected-read study](../connected-reads/README.md). Reuse the source-order recovery data from the original [recovery study](../prefix-recovery/README.md). For validation teacher memory, replay each program's native tape with the extra arguments `--memory MEMORY`.

1. Run `root_frontier_audit.py capacity FOLDER MEMORY BINARY OUTPUT --budget WIDTH` for each width.
2. Run `root_frontier_audit.py pointer FOLDER MEMORY ACTOR RECOVERY BINARY OUTPUT --budget 32 --seed 3434` for the root-only failure attribution.
3. Run the source-order native assist and exclusive commands from the connected-read study, adding `--root-budget 64` or `--root-budget 128`.
4. Fit each recurrent arm with `train_prefix_recovery.py ROOT ACTOR BINARY SOURCE_DATA OUT --refinements STEPS`. Pass OUT as the recovery directory for `layout_credit.py`, with the original budget and field reader.

[Study configuration](protocol.json)
