# Actual constructor result contexts

Following the composed Set witness work at Bake ace4f4c4, this experiment adds
three input contexts per constructor-write rule: target absent, target present
with the assigned result, and target present with a distinct result. The latter
must retain a nontrivial union. These are synthetic inputs, not native program
snapshots, and do not claim a new GPU Set optimization.

`synthetic_result_ownership.py synthetic-context-recipe.json ARTIFACTS` builds the
six contexts. Seed 20261203 was the first seed starting at 20261200 containing
both relevant rule entries; selection checks input availability, not completion
labels or validation scores. All sides materialize the same pre-Set constructor
prefix. The terminal constructor is then absent, assigned to the existing value,
or assigned a fresh typed result. Actual stored values may belong to other seed
Cells. No future saturation information enters the seed construction. The normal
replay validator reconstructs this transformation and verifies the input hash.

The focused independent test proves: absent adds one constructor, equal adds no
union, distinct adds one real union without construction. In the larger synthetic
family all six cases pass complete GPU matching, per-Run graphs, final graph and
lowering audits. Each produces five captured direct-source Cells, zero generated
source consumers, and six released owner rows. For each rule the absent case
allocates five fresh IDs, the existing cases four; first-Run union counts are
1/1/2 for absent/equal/distinct. The shared one-union background comes from a
separate rule. These are effect differences, not claims of fewer logical matches.

## Synthetic-only fit and real-program evaluation

Added these 30 direct-source samples to the preceding 19 synthetic contexts.
The ridge alpha, feature representation and state decoder remain unchanged;
training uses no real Run samples and no backpropagation.

| Exact-source offline evaluation | Previous paired set | With result contexts |
| --- | --- | --- |
| GCD complete states | 22/41 | 25/41 |
| GCD direct-source states | 14/26 | 17/26 |
| LCM complete states | 55/99 | 80/99 |
| LCM direct-source states | 35/78 | 60/78 |
| Expanded false Eq pairs, GCD/LCM | 88/150 | 67/33 |

The candidate is not promoted. These development evaluations are not untouched
test sets, and this is only the selected three-rule family.

## Actual predicted-token feedback

The new head then ran on the GPU GCD snapshot, with generated predictions retained
and consumed by later Cells. It generated 41 Cells, 15 generated-source consumers,
30 released owner rows and three Runs. All exact graph and match checks passed;
learned Eq does not authorize graph mutation. Diagnostic GPU compile/upload/run
cost was 32.866 seconds, CPU reference plus graph audit 0.128 seconds: no speedup.

The head's selected completion state is correct in only 20/41 cases: direct
17/26, generated 3/15. Thus direct-source performance is retained here but generated
feedback loses five correct cases relative to the exact-source offline evaluation.
CPU local diagnostics reject 21/41 instances (51.22%), including 9 direct and 12
generated cases. These diagnostics are post-execution, not applied correction.

There are also 20 disagreements between selected state and the historical learned
Eq decoder's token readout. The selected-state audit uses actual captured head
choices and independent labels; it must not be replaced by decoder accuracy.
The old decoder is not evidence that the new state representation is reliably
readable across all selected states. Addressing this separately from generation
accuracy is a live obligation. No LCM predicted-feedback rollout was run this turn.

Full multistage Eggcc, learned completion authority and applied CPU correction
remain unfinished. This work strengthens controlled inputs and actual ownership
coverage; it does not close those requirements.
