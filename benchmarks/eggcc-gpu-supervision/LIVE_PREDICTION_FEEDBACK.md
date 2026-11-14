# Live boundary prediction and generated-source feedback

The five-program ridge candidate now runs inside the GPU query-to-Cell path.
Previously its extended features were captured on the GPU but its candidate
predictions were evaluated after execution. This change also adds an explicit
experiment that retains generated Cells' predictions for subsequent consumers.
No backpropagation, CPU future matches, or CPU token correction is introduced.

This is **not** authoritative learned completion: constructor queries, exact
slots/Eq, effects, saturation control and ownership proofs still use the existing
GPU machinery. The experiment starts from a real saved Eggcc Run snapshot and
executes one three-rule family, not the full original multi-stage program.

## Live computation

For the experimental boundary model, `device_join_transition.proposals` reads the
current owner-projected neighborhood and computes its floating columns before
ridge inference. The columns are appended to the original feature map and use
the trained 2177-by-128 coefficient matrix. The capture references these same
computed columns instead of encoding the neighborhood again. Feature/model and
compiled-layout dimensions must agree. The existing source lifetime and finite
value checks still gate numerical readiness.

The runner requires both `--experimental-boundary-model` and `--boundary-context`
for a boundary-trained model. The default resident path remains available. A
calibrated model's original semantic family is checked before running.

## Nonvacuous feedback experiment

With `--predicted-source-feedback`, only the original generated rule templates
retain their birth prediction when exact effects finish. Imported seed templates
continue using exact encoding. Required slots, typed Eq readiness, scalar validity,
visibility, completed effects and finite predicted values are still checked before
clearing the numerical dirty flag. This does not turn a floating token into an Eq
proof. The shared owner representation, generation checks and effect PCs are
unchanged. There is no parallel shadow history of predicted bindings.

For retained templates, the exact token encoder is not invoked by refresh; the
prediction itself becomes the source floating token consumed by later queries and
boundary pooling. The experiment intentionally does not re-predict a retained
Cell after each subsequent union. Handling changing external assumptions remains
a separate unresolved state-transition obligation.

## Real GCD outcome

Both modes use the same frozen five-program weights, initial snapshot 437,
original rules 283/290/293, query order, capacity and fixed scheduler budget.

| Metric | Live inference, exact source encoding | Live inference, predicted generated sources |
| --- | ---: | ---: |
| Generated Cells | 41 | 41 |
| Consumers of generated sources | 15 | 15 |
| Released physical owner rows | 30 | 30 |
| Completed Runs | 3 | 3 |
| Exact predicted partitions | 35/41 | 35/41 |
| False pair merges after closure | 0 | 0 |
| Missed pair equalities | 16 | 16 |
| Direct selected-source exact | 23/26 | 23/26 |
| Generated selected-source exact | 12/15 | 12/15 |

Independent CPU interpretation of original unlowered rules passes every completed
Run's graph and per-rule match count in both executions. The comparison additionally
checks 454 shared integer/boolean capture arrays and identical CPU target tokens.
Those capture comparisons do not replace the separate Run graph audits.

The feedback path is not vacuous: all 15 generated-source consumers have changed
floating inputs. One additional direct selected-source instance changes through a
generated boundary neighbor. Maximum source-token change is 0.340579, feature
change 0.373253, and predicted-token change 0.077113. Thus equal aggregate accuracy
does not mean identical predictions or a disabled experimental path.

The readout decoder on CPU-correct target tokens scores 41/41. The same six
prediction failures survive feedback. Zero observed false merges on this one
validation program does not authorize removing exact completion or imply full
saturation correctness from ridge alone. The final graph passes because exact
GPU semantics remain authoritative, not because every learned token is correct.

CPU reconstruction of the live floating prediction is checked against actual GPU
captured predictions. Model and archive hashes are retained in all reports. The
label report now distinguishes exact versus predicted source-token mode and
counts direct selected-source instances with generated boundary neighbors.

## Cost and remaining work

Diagnostic compile/upload/execute time is 30.354 s with exact sources and 33.042 s
with feedback. These are single instrumented executions, not speed evidence.
Dense neighborhood construction and exact graph work remain. Readiness/lifecycle
checking is retained even where exact token re-encoding is bypassed.

Latest inspected Bake remains `883b1547`: completed RHS result joins require actual
returned witnesses and preserve dirty/pending/reader constraints. This experiment
does not add result-only owner joins; existing query-witness ownership transfer is
what the 30 releases measure.

Next obligations include a broader independent validation program, learning from
actual predicted-source inputs in the training partition, updating tokens when
boundary assumptions change, result-witness ownership takeover, and replacing
covered exact query/effect work with proved or audited token transitions. Full
Eggcc stages, general effects and CPU correction remain incomplete.

## Reproduction

ROOT = `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`; use the project MLX Python:

```
python audit_construct_union_family.py ROOT/union-corpus/validation-016-gcd.trace.json ROOT/five-program-boundary-model.npz ROOT/gcd-live-boundary-execution.json --rules 283,290,293 --snapshot-run 437 --ticks 12 --flush-every 1 --order-queries --boundary-context --experimental-boundary-model --capture ROOT/gcd-live-boundary-witnesses.npz
```

Repeat with `--predicted-source-feedback`, writing `gcd-feedback-*` artifacts.
Label each archive with `label_composed_witnesses.py`, the same trace and model,
original corpus manifest, and snapshot 437. Evaluate with
`audit_device_match_readout.py` and `five-program-boundary-decoder.npz/.json`.
Finally:

```
python audit_prediction_feedback.py ROOT/gcd-live-boundary-labeled.npz ROOT/gcd-feedback-labeled.npz ROOT/gcd-feedback-comparison.json
```

30 relevant tests pass, including compiled live inference, nonvacuous token change,
unchanged admitted symbolic state, missing-layout rejection, feedback readiness
failures, and existing constructor/union refresh tests. Native semantic acceptance
contracts are unchanged; this work edits no CPU executor code.
