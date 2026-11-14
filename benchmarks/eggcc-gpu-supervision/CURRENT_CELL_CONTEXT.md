# Current Cell context instead of recurrent latent memory

`device_current_cell_inputs.current_inputs` reads the explicit current Cell set
through the existing ownership slot interface on GPU. It includes completed
non-seed Cells and all compiled slots, rather than truncating generated Cells to
the seed-query width. It returns floating role/scalar/equality-context fields,
visibility/lifetime masks and a completeness flag. Stable IDs are used only for
incidence, not embedded numerically. Historical predicted latents are not read.

`current_candidates` encodes these fields into ephemeral 128-float embeddings and
feeds them into the existing exact source/ownership query route. The original
state is unchanged. It rejects unsupported block-token layouts explicitly.

Tests poison all historical latents with NaN and verify identical finite query
features and bindings after a physical ownership transfer. Unsettled visible
Cells prevent completeness; hidden Cells contribute zero fields. Dirty historical
latents do not invalidate the explicit feature reader, but this does not remove
the old admission guard or authorize unverified effects.

This is a standalone input-path implementation, not a trained runtime takeover.
The encoder in the test is randomly initialized. The old recurrent checkpoints
must not be presented as validated for this representation. Current limitations:

- No training or full Run audit of the new representation yet.
- Existing bounded Cartesian query routing remains; not full-set attention or
  proven complete scalable context selection.
- Full-width per-Cell encoding is charged work and has no demonstrated speedup.
- New matching/effect heads must consume these transient embeddings; old Run
  scheduling and ownership checks remain authoritative in the interim.
- Exact selected source projections still matter: a logical producer is not
  necessarily the physical owner of a reused result (Bake branch f3321a3a).

Next integration must train from current synthetic explicit states, validate
multi-Run generation, and only then retire recurrent-latent invalidation within
proven coverage. It must not substitute an unvalidated encoder for old weights.

## Synthetic current-state training

`neural_third_step.py --current-state --include-uncovered-transfers` now generates
features from exact completed synthetic Cells after ownership transfer. It uses
resolved semantic source addresses, drops recurrent parent/consumer replay arrays,
and pads to the actual maximum observed full layout. It does not assume twice the
base template width bounds the composed layout. CPU exact application supplies
labels; no real Run bindings train this experiment.

`train_current_cell.py` trains a fresh encoder, transient transition and Eq head
with backprop. Only explicit `x`, edges, masks, source role tags, requests and
incidence enter the model. There is no token-target regression or recurrent
latent input. The dataset hash and current-state manifest are checked.

The first canon run uses 61 template pairs, 717 candidates, 233 legal matches and
600 training steps. Matching errors fall to zero; 207/233 legal states have exact
Eq outputs, with 18 false-positive and 11 false-negative pairs. This is training
fit, not independent validation or a full Run audit. It is not enabled by default.
The 5,376-float padded source input also requires efficiency work. This uses the
existing selected query context, not yet all-context generation or scalable
Bake-directed routing. Evidence is in `current-cell-results.json`; large artifacts
are outside Git under `current-cell-v36`.

```sh
python neural_third_step.py TRACE DATA.npz --ruleset canon --current-state --include-uncovered-transfers --count 1 --per-pair 1
python train_current_cell.py DATA.npz FIT.json --steps 600
```

## Admission integration

`CurrentCellModel.current_candidate_batch` explicitly opts into current-state
inputs. `advance` uses this path for the sealed query snapshot; RHS effects still
use the current write state. Field capacity comes from the trained model and
undersized layouts raise instead of truncating. The ordinary recurrent path is
unchanged.

Only this mode bypasses historical-latent dirty checks during candidate resolution
and commit. Original dirty metadata is preserved in the resulting state, so
switching back to the recurrent path cannot consume uncertified old latents.
Exact ownership generations, witness checks, visibility, capacity, finite new
outputs and current-state completeness remain required. Existing forward witness
context checks may still block uncovered cases; they have not been waived.

A controlled-head GPU test poisons historical latents with NaN and marks them
dirty before each Run. Run one adds G from F; Run two adds H from G; Run three
admits nothing. New facts remain invisible until the next source Run. Switching
back to the recurrent path blocks on the preserved dirty metadata. This proves
execution-path independence from historical latents, not trained-model accuracy
or complete saturation of arbitrary rulesets. The learned checkpoint still needs
a full independent Run audit.

## Learned-model multi-Run audit

`audit_current_cell.py TRACE FIT.safetensors AUDIT.json` executes the trained
current-state model against the full eight-rule canon Run, starting from the
same 61 synthetic template pairs as the training generator. It checks the recipe
hash, poisons old latents before each Run, and independently executes the CPU
ruleset for comparison. GPU state is passed directly to the next Run only after
a successful audit; no CPU correction is installed. Budgets are three Runs and
eight admission attempts per rule, with one-hop witness context. These are not
held-out workload results.

