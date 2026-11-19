# Single-row pointer-head and static-encoder ablation

Fit the two head-sharing arms first, with identical compiler-role input. Then
hold the pointer head shared and fit template-ID, pooled-GNN and port-GNN arms.
Reuse the shared role arm in both tables. This is five configurations × two
predeclared seeds (1703 and 1709), each with a final checkpoint. Primary endpoint
is exact nonempty second-Run coverage on complete unseen composition families.
Also measure wrong parent (distinguish live-but-wrong from inactive/invalid),
duplicate bindings, missed source obligations, endpoint time and conditional
coverage when every required parent was actually generated.

The experiment uses frozen real Bake join structures, typed recipe-derived
static wiring and synthetic candidate frontier tables exercising their boundary
contract. Scope is the two adjacent interface steps. Whole-workload inference,
RHS side effects and equality saturation are outside this endpoint. Family
membership and witnesses are obtained from corpus/, independently of fitting.
The effective number of templates, families and held-out rules is recorded after
static extraction and before training. Reserve separate strata for seen atoms
when available. Cache identity is never a role feature. Train/test both include
multiplicity, conflicting candidates and source values from the same scalar
vocabulary, so novelty of composition is the comparison variable.

A single sequential row has up to eight positions per logical step. The consumer
reads the emitted producer frontier, its static port conditions, and the supplied
consumer request records. CPU supplies offline training alignment and audits
completed evaluations. All arms have the same ordered static projection,
activation and recurrent modules, train-only auxiliary output supervision and
conditioning width 32. For the head experiment, create independent copies of
the same initialized pointer scorer, keyed by primitive rule, or tie them all.
Keep pooled and per-port GNN weights/shapes equal at initialization; only readout
changes. Role-only uses the same dense updates and parameter count with self
features and incident relation counts in place of neighbor features. Each GNN
uses two directed typed message rounds. ID uses a learned training-template
vector plus local operand features, with a fixed zero vector for unseen IDs.

Predeclare 1,536 optimizer updates per fit, batch 32, Adam lr 0.001, same
homogeneous-template training minibatches, balanced cyclic template sampling,
no validation-based checkpoint selection, no teacher intermediate state.
Train only on training families; retain training-family diagnostics separately.
No retraining for endpoint measurements. Report actual parameter counts,
initial equality of the unaffected weights, and cost of preparing and encoding
the static graph versus steady-state execution with cached embeddings.
Use matched inputs and synchronized batch-one MPS timings. Repeat an identical
decoded-witness audit for timed inputs; CPU scoring and offline Bake are outside
the latency window. Check scores per template and seed. Do not promote an arm
from two seeds or a single holdout family solely on aggregate counts.

Before any optimizer update, extraction produced 19 unique supported two-leaf
templates, with 12 templates/9 families for training and 7 templates/2 entire
families held out. The grouping conservatively erases literal values, column
numbers and sort identities as specified in the extraction manifest. Four
held-out templates contain two seen primitive rules; three contain at least one
untrained primitive head. Report these strata separately, including the
untrained head limitation for the private arm. All 34 longer source units are
excluded. Each template contributes 64 collision examples (32 counterfactual
pairs); training uses 1,024 graphs per training template. Primary readout is
on the 448 held-out collision graphs. Macro-average over the two families
and list per-family results. The 64 IID examples per template are diagnostics.

Pre-evaluation correction: the pilot readout of a whole input table contained
its degree but omitted the compiler roles of its ordered columns. No held-out
scores had been calculated. The formal protocol gives ALL four encoders the
same local operand descriptors (sort kind per present column, prior publication,
cross-row/within-row/literal equality, projection use). All four builds restart
from the same per-seed initialization in a separate directory. Pilot fits
are excluded. The roles/pooled/ports arms have exactly matching trainable
parameters and initial weights. Template ID still conveys only learned
training-template context in addition to the common local descriptors.

Before primary held-out evaluation, also register a parameter-budget check for
Fig. 02: fit two additional shared-role models with a single widened linear
query/key projection and the same number of head parameters as the whole private
bank. Initialize it to the same scores as the ordinary shared head. The input
width still bounds the effective bilinear rank; this sensitivity arm isolates
the raw weight budget, not arbitrary expressivity. Keep it separate from the
five primary arms. Report the 317/448 collision inputs whose supplied residual
requests can coexist under the local functional-key check, in addition to the
full synthetic candidate study.
