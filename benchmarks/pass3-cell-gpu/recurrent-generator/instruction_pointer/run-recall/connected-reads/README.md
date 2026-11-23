# Does a different parent read order improve distinct Cell issuance?

A sealed seminaive Run provides the same anchor and typed port domains in all three arms. The connected order reads the first remaining atom sharing a template variable with a previously named atom. It starts the next disconnected component in source order. The pointer scores the entire eligible port domain at each step and emits the complete parent tuple in original atom order. A duplicate receives the existing native verdict. No other request's returned port is assigned to it.

Two complete EggCC program trajectories supplied training examples. Only the connected-order recovery head was fitted on Metal. A fixed subset of source rule signatures was excluded, and a reserved subset of training Runs was used to set the head threshold. The old head and the refit both used a beam of 32 with four recovery slots. Validation used two different whole programs and separately tracked the held graph-layout subset. [Program split and promotion criteria](protocol.json) · [Training counts and hashes](training.json)

| Native assist on affine-twins and gated-state pooled | Signed / 10,333 reference commits | Missed | Native duplicates | Paid external requests | Complete rule × Runs / 2,070 | EPT |
|---|---:|---:|---:|---:|---:|---:|
| Source order | 7,835 | 2,498 | 16,784 | 25,389 | 1,435 | 0.21182 |
| Connected order, frozen weights | 7,939 | 2,394 | 18,032 | 27,300 | 1,458 | 0.21139 |
| Connected order, refitted recovery head | 7,875 | 2,458 | 17,477 | 26,747 | 1,456 | 0.21374 |

Duplicate verdicts include internal proposals. EPT credits signed effective operations per paid external request. All six assist executions matched the reference schedule, RHS, writes, returns, events, final state and effective-operation ledger. Fully signed nonempty Runs totaled 394, 409 and 399 respectively. Completed instances of held layouts totaled 5, 9 and 4. External requests per signed commit rose from 3.24 to 3.44 and 3.40. Both alternatives failed the promotion criterion. The deployment uses source order and the reserved test program was left unused. [Locked selection](lock.json) · [Per-program assist reports with timings and decision counts](validation)

With independent search disabled, all three arms reproduced the first 14 Runs on affine-twins and the first 10 on gated-state. All six exclusive final states differed from their references. The extra bindings from connected ordering did not move the first divergence on either program. Single-execution timings are diagnostic only. [Exclusive executions](exclusive)

## How much fallback search survives perfect positive proposals?

Using each training program's original sequence of complete teacher certificates, native assist accepted all 7,265 sum-bits and all 6,704 dot-product commits, with zero duplicates or residual commits. It still visited 8,744 of the original 8,769 and 7,988 of the original 8,022 fallback candidates. Exclusive teacher replay used zero fallback candidates and matched the reference through the final state. The assist result measures these specific full teacher tapes. The number of residual commits understates the work spent checking for missing bindings. [Sum-bits control](sum-control.json) · [Dot-product control](dot-control.json)

## Reproduction

From instruction_pointer, use the existing field-wiring study's frozen Actor, field reader, graph policy, catalog and native receiver. Run the following with the training corpus as ROOT and a separate working directory as OUT.

1. Run `connected_read_study.py control ROOT/sum RECEIVER OUT/sum-control.json` and repeat for dot.
2. Run `train_prefix_recovery.py ROOT ACTOR RECEIVER OUT/data OUT/model --collect sum dot --read-order connected`, then run the same command without the collection flags to fit the head.
3. Run `layout_credit.py CORPUS ROOT/sum RECEIVER ACTOR BAKE OUT/validation/ARM --cases affine-twins gated-state --omit --attach --run-recall --read-order ORDER --recovery HEAD --policy POLICY --field-reader READER`. For source and connected, use the same original head and the corresponding order. For refit use connected order and OUT/model. Repeat each arm with `--exclusive` and OUT/exclusive/ARM.
4. Run `connected_read_study.py select run-recall/connected-reads/protocol.json CORPUS OUT OUT/lock.json`. It checks checkpoint identities, distinct signed commit totals against the reference, the per-program effective-operation ledger, and the exclusive search count before selection.
