# Actual-source ridge repair across programs

The earlier real context-family capture exposed direct-source false merges.
This iteration collects more **actual GPU-selected joint witnesses**, trains a
closed-form residual ridge, and executes the corrected readout in the same
GPU-controlled union saturation loop. It is a standalone selected-family
experiment, not full Eggcc execution, learned union authorization or a speedup.
No backpropagation is used. The default resident model remains unchanged.

## Data and acceptance

`collect_union_corpus.py` scans verified saved traces for the first nontrivial
pre-Run union operands of rule 283. It retains the original program partitions:
Pascals and Euclid train; GCD and LCM validate. Source reference executions must
be at most one second; full observer graph auditing is longer. Original program
JSON is restored from compressed storage and its compiler fingerprint checked.
The native observer then captures the actual pre-Run boundary and verifies all
Runs against its independent unobserved executor. Snapshot reuse checks recipe,
fingerprint, audited status and the requested boundary; it never reuses a live job.

Actual GPU matching, exact union/congruence, saturation, ownership transfer and
independent CPU verification produce 20 training and 4 validation instances.
Training features use only selected input witnesses; labels come from independent
CPU selected-family saturation, not from predictions or future inputs.

LCM initially fails at capacity 32: a sound selected witness exists, but enumeration
reports overflow and incomplete coverage. The Run is not allowed to commit its
union or finish. Capacity 128 passes all four cases. This is a charged capacity
increase, not an enumeration optimization. The failure is preserved in the report;
no failed program is removed from the accuracy denominator.

## Controlled ablation

A frozen token model supplies the baseline. Both candidates fit the same training
residual `atanh(target) - original_input @ resident_weights`, with an unpenalized
intercept and training-only feature scaling. A dual ridge solve avoids forming
a wide feature Gram. Alphas 1, 10 and 100 are all reported, not hidden behind a
best-result aggregate. The Eq decoder is fixed throughout.

| Validation | Exact partitions | False pair merges after closure |
|---|---:|---:|
| Resident | 2 / 4 | 8 |
| Residual using existing inputs | 4 / 4 | 0 |
| Residual plus 128 relation columns | 4 / 4 | 0 |

These counts hold for all three tested alphas. The relation columns offer no
additional semantic benefit on this corpus; they are not installed.

Crucially, the 20 training samples contain only **three distinct floating input
vectors**. All four validation inputs exactly equal training inputs, with matching
CPU target tokens. Program separation is genuine, but this is reuse of known
finite patterns across programs, **not unseen-structure generalization**. It
supports enriching the real witness distribution; it does not establish a broad
accuracy threshold. More distinct local patterns and cross-source Eq cases remain
necessary before selecting a general model.

## Actual GPU integration

The alpha-1 existing-input residual is an explicit opt-in `--adapter` in
`audit_union_family.py`. Loading checks the frozen parent-model hash, exact Cell
rule definition, coefficient shape and finite values. Since input column zero is
constant, the intercept and residual coefficients fold into the original matrix:

```
C_new = C_resident + C_residual
C_new[0] += residual_bias
```

The GPU uses the original feature width, single readout matmul and tanh. There is
no additional inference feature extraction, launch or branch. This does not remove
existing matching, exact completion or auditing costs. Coefficient artifacts remain
external and are not a global model replacement.

Both GCD and LCM were executed again with the folded matrix. Each produces two
correct partitions, zero false merges, and passes independent final partition,
fact and saturation checks. Ownership checks remain live. Captured targets and
inputs reconstruct correctly. Exact kernels still authorize union; improved
predictions are not treated as semantic proof. The inference coefficient and
adapter hashes are recorded separately from the frozen parent model.

## Reproduction and Bake alignment

Artifacts: `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/union-corpus` and
`union-feature-residual.{npz,json}`. Sources and text results are tracked; binary
captures, restored programs and weights are not.

```
python collect_union_corpus.py TRAIN VALIDATION CORPUS CAPTURE_BINARY MODEL ARTIFACTS REPORT --capacity 128
python fit_union_input_relations.py REPORT MODEL DECODER DECODER_REPORT WEIGHTS RESULT
python audit_union_family.py TRACE MODEL OUTPUT --rule 283 --snapshot-run RUN --capacity 128 --adapter WEIGHTS --capture CAPTURE --corpus-manifest CORPUS
```

Run from `benchmarks/eggcc-gpu-supervision`. `--reuse-snapshots` permits verified
saved boundaries without repeating the native audit. Tests check dual/primal
agreement, constant inputs, pre-union boundary selection, coefficient folding,
Cell/parent mismatch rejection, typed union and input relation encoding.

Latest inspected Bake branch: `f449d63e`, including `230b221a`. Its activation-reuse
selector constrains Entry activation and result capture independently, retaining
costs for larger dispatch/catalogs. This GPU change similarly adds no maintained
source facts or consumer lists: it reuses current witness inputs and folds the
chosen correction into existing computation. Future feature adoption must justify
its extra input storage and math; no CPU executor code was merged or changed here.
