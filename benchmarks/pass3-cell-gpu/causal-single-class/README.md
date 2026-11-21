# Emit a singleton policy action before reading the table

The deployed frozen singleton head has a useful restricted input map. For a rule with a physical pivot and a certified-model flag, the varying feature after compilation is a single bit: is this pivot at least as recent as the rule watermark? Rule features, rule ID and the current four-coordinate recurrent state are fixed at the action boundary. A stale and a fresh score therefore suffice to reconstruct the checkpoint's decision for every address in that rule's current source class.

For an eligible nonempty source call, the actor evaluates the existing head twice on those two feature vectors, thresholds the outputs and emits one **64-byte action**. This happens before acquiring or reading the pivot member list. The empty-table fast path consults public table counts and emits zero actions. The action includes a format, scheduled rule, table and pivot, source epoch, table generation, watermark, starting neural serial, the two exact float logits, a two-bit acceptance mask and a transport checksum. No fields scale with membership. A nullary or otherwise unsupported call stays on the original per-singleton path.

The receiver validates the context and reconstructs source membership in deterministic native order from the current public table and original input identities. It performs the compiled watermark and signature filters, expands the accepted classes, then checks the scalar key certificates and the normal full source suffix. It constructs the ordinary typed pages internally from those expanded receipts. Ordered winner choice, RHS, union and Spine retain their original entry points. The receiver supplies the recurrent updater with a 20-byte feedback record containing accepted count before scalar rejection, sum of freshness and source count. This handshake runs for every emitted action, including actions producing zero final receipts. The actor is causal across rules and needs this feedback before the next recurrent decision. It does not require a hidden view of the individually scored source addresses to recover the issued members.

A native request enables the treatment with numeric `class_actor=1` on the existing packed + scalar-negative path. The selector accepts the certified frozen feature basis, fixed memoized row action 4, learned mode without residual repair, native public header mode 3, and a typed pivot. Controls corrupt the action checksum, table generation or starting serial. All must reject explicitly.

**Metrics.** FEPT is final-visible original constructor e-node identities per external proposal packet. Count one actual class action, every residual singleton root, every multi-parent root, and every selected nested child. The effective numerator excludes initialization already present before inference, unrelated births, retired originals and originals hidden at final export. It includes visible constructors born by the explicit initialization RHS. Fresh nested children receive their own credit. The bidirectional variant additionally charges each feedback record as one packet. Internal per-lane receipt materialization, verification and filtering are separately counted and timed.

**Wire size.** The actor and recurrent feedback use real fixed-size byte layouts in the native process. To compare different unchanged native object types, the audit also declares a common framing: eight u64 fields per singleton page and 37 bytes per literal (three source words plus u64 neural serial, f32 score and one initial-source flag); six u64 fields per multi-parent page and four u64 fields per raw parent reference; each selected child uses the measured compact JSON representation of its issue-time fields plus an eight-byte length. Forward and bidirectional size totals cover all branches under this declared framing. These figures do not measure network I/O.

**Downstream gate.** `ClassGate::choose` runs before membership enumeration. `ClassGate::observe` sees source and surviving counts only after execution of this call or a proved empty-table return. Audit-only `single.class_actor.rule_calls` records epoch, rule, eligibility, chosen class path, source count after watermark/signature filtering, selected candidates before the scalar proof, eligible post-scalar receipts, descriptors, residual external singletons and the empty-table bit, all in original call order. Both control and treatment expose this trace. The recurrence digest covers every issue call, its feedback, original source ordinal and all four resulting state coordinates as float bits.

## Results

| Workload | Visible original nodes | External proposals, packed → class | FEPT, packed → class | FEPT including feedback | Model evaluations, packed → class | Inference ms, packed → class | Caller wall ms, packed → class |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 2,691 | 12,662 → 7,770 | 0.2125 → 0.3463 | 0.2852 | 1,620 → 3,331 | 31.95 → 33.21 | 68.32 → 70.31 |
| conjugate-gradient | 34,595 | 217,966 → 90,478 | 0.1587 → 0.3824 | 0.3583 | 5,531 → 12,151 | 633.59 → 666.55 | 752.96 → 784.34 |
| 3mm | 92,658 | 558,074 → 232,580 | 0.1660 → 0.3984 | 0.3834 | 8,611 → 18,197 | 1,801.21 → 1,940.70 | 2,059.72 → 2,203.07 |

| Workload | Class actions (zero post-scalar receipts) | Receiver public headers enumerated | After public prefilters | Removed by exact scalar filter | Internal singleton receipts | Residual literal / multi / selected child | Bidirectional canonical MB, packed → class |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 1,664 (393) | 66,500 | 7,886 | 1,330 | 6,556 | 3 / 5,912 / 191 | 0.911 → 0.727 |
| conjugate-gradient | 6,074 (2,193) | 2,593,759 | 243,380 | 109,818 | 133,562 | 3 / 83,313 / 1,088 | 11.984 → 7.304 |
| 3mm | 9,097 (3,085) | 8,790,167 | 845,165 | 510,574 | 334,591 | 3 / 220,972 / 2,508 | 31.152 → 19.151 |

Every header reaching class selection after the structural source prefilters received a positive threshold decision in these runs. The frozen actor sometimes excluded the stale class, but public source constraints had already removed all such would-be negative members. The gain is in carrying many positive proposals in a causal fixed-size action. The number of actual neural evaluations rises: the control memoizes only classes it encounters, while the prospective actor pays for both logits before knowing whether either class has members. Reconstruction also reads the complete public bank on each eligible call; it does not reuse the issuer's cached membership list.

The exact source RHS, writes, union, Spine, final graph, physical root/child ledgers, complete singleton decision digest, per-call recurrence digest and endpoint-origin yield all agree. Four paired prepared-process samples per arm followed a warmup; the public decoding and exact lookup work is included. Three native transport fault controls failed as expected in each workload. The higher FEPT did not accelerate whole inference in this experiment. [All samples, denominators and verifier counters](results.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/class-actor-build"
python3 study.py "$exp" "$exp/class-actor-build/session" "$exp/class-actor-study"
python3 verify.py
```
