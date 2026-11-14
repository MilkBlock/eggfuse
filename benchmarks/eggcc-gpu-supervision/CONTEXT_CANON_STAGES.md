# Real compiler rules across two GPU stages

The existing device scheduler already supported nested control. The family audit
entrypoint incorrectly constrained all selected rules to one source ruleset. It
now accepts `--schedule CONTROL.json`, routes each compiled rule block to its
actual source stage, keeps one resident Cell/ownership state across stages, and
checks the completed GPU stage sequence against an independent CPU schedule
interpreter. The original single-stage default remains supported.

The CPU interpreter walks the source tree directly; it does not reuse the GPU
compiled control table. Every Run matches before applying effects. Saturation
checks actual constructor/union changes. The oracle executes sequence, repeat
and saturation with a Run budget and rejects unknown source stages. Labeling now
uses the captured control rather than saturating all selected rules together.
Those two computations can have different semantics. Legacy captures retain
single-family saturation behavior.

## Audited synthetic experiment

The fixture contains actual Eggcc compiled rules 288 (`context`: push AddContext
through Bop) and 270 (`canon`: Add commutativity). It contains no observed Run
bindings or values. Seed 20261400 generates four query fragments; one explicit
same-sort BinaryOp equality identifies a context Bop's operator with Add, ensuring
a real producer/consumer connection. The document's generator and merge replay
under the ordinary synthetic-input validator.

The explicit schedule is `saturate(context); saturate(canon)`. That order occurs
in the original compiler control, but this is only a selected fragment: omitted
rules/stages are not claimed covered. The fixture is rule-valid, not proven
reachable from a complete source program.

GPU execution passes full graph comparisons after every Run, final graph,
complete matching and lowering checks:

- stage sequence: context, context, canon, canon;
- per-Run matches: 2, 2, 4, 7;
- generated Cells: 9;
- generated-source consumers: 4;
- physical owner rows released: 5.

A captured canon query at `capture/7/0/1/`, lane 3, consumes the context-produced
Cell at witness row 8 alongside the Add seed at row 0. Thus at least one consumer
crosses the actual source-stage boundary; merely putting independent rules in
two stages would not establish this. The final dataset has nine samples and ten
positive quotient Eq labels. No new ridge model is fitted this turn.

The ordinary single-stage seed 20261120 also passes the updated GPU runner. Nine
schedule tests pass, including independent stage-order sensitivity and budget
failure tests. Large captures remain outside Git; text fixtures/results reproduce
the experiment with:

```
python audit_construct_union_family.py context-canon-synthetic-input.json BASE_MODEL \
  OUTPUT.json --synthetic-input --rules 0,1 --snapshot-run 0 \
  --schedule context-canon-schedule.json --capacity 32 --ticks 32 \
  --flush-every 1 --order-queries --capture CAPTURE.npz
```

Use distinct stems for OUTPUT and CAPTURE metadata. Labels are generated with
`label_composed_witnesses.py CAPTURE.npz INPUT.json BASE_MODEL /dev/null LABELS.npz
REPORT.json --synthetic-input --snapshot-run 0`.

## Open obligations

This run uses exact completed source tokens and exact GPU graph effects, with the
old floating predictor only diagnostically evaluated. It does not establish
learned multistage completion or neural-like speed. An explicit schedule with a
learned classifier/decoder now requires its report to name that completion
control; old single-stage weights must not be silently reused for a new control
contract. Future training must condition or separate remaining stage semantics,
not mix identical structural inputs with different completion targets unnoticed.

The full original Eggcc schedule, broad primitives and mutable operations,
learned matching authority and applied CPU corrections are still unfinished.
Bake branch remains ace4f4c4; no CPU executor code was changed or merged here.
