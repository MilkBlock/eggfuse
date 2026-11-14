# Direct state ridge in live GPU Cell continuations

The direct completion head now runs at GPU token birth and its reconstructed token
is consumed by later Cell queries and boundary aggregation. This is an opt-in
selected-family runtime experiment, not full native Eggcc or authoritative learned
completion. No backpropagation or online validation-label feedback is introduced.

## Replaced work

`device_ridge_transition.encode_features` exposes the existing current-source
feature map and readiness checks without executing an output projection. In the
new path, `device_join_transition` uses this map once, gathers existing actual
scalar slots, evaluates the template's centered state-score ridge matrix and
selects a state compatible with proven current input Eq. Baked moments plus actual
scalars generate the complete 128-dimensional token handed to admission.

The old 2177-by-128 output projection and the secondary Eq decoder are neither
uploaded nor evaluated in this mode. The runner loads only the original random
feature matrix from the prior model; the new state heads supply output weights.
The decoder hash remains in provenance solely for the separate CPU readout audit.
Tests deliberately make old inference and decoder calls fail, while exercising
CPU and compiled GPU proposals with a model that has no `coef` key.

The head bank still costs 278,656 bytes plus 52,376 normalization/bias bytes.
The original input projection, source/boundary gathers, state/moment tables, scalar
encoding and exact execution machinery remain. This is a concrete output-path
replacement, not an end-to-end performance claim.

## Preserved semantics and ownership

Exact proposal slots, slot roots, witnesses, source generations, key/delta handling,
effect PCs, visibility and ownership metadata stay on the existing path. No second
binding representation or per-producer consumer list is introduced. State selection
changes only the floating token. A predicted Eq never changes the exact graph or
proves a takeover. Nonfinite inputs, missing scalar results and incompatible head
layouts remain explicit failures. The two optional predictor modes are exclusive.

Generated Cells retain their birth tokens through exact effect completion, and
later consumers read them through the existing owner-projected interface. Imported
Cells use exact encodings. New scalar effects still need actual results; this
selected family only has query scalars. Later external unions do not yet trigger
learned re-prediction of a retained Cell. That remains a lifecycle limitation.

The original Run schedule, exact GPU matching, constructor/union completion and
fixed-point detection remain authoritative. CPU interpretation happens afterward
for audit; it does not send future matches or corrected tokens into the run.

## Validation

Thirty tests pass across direct heads, previous readout, partition/token encoding,
ordinary joint queries, owner admission/effects and feature schema. New tests
verify that the old output and decoder are not called, exact proposals are
unchanged, GPU choices/tokens agree, invalid head shapes/scales fail, nonfinite
inputs cannot be admitted, and dirty sources remain blocked.

The GCD run uses original snapshot 437 and rules 283/290/293. It completes 3 Runs,
generates 41 Cells, consumes generated sources 15 times, and releases 30 physical
owner rows. Every Run graph, per-rule match count and final selected-family graph
passes the independent original-rule CPU interpretation. All 454 shared symbolic
capture arrays match the exact-source control and CPU target tokens are identical.

All 15 generated-source consumers have changed floating inputs, as does one direct
consumer through its ambient generated neighborhood. Complete-state prediction
is 39/41: direct inputs 24/26, generated inputs 15/15. There are 3 expanded false
merges and 3 expanded missed equalities, all in direct inputs. Quotient Eq precision
and recall are both 16/18. Selected states and their reconstructed-token readout
have zero disagreements. Live feature/head/token reconstruction agrees within
1.67e-6. This preserves the offline result under actual feedback; it does not prove
all Eq proposals correct.

GCD diagnostic compile/upload/execute time is 32.610 s; CPU reference plus audit
is 0.187 s. These instrumented single runs are not evidence of throughput benefit.
Remaining dense exact matching/completion dominates this prototype's architecture.

## LCM feedback and local CPU diagnostics

LCM completes 3 Runs, 99 generated Cells, 21 generated-source consumers and
25 physical owner releases. All Run graphs, per-rule match counts, final graph
and 454 shared symbolic arrays match the exact-source control. Twenty generated
consumers and one direct consumer have changed floating inputs.

