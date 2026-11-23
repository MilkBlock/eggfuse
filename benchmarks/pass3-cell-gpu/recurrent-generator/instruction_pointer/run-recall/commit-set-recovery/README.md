# Distinct-commit supervision for the existing recovery pointer

The native receiver, root Actor, graph policy, beam, thresholds and deployment code are the existing versions. This experiment fine-tuned the recovery pointer on Metal. Offline, the native verifier checked 148,059 complete certificates from sum-bits and dot-product. It assigned a reference commit identity to each valid certificate. A separate replay recorded which commits the frozen root Actor could already issue with the normal beam and no recovery. Both audits checked the ordered source execution and final state on the teacher trajectory. Only programs from the declared training partition supplied labels. The held source rule signatures and reserved training Runs were excluded from updates.

Training grouped 9,490 valid complete proofs into 2,750 distinct commits, 1,783 with multiple sampled proofs. The normal beam had already covered 1,279 groups. Each uncovered group earns coverage credit once, approximating the chance of at least one issued proof under independent sigmoid scores. All selected proofs pay the same soft proposal cost. Partial reads and invalid proofs retain a distillation loss against the original head. Native commit identities, group membership and normal-beam coverage are offline targets. Deployment sees the ordinary model inputs. This experiment changes a single component of the generator. It does not jointly train the root Actor or higher Cell choice. [Training hashes and sample counts](model/training.json)

On reserved training-program snapshots, the candidate selected fewer invalid and redundant complete proofs at the frozen threshold. It also missed unique commits the original head recovered. Sum-bits lost 12 of those commits and dot-product lost 11. This isolated threshold audit uses the sampled complete-proof rows without a beam or live rollout. [Read audit](held-read-audit.json)

| Native assist on validation programs | Original → candidate signed commits | Paid external proposals | Native duplicate verdicts | Fully signed nonempty Runs |
|---|---:|---:|---:|---:|
| affine-twins | 3,337 → 3,318 / 4,215 | 11,352 → 11,233 | 7,506 → 7,443 | 188 → 186 |
| gated-state | 4,448 → 4,425 / 6,118 | 14,005 → 13,932 | 9,062 → 9,046 | 200 → 198 |

Duplicate verdicts include internal proposals. Native assist reproduced the reference schedule, ordered RHS, writes, returns, events, state and effective-operation ledger. Both candidates used the same executable, graph catalog and checkpoints outside the recovery head. The worst validation recall fell from 72.70% to 72.33%. The original policy was retained. Window-laplacian remained unused. Exclusive execution with zero independent search matched the first 14 and 10 Runs respectively with both heads. Neither reproduced either final state. Timings in the raw reports are single executions. [Selection and layout holdout counts](selection.json) · [Original assist audits](../marginal-policy/validation/base) · [Candidate assist audits](validation) · [Exclusive trajectories](exclusive)

An earlier discarded receiver experiment let duplicate requests borrow the winning request's sealed return ports. On sum-bits this raised completed graph instances from 159 to 673 while distinct signed commits fell from 5,419 to 5,408 and internal step checks increased from 4,625 to 12,442. The experimental receiver changes were removed. Both arms of the pointer experiment used the original verifier with SHA-256 9baee8273937950f151f9f640ff325254ad4a4556fd994db7a6a26665472499d.

## Reproduction

Use the same source corpus, frozen Actor, Bake catalog, receipt policy, recovery checkpoint and native example as the preceding program-held calibration. Run from instruction_pointer with MPS-enabled Python. TRAIN holds the sum and dot teacher tapes and memory histories. VALIDATION is the corpus directory of the preceding experiment, including the two validation programs and native reference audits.

~~~sh
PROTO=run-recall/commit-set-recovery/protocol.json
python train_prefix_recovery.py "$TRAIN" "$WEIGHTS" "$BIN" "$OUT/data" "$OUT/model" --collect sum dot --commit-sets
python train_commit_recovery.py "$TRAIN" "$OUT/data" "$WEIGHTS" "$RECOVERY" "$PROTO" "$OUT/model"
python layout_credit.py "$VALIDATION" "$TRAIN/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/validation" --cases affine-twins gated-state --omit --attach --run-recall --policy "$POLICY" --recovery "$OUT/model"
~~~

For exclusive traces, pass the same arguments with a different output directory and add --exclusive. Run each arm with its own recovery checkpoint.