With the 600-step checkpoint: 47/61 first Runs pass; 45/61 reach an independently
verified fixed point. There are 76 audited Runs. Fourteen cases fail in the first
Run with diagnosed wrong Eq output, concentrated in pairs involving Cell 5.
Pair (7,6) passes the first Run but fails the second with query-incomplete;
one remaining case does not reach a fixed point within the Run budget. Errors
are not dismissed as latent drift: historical latents are deliberately NaN and
are not model inputs. The model remains unpromoted.

The 233 legal training samples contain 98 distinct exact masked feature inputs
and no contradictory duplicate labels. This rules out exact collisions within
this sample set only; it does not establish global representation sufficiency.
`train_current_cell.input_census` reproduces this diagnostic.

Full evidence and CPU audit timing are in `current-cell-run-results.json`.
Timing includes CPU full ruleset execution and graph comparison, but excludes
separate admission diagnosis and GPU time; it is not an end-to-end speed claim.

## Separating capacity failures from learned Eq errors

Run attention reports now retain `query_overflow` and actual per-atom pool sizes.
The second-Run failure in pair (7,6) has pool sizes [1,19], exceeding the default
16-slot candidate pool. With the same 600-step weights and an explicit
`--candidate-capacity 32`, all three Runs pass (6,4,2 admissions respectively),
and the third Run changes no reference facts or equalities: a verified fixed
point. The larger diagnostic capacity costs additional enumeration; it is not
a scalable-routing optimization. The default remains 16 and overflow remains a
failure, not a saturation signal.

Separately, training the same current-state dataset for 3,000 steps produces
224/233 exact Eq states (225 after Eq closure), zero matching errors, seven
false-positive and five false-negative pairs. The formerly failing pair (5,0)
now passes its full Run and fixed-point audit. This targeted result does not
establish full-suite correctness of the new weights; they remain unpromoted.
Reproduce targeted checks with `--pair 7 6 --candidate-capacity 32` on the old
checkpoint, or `--pair 5 0` on the 3,000-step checkpoint. Text evidence is
`current-cell-refinement-results.json`.

## Capturing the whole current Cell context

`neural_third_step.py --current-state --capture-context` additionally writes a
`.context.npz` bank with all current rows per synthetic case: full floating fields,
visibility/readability mask, exact roots and slot-valid flags, template IDs and
roles. Every candidate records `case` and actual `source_rows` into this bank.
There is no top-k neighbor truncation in the bank. Roots and row indices are
connectivity metadata, not floating semantic embeddings. Model inputs remain
explicitly allowlisted; capturing this bank does not silently train on labels.

The 61-case bank has been generated and tests check that source features reproduce
exactly the corresponding bank rows after ownership transfer. This is data
preparation for whole-context computation. The current trained model still reads
selected query sources; it has not yet learned or executed full-set context.
The bank lives outside Git alongside other current-cell-v36 artifacts.

Rechecking `neural_baked_eq.compile_rule` on these eight canon rules finds positive
proof support for rules 0–5, with 6–7 rejected as unsupported sealed operations.
These proofs establish some equalities, not a complete transition semantics or
permission to treat every unproved pair as unequal. They must not be substituted
for full constructor reuse and boundary completion checks.

The completed 3,000-step checkpoint audit with explicit candidate capacity 32
passes 54/61 first Runs and verifies 53/61 fixed points within three Runs. Seven
cases fail; one remains outside the fixed-point budget. This configuration changes
both training duration and candidate capacity relative to the earlier 600-step,
capacity-16 audit; the full-suite difference cannot be attributed solely to either.
The model is not promoted. See `current-cell-all3000-results.json`.

## Explicit union effects are template-owned

The speculative installer previously skipped union instructions when compiling
frame operations, relying entirely on learned Eq scores to reproduce them.
`compile_frame` now records a static, typed required-Eq mask for explicit union
instructions. In the current-state execution path, `frame_payload` installs
these required edges even if the learned score is negative. Stable slot handles
remain unchanged. Invalid union types/indices are rejected at compile time;
nonfinite model output still fails readiness. The legacy speculative diagnostic
keeps its old behavior unless `template_effects=True` is selected.

This is a partial semantic takeover: the model can no longer omit an explicit
union in this path, but it can still propose erroneous additional equalities.
There is no claim of complete congruence or boundary coverage. The static mask
uses existing closure machinery, not a new per-instance dependency registry.
Thirteen relevant installer/Run tests pass. Earlier learned-model audit results
predate this change and must not be presented as validation of the new behavior.

## Experimental template-only effect semantics

