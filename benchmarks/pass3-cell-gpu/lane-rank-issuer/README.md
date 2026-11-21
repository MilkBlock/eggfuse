# Rank signed lanes for private Cell reservations

This standalone native Cell CPU experiment leaves the existing Run-wide quantity predictor, budgets, parent issuers and verifier intact. After every active rule in the Run has finished sealing its candidates, and before its first source validation, an optional shared head ranks the complete set of available lanes for each rule. The rule's K granted records are already privately constructed. It names up to K of that rule's signed parent tuples, with earlier source order breaking exact score ties. Accepted selections keep the identical physical fact backing. All other verified fresh roots use their ordinary physical allocation. The ranking does not alter the candidate stream, reissue a graph row, reorder source effects or silently replace a parent. After selection, the native claim still checks exact root serial, Run, template and original physical parents/versions against the signed receipt.

The eight input count-forecast weights and the lane rank weights have separate purposes. An unchanged count forecast always receives the same largest-remainder per-rule budget. For `spec_cells` with `timing="run"`, `storage="named"`, and whole-Run `proposal_wave=65536`, specify `lane_rank` with one of the following:

- `{"mode":"first"}` selects the first K offered lanes at the same wave barrier.
- `{"mode":"score","weights":[...],"bias":...}` evaluates a shared 12-input affine head. A hidden-layer alternative accepts `hidden` (eight rows of twelve coefficients), `hidden_bias` (eight), `output` (eight) and scalar `bias`. It uses tanh and binary64 evaluation. Completely admitted or zero-budget cohorts have a fixed action and bypass scoring.
- `{"mode":"capture","groups":true}` preserves first-K policy and records all labels. Each group is `[epoch, rule, grant, [[features,negative_count,positive_count], ...]]`; every nonempty group, including one with zero grant, is represented. `hist` also holds a global histogram. A positive label is the first subsequent verified *physical primary allocation* belonging to that serial, not an accepted RHS alone. `groups:true` or `capture:true` can also be added to a score control.

All 12 inputs are integers in [0,8], divided by eight at scoring. They are, in order, multi-parent page indicator, page-size log bin, lane position fraction within that page, arity, fraction of fact versus function refs, fraction with age at most one epoch, minimum and maximum parent age log bins, fraction of unchanged role/address/version triples relative to the previous lane, first- and last-parent frequency bins within the page, and rule LHS arity. Boolean true is eight. Fractions are floored. Log bins use floor(log2(1+n)) capped at eight; arity counts are capped at eight. Absent parents have zero age/frequency features. All words and source timestamps are known after issue, and features need no exact source row lookup or verifier feedback. Features are captured for both selected and unselected lanes. The source verifier alone supplies eventual outcomes.

## Native control evidence

Each arm runs the actual frozen Rust Pass 3 proposer. The independent default EggFuse executable supplies ordered Run/RHS/writes/Spine, union and final-state reference. Surviving source parent identities, signed issue streams, allocation receipt provenance and physical Cell IDs also agree with the previous one-to-one named allocator. These are mechanism and correctness controls, without speed claims. Fixed demand is six per rule, Run cap 37. Each benchmark has at least one nonempty zero-budget cohort.

| Program | Issued lanes | Actual root births | First-K uses | Later-position scorer uses | Upper bound within the same budgets | Selected beyond first-K |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 13,801 | 5,764 | 1,514 | 1,453 | 1,603 | 1,315 |
| dot-product | 15,781 | 5,538 | 1,216 | 1,186 | 1,346 | 1,446 |

The later-position control intentionally scores only the position feature; a monotone hidden head returns the identical actions. They demonstrate real reassignment and cost no additional granted slots. The independent Python calculation reconstructs feasible fresh-hit bounds by pool and score from the compressed histogram. It allows either outcome at indistinguishable score ties. Zero affine weights produce identical decisions and physical usage to the legacy first-K implementation. Zero-cap capture produces the same global feature/outcome histogram as fixed-cap capture, despite using no staged Cell. Expired epoch, withheld name and foreign-page-lane controls reject every otherwise fresh selected allocation. They preserve all original source results with ordinary allocation at the omitted physical site. A distinct physical ID never becomes visible during scoring. [Observed controls](controls.json)

```sh
d=benchmarks/pass3-cell-gpu/lane-rank-issuer
python "$d/build.py" "$EXP/lane-rank-build"
python "$d/control.py" "$EXP" "$EXP/lane-rank-build/session" "$EXP/lane-rank-controls"
python "$d/verify.py"
```
