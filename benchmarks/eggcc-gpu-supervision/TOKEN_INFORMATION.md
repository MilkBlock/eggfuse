# Preserve the connected input interface; distinguish missing context from fit error

This experiment audits actual f32 inputs to the Eq boundary decoder, then fixes
one information-loss path in the **whole-Cell token model**. GPU replay still
consumes supplied successful matches and observed provider routes. There is no
backpropagation, autonomous matching, ownership proof, native union submission
or native semantic acceptance.

## Exact feature ambiguity

`audit_token_information.py` compares complete f32 decoder feature rows within
each case and template. Signed zeros are normalized and nonfinite features are
rejected. A group containing both true and false Eq labels is indistinguishable
to a deterministic decoder with that input. Its minimum sample error count is
the smaller label count. The audit counts static-class queries, not expanded
slot pairs, and does not combine cases into a global collision catalog.

| Partition | Class queries | Oracle-feature conflicts | Predicted-feature conflicts | Minimum query errors from predicted conflicts |
|---|---:|---:|---:|---:|
| Training | 123,021 | 0 | 28 | 36 |
| Validation | 156,165 | 0 | 111 | 166 |
| Test | 34,240 | 0 | 2 | 7 |

Zero oracle conflicts does **not** prove robust separation, absence of near
collisions, or sufficiency of ridge. The small exact-conflict lower bound cannot
explain all observed false merges and misses. No new decoder is fitted by this
audit, and labels are used only to diagnose ambiguity.

At most eight conflicting feature groups per case retain positive/negative
witnesses. A diagnostic reconstructs model inputs with the replay plan's GPU
aggregation shapes and verifies recomputed outputs against actual GPU predictions
(maximum observed difference about 3.08e-5, within the existing audit tolerance).
This is a reconstruction, not an instrumented bit-exact intermediate trace.
All 58 retained witness pairs have identical reconstructed inputs, even when
provider tokens are replaced by oracle states. Fifty-six also have identical
normalized captured input bindings; two do not.

## Two different missing-information cases

The two test conflicts both have **zero provider edges** and identical normalized
input bindings. Their different Eq labels already exist at RHS return, not just
after Run completion:

- Rule 145: `Single(Get(expr, i))` equals `expr` in one graph context but not
  another (negative Run 98 / binding 212; positive Run 570 / binding 141).
- Rule 43: `Add(x, y)` equals `y` in one graph context but not another (negative
  Run 495 / binding 0; positive Run 563 / binding 9).

The rule's local matched slots alone do not specify all relevant graph context.
This audit does not identify the exact prior operation that established each
relationship. A different optimizer cannot recover absent context from identical
input. These cases need additional earlier/contextual Cell information or an
explicit CPU boundary, not numeric node IDs as features.

The two validation witnesses with **different** normalized bindings are euler
Run 17, bindings 35/37, rule 520 (Concat type analysis), comparing slots 3/6 and
4/7. Both have 13 provider edges. The old seed deliberately removed every input
Eq slot having a provider. That also removed the known **correlations between
connected input slots**, and the pooled providers did not preserve them.

## Implemented interface-preserving option

`--encoding class-interface` retains all current input slots in the class-balanced
seed. The original scalar values were already retained. Connected Eq inputs add
their template roles and **current input equivalence grouping**, not constructor
contents, RHS values, post-Run roots or numeric identities. Predicted provider
tokens still supply their state through the existing four-channel dataflow.

Output encoding is identical to `class-balanced`. Token width (128), feature
width, model dimensions, route arrays and GPU control flow are unchanged. Input
encoding still happens in CPU preparation; the future GPU runtime must carry
these interface correlations itself. This does not claim a CPU-free solution.
The option is recorded in model metadata and remains opt-in.

The model is refit on the same ten training workloads, selecting alpha using
only the original euler validation manifest. Its selected alpha remains 0.1.
The five-workload boundary selection audit uses the same fixed criteria as
`EQ_READOUT_SELECTION.md`; it again chooses alpha 100 for MSE/false-merge and
0.1 for partition accuracy. All four boundary coefficient arrays and their
feature maps are **bit-identical** before and after this change: targets and
boundary training examples did not change. The observed change is therefore
not due to an altered decoder fit or post-hoc test selection.

## Results and remaining regressions

| Fixed policy | Input seed | Exact Eq partitions / 5,454 | False Eq pairs | Missed Eq pairs | False pairs after closure |
|---|---|---:|---:|---:|---:|
| MSE / false merge | Old | 4,265 | 735 | 1,989 | 1,175 |
| MSE / false merge | Full interface | 4,288 | 379 | 2,038 | 596 |
| Partition | Old | 4,385 | 1,014 | 1,850 | 1,131 |
| Partition | Full interface | 4,415 | 883 | 1,828 | 976 |

The interface repair reduces false merges substantially under the MSE policy,
but increases missed equalities by 49. No version is safe to submit unions.
Every original test instance remains in scope; 99 complete cases have no Eq
comparison and 382 incomplete captures remain explicitly outside this audit.

The two euler binding-35/37 ambiguity groups disappear. Validation exact feature
conflicts fall from 111 to 108 (minimum errors 166 to 163). Training conflicts
and the two no-provider test conflicts remain unchanged. This confirms a useful
representation fix without pretending it solves the broader context problem.

## Costs, verification and reproduction

Whole-model preparation is 4.961 s and fitting 0.566 s. Cold GPU replay including
plan/upload/compilation is 0.195 s, CPU replay 0.196 s. The boundary diagnostic
uses 0.321 s for CPU features, 0.092 s for GPU readout/transfers, and 0.368 s for
three policy audits/mark writing. The information audit and boundary audit ran
concurrently; these are component diagnostics, not comparable throughput or an
end-to-end speedup. CPU/GPU numerical audits pass. The suite passes 105 tests,
including retention of connected-input Eq without any RHS/post-Run fields.

Use `CLASS_BALANCED_TOKENS.md`'s training command with the expanded training
manifest, unchanged original validation manifest, fresh `class-interface*`
outputs and `--encoding class-interface`. Use `EQ_READOUT_SELECTION.md`'s
selection command with that model and fresh `interface-selection*` outputs.
For the information audit:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_token_information.py \
  "$ROOT/rhs-training-expanded-20261114/manifest.json" \
  "$ROOT/rhs-validation-expanded-20261114/manifest.json" \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  "$ROOT/class-interface.npz" "$ROOT/class-interface.json" \
  "$ROOT/interface-information.json"
```

Substitute `class-balanced-expanded` and a fresh `token-information.json` for
the control audit. Committed reports: `token-information-results.json`,
`interface-information-results.json`, `class-interface-results.json`, and
`interface-selection-results.json`. Models, raw captures and local marks stay
on the external SSD. The next contextual extension should specifically address
persisting Cell sources outside the current adjacent-Run provider window and
preserve their interface correlations; adding more instances alone cannot fix
identical locally observed inputs with different completion outcomes.