`audit_current_cell.py --template-only` keeps the current-state floating matcher
but bypasses the learned Eq readout entirely. The installed equality relation is
formed from current identities, explicit template unions, copy aliases, actual
returned constructor witnesses and local congruence conditions. The compiler
pairs occurrences of the same constructor in query/effects; all corresponding
inputs must be equal before their output ports merge. Fixed wiring is shared in
the plan; no per-instance reverse subscribers are created. Bound scalar literals
use exact reserved identity metadata. Unsupported non-constructor facts fail
compilation rather than being silently treated as constructors.

The local closure uses bounded GPU operations and explicitly checks settlement
before installation. Stable slot handles remain unchanged. This is exact semantic
control, not a claim that Boolean/int operations realize neural floating speed.
The candidate matcher can still miss cases; external constructor reuse and
cross-Cell congruence coverage remain incomplete. Full-Run CPU audit therefore
remains required. This mode is experimental, not the default.

Pair (1,6), previously failing with the 3,000-step learned Eq head, passes two
Runs and reaches a CPU-verified fixed point with this mode (capacity 32). Evidence:
`template-cell-transition-results.json`. The final audit rerun bypasses Eq-head
computation, not merely its outputs. Installer, condition, admission and audit
unit checks pass. This targeted result does not establish all-workload correctness
or any speedup.

## Remove dead dense computation in the template-effect control

`InterfaceCellTransition.match_logit` uses only `relation(relations)` and
`match_relation`; its score is independent of encoded Cell content. With Eq
prediction removed, the content encoder, attention transition and successor
latent no longer affect semantic execution in this particular mode. The current
model therefore bypasses these computations when `template_only=True`, retaining
the same incidence classifier and a zero placeholder for unused latent storage.
The explicit Cell slots remain the persistent semantic state. Other modes and
training are unchanged.

A test verifies bit-identical matching logits, including with NaN content inputs.
Pair (1,6) still passes both Runs with identical graph/admission verdict fields.
No speedup is claimed from this targeted check. Evidence is in
`template-matcher-results.json`. This path is a semantic execution control, not
a successful dense floating context engine: the classifier still reads exact
incidence and candidate enumeration still precedes it. The intended useful
floating work must address candidate search/matching, not dead content features.

## Supervise candidate construction instead of post-enumeration Eq prediction

`cell_prefix_targets.py DATA.npz TARGETS.json` transforms current-state captures
into next-Entry selection labels. An Entry is addressed by actual source Cell row
and a compiled constructor-view record; selecting only a Cell row is ambiguous
when it exports several facts of the same constructor. Capture is opt-in in
`candidates`, so the ordinary runtime does not allocate these label arrays.

Each sample names its context case, rule, selected Entry prefix, offered next
Entries and *all* legal continuations. Negative prefixes retain empty answer sets;
multiple matches are not collapsed to a single arbitrary winner. The generator
rejects contradictory labels for one complete Entry tuple and checks that walking
its prefix labels reproduces acceptance for every distinct captured tuple.

The existing 61-case synthetic corpus yields 674 prefix states, of which 81 have
multiple legal choices and 336 have no legal continuation. Dataset and context
bank hashes are verified. Evidence: `cell-prefix-results.json`. This is supervision
for a future current-context selection model, not a runtime candidate reduction
or a complete interaction census. It does not reinstate recurrent latent inputs.
Generate the input using `--current-state --capture-context`; newly generated
captures include exact `entry_sources` and `entry_records` alongside semantic
source rows, keeping physical witness identity separate from semantic ownership.

## First current-context next-Entry model

Captures now also retain exact Entry roots and source slot projections, verified
against the current ownership-resolved context bank. `cell_context_features`
forms dense floating port messages by summing role vectors of all visible valid
ports sharing a root, normalizing and applying tanh. Root magnitudes never enter
the network. Tests check invariance to representative renaming, hidden-row
exclusion, actual shared-context dependence, and NumPy/MLX agreement.

`train_cell_prefix.py DATA.npz FIT.json --steps 2000` trains a dense network on
current candidate-port messages, selected-prefix messages, query request/depth,
and exact prefix-candidate incidence features. It predicts next-Entry validity,
not Eq effects. All legal continuations and dead prefixes remain supervised.
The network has no recurrent latent input. Feature extraction is charged work,
not demonstrated free or faster than exact indexing.

On the 61-case synthetic corpus: 1,252 next-Entry examples, 674 prefix states,
1,412 floating input dimensions. After 2,000 steps all 674 training prefix answer
sets are exact, with zero false-positive/false-negative choices and no exact
feature-label conflicts. This is fitting, not held-out or closed-loop correctness.
The training script still enumerates examples offline. No runtime candidate
enumeration has yet been replaced, and missing-match/fixed-point proof remains
outside this model. Text evidence: `cell-prefix-model-results.json`; binary
artifacts remain under current-cell-v36 outside Git.
