# Improve the Eq decoder without changing Cell tokens

This is a frozen-token readout experiment on actual captured Eggcc data, not a
complete autonomous GPU runtime. The baseline token model, source routing and
completion representation remain unchanged. No backpropagation is used.

## Features and execution

The existing 512 input columns include token z, template request q, endpoint
sum s, absolute difference d, product p, and two token-role products. The opt-in
--port-interactions decoder appends z_first*p, z_second*p, z_first*q,
z_second*q: 256 floating interaction columns. Baseline random projection rows
are preserved, with only new rows appended. Both layouts use a 256-wide fixed
tanh projection and closed-form ridge. Template queries and endpoint products
are compiled constants; only z changes during inference. There is no additional
GPU branch per instance or identity-to-float conversion.

The feature function executes as a compiled MLX operation. The workload readout
audit still materializes decoder features on CPU before GPU linear inference;
its timing is **not** end-to-end GPU runtime performance. The test separately
verifies the full feature arithmetic on Metal. The 768 input layout is explicit
in saved projection dimensions; unknown layouts fail rather than silently decode.

## Held-out results and the tradeoff

Training/validation/test provenance is unchanged from the baseline Eq selection.
Four ridge alphas are evaluated on validation; partition policy selects .1 for
both models. Test labels do not choose the policy. All policies and numeric
checks are retained in the JSON report.

| Metric, partition policy | Baseline | Interactions |
|---|---:|---:|
| Validation macro exact partition rate | .80708085 | .82870034 |
| Test exact partitions / 5454 | 4404 | 4612 |
| Test false equal pairs | 613 | 991 |
| Test missed equal pairs | 1815 | 1360 |
| Test nontransitive partitions | 54 | 150 |
| False pairs after transitive closure | 771 | 1174 |

More correct whole partitions does not authorize more unions. False positives
and nontransitivity regress. This is opt-in, not a new default or a proof-carrying
completion implementation. CPU verification / explicit boundary handling remains
necessary; confidence and ambiguity handling must be selected using validation,
not adjusted to these test errors.

One selected decoder requires 197633 weight floats, versus 131841 previously
(+49.9%). Feature rows grow from 769 to 1025 floats. New dense projection work is
256*256 multiply-adds per decoded pair; template interactions also require 256
products. Saved reports expose audit feature preparation, GPU readout and CPU
validation times separately. No speedup is claimed.

## Oracle-state audit: some information was accessible but underused

The same frozen decoder is fed actual completed-state tokens, completions inferred
from correct sources, and recurrently inferred completions:

| Input | Baseline exact partitions | Interactions exact partitions |
|---|---:|---:|
| Actual completed state | 4419 | 4550 |
| Direct, correct source tokens | 4406 | 4580 |
| Recurrent source tokens | 4404 | 4612 |

Improving actual-state decoding without changing its encoding demonstrates that
at least some previous errors came from inadequate readout features, not solely
irreversible information loss. It does not prove the representation sufficient.
904 actual-state errors remain. Prediction errors can cancel decoder errors:
recurrent tokens fix 35 direct errors and introduce three. Thus the recurrent
score alone cannot establish faithful latent completion or ownership transfer.

## Reproduce

Run select_eq_readout.py with the existing class-history-neighborhood-input model
and report, rhs-training-expanded-20261114 and rhs-validation-expanded-20261114
manifests, held-out rhs-dot-product trace, --port-interactions and
--reject-unstable-candidates. Run audit_direct_source_readout.py with those frozen
weights and selection report. All inputs/models stay under
/Volumes/Extreme SSD/eggfuse-artifacts/21ee; committed reports include their hashes.
25 relevant tests pass, including unchanged baseline columns and compiled Metal
interaction arithmetic. Numeric/threshold audits pass on real validation/test.

The tracked Bake branch is still 55f5fd9a. Static endpoint/template features are
derived from the same Cell definitions; this experiment adds no runtime binding
store, subscription graph or ownership certificate.
