# Does the binding need to be scored before the anchor is discarded?

Two binary-atom shadow runs use all scheduled binary rules on complete teacher snapshots. The same frozen Actor scores each full tuple by the sum of the two log sigmoid margins, conditioning the second parent on the first. One arm first drops anchor rows using the ordinary width-32 recovery pointer. The other scores every typed legal anchor with every legal second parent. Cutoff ties are discarded; the matched comparison issues exactly the same count in each rule/pivot/Run. The native replay receiver independently checks the named pairs. The underlying scorer still uses ordered roles. This tests the cost of irrevocable prefix pruning in two-parent rules.

| Program | Required binary commits | With early pruning | With delayed pruning | New / lost distinct commits | Paid per arm |
|---|---:|---:|---:|---:|---:|
| affine-twins | 2,524 | 2,323 | 2,330 | 15 / 8 | 42,100 |
| gated-state | 3,776 | 3,039 | 3,177 | 166 / 28 | 45,470 |

The combined joint domain contains 9,065,882 pairs versus 7,316,806 after anchor selection. For the control the diagnostic reuses score tiles from the full domain. Pair counts describe logical work and the result does not establish a wall-clock gain. [Affine-twins](affine-twins-binary.json) · [Gated-state](gated-state-binary.json)

## Two batches with shared context

The frozen pointer reads a width-64 frontier. Each rule/anchor group may issue up to 32 complete proofs. First it chooses up to 16 by the original confidence. For contested groups, the second batch competes for exactly the remaining number issued by the one-batch control, including the handling of boundary ties. The contextual head reads a soft attention summary and field similarities to those first named proofs on the same snapshot. Its blind control sees only its own candidate. The native receiver sees one sealed batch in original frontier order. The approach has no inter-batch verifier calls. Training used only sum-bits and dot-product, removing a fixed subset of rule signatures. Each reachable distinct new binding receives one unit of positive training weight within its pool. Failures and proofs of bindings already covered by the first batch are negative.

On contested validation pools the common first batch reached 2,011 distinct reference commits. The second added 628 with ordinary ranking, 662 with the blind head, 740 with the contextual head and 656 with that same head's context projection disabled. These marginal counts are across contested pools only. The entire upstream root pool already misses 2,387 / 10,333 distinct reference commits, even with unlimited final selection from that pool. Changing the final selector cannot recover them.

| Native assist across both programs | Signed / 10,333 | Paid external | Native duplicates | Signed effective operations |
|---|---:|---:|---:|---:|
| Single ranking | 7,860 | 25,854 | 17,222 | 5,432 |
| Blind second batch | 7,910 | 25,901 | 17,197 | 5,452 |
| Contextual second batch | 7,995 | 25,912 | 17,069 | 5,491 |

Each assist execution matched the reference through the ordered source Runs, final state and effective-operation ledger. All six exclusive executions matched the first 14 Runs on affine-twins and the first 10 on gated-state with zero independent search. None reproduced its final state. All three assist arms completed five instances of held graph layouts across the two cases. Live alias frontiers and higher-Cell obligations can differ across arms even when every local second-batch allocation has a matched budget. The validation experiment does not promote a new deployment or claim a speedup. [Assist](validation) · [Exclusive](exclusive) · [Training hashes](model)

## Reproduction

Use the existing frontier-depth study's frozen weights, native receiver and sealed memories. Run binary_joint_audit.py FOLDER MEMORY ACTOR RECOVERY BINARY OUT for each validation case. For the sibling study, train_sibling_issue.py collect CASE ROOT MEMORY ACTOR RECOVERY BINARY DATA uses --training only for sum and dot. Run train_sibling_issue.py fit DATA MODEL for the blind control and add --context for the contextual arm. Run sibling_audit.py CASE DATA MODELS OUT for offline credit. Run the source-order layout_credit.py commands from the connected-read study, adding --root-budget 64 --batch-cap 32 and optionally --sibling-head MODEL. Use --exclusive for the search-free rollout.