| Metric | Previous whole-state feedback | Direct-head feedback |
| --- | ---: | ---: |
| GCD complete states | 35/41 | 39/41 |
| GCD generated-source complete | 12/15 | 15/15 |
| GCD expanded false merges | 0 | 3 |
| LCM complete states | 83/99 | 95/99 |
| LCM direct-source complete | 71/78 | 76/78 |
| LCM generated-source complete | 12/21 | 19/21 |
| LCM expanded false merges | 7 | 13 |
| LCM expanded missed equalities | 21 | 0 |

The offline direct head scored 96/99 with 9 expanded false merges. Feedback loses
one generated-source instance and increases that count to 13. The live LCM head
has 37 true and 7 false quotient Eq predictions: recall 100%, precision 84.09%.
Selected-state and reconstructed-token readouts agree exactly, and CPU rebuilding
of live features/head scores/tokens agrees within 2.39e-6. Consistent encoding does
not eliminate the remaining semantic prediction errors.

The readout audit now writes local rejection diagnostics keyed by the immutable
capture hash, capture prefix and accepted lane. Each record includes original rule,
source witness rows/generations, generated-source status and false/missed quotient
slot pairs. GCD rejects 2/41 instances (4.88%); LCM rejects 4/99 (4.04%). These are
post-execution diagnostic marks, **not** executable repair tickets or applied CPU
corrections. No live state is changed by this analysis.

GCD failures are rule 290 (missed Eq) and rule 293 (false Eq), both direct. LCM
failures are two direct rule-293 instances and generated instances of rules 283
and 293. This provides a concrete next training/audit target instead of attributing
all remaining failures to long chains or counting expanded pairs as independent
failed Cells.

LCM diagnostic GPU time is 258.409 s; CPU reference plus audit is 0.227 s.
Separate captured-token readout/rejection audits take 0.141 s for GCD and 0.185 s
for LCM in the saved run. These include decoding saved labels and do not represent
online CPU correction throughput. The GPU path remains much slower in this
instrumented prototype; removing the old output/decoder has not established an
end-to-end speedup. No default model or semantic authority is promoted.

## Latest iterative Bake inspected

The latest branch inspected is `codex/cell-parallel-admission` at `6e8fead0`.
Its preceding `f0e6616f` inherits native binding projections through an append whose
typed wiring preserves source positions, reducing materializations from 1,166 to
239 while increasing some layout/equality checks. The latest observer recognizes
already-satisfied constructor Sets only with an actual visible owned witness,
full key agreement and current result equality. It observes 174/186 newly covered
Sets in seed/joined catalogs; it does not skip those writes yet.

Our three-rule Get family overlaps the kind of opportunity that observer finds,
but a learned completed state is not such a witness certificate. This change does
not count predicted equalities as redundant Sets or remove exact effects. Future
GPU takeovers must preserve actual returned results, owner/generation validity,
full keys and original effect ordering, then remove the covered old path rather
than adding a successful probe before it. No CPU executor changes are included.

## Reproduction

Use `audit_construct_union_family.py` as documented in
`RESIDENT_COMPLETION_STATES.md`, replacing the two completion-decoder options with:

```
--completion-classifier ROOT/direct-completion-classifier.npz \
--completion-classifier-report ROOT/direct-completion-classifier.json
```

Keep `--predicted-source-feedback --experimental-boundary-model --boundary-context`.
GCD uses snapshot 437 / 12 ticks; LCM uses snapshot 514 / 16 ticks. Write
`*-classifier-feedback-witnesses.npz`. Label with `label_composed_witnesses.py`
plus `--completion-classifier ROOT/direct-completion-classifier.npz`, then use
`audit_device_match_readout.py` and `audit_prediction_feedback.py` against the
matching exact-source control. ROOT is `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`.

Capture labels verify weight hashes, independently rebuild current input features
and scalar codes, recompute state scores/choices, and only then compare with final
CPU labels. Binary datasets and weights remain external; text results are saved
with the reproducible sources. These are development validation programs, not a
fresh held-out test or acceptance of full multi-stage Eggcc support.
