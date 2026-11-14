# Semantic ownership in the GPU prototype

This is a standalone MLX experiment, not the egglog runtime. Physical payload
transfer does not establish that a successor token represents the source Cell.
In particular, fields copied into spare payload slots are not part of the
successor's semantic template.

`neural_semantic_owner.compile_semantic_transfer` checks a conservative sealed
constructor/copy/union subset. It proves source constructor facts and equalities
under the slot mapping from destination facts and explicit Eq closure. Constructor
`set` is interpreted as a fact only for constructor tables. Mutable functions,
unsupported guards/effects and overwritten slots remain uncovered. Lowered
constructor-set temporaries use the existing semantic slot projection. This is
an offline structural proof, not proof that a learned token is numerically right.
The existing completion certificate and CPU numerical audit remain necessary.

Opt-in initialization adds two int32 vectors: semantic source row and generation,
8 bytes per logical Cell. No bindings, facts or floating tokens are copied.
A certified handoff composes aliases to the new source. Candidate construction
keeps original logical witnesses and binding-slot projections, but reads token
content and relational port-role features from the semantic source. Referencing
a retired, hidden, unsettled, dirty or reused semantic source blocks consumption.
This conservatively requires a live semantic owner; independent retirement and
asynchronous audit still need explicit lifecycle integration.

The implementation uses fixed tensor operations. It currently scans the bounded
logical arena during handoff and may include the same semantic source repeatedly
as resident context. It is not a dispatch or bandwidth speedup claim. New entries
and recycled rows do not automatically inherit a valid semantic directory.

Tests cover physical transfer with semantic aliasing, old Entry consumption,
matching owner roles, repeated alias composition, generation rejection and
rejection of field-only containment or missing Eq evidence. Existing model weights
have not been retrained for these changed inputs.

Run the independent synthetic audit with:

```sh
python benchmarks/eggcc-gpu-supervision/audit_neural_gpu_rhs.py TRACE \
  TRANSITION_WEIGHTS OUTPUT.json --limit 107 --follow --interface-only \
  --context-capacity 8 --eq-readout EQ_WEIGHTS --semantic-owners
```

Inspect `semantic_owner.adopted` per case before interpreting any accuracy result.
A pass with no semantic adoptions does not validate this execution mode. For
uncovered cases Bake must construct a combined semantic Cell layout and training
must learn its output token; a destination-only token cannot be relabeled as
containing its entire ancestry. Speculative corrections still require an updated
token, and full multi-stage GPU saturation is not implemented here.

The full existing 107-case synthetic corpus admitted zero semantic takeovers:
83 retained source fields only in payload slack, 23 lacked payload coverage, and
one lacked structural facts. Its 312 subsequent states still had 16 incorrect Eq
states including two false-merge states (`difference`, exit 1). These reproduce
the old model's behavior; they do not measure a trained combined-owner token.
See `semantic-owner-results.json`. This rejects promoting destination-only tokens
as semantic dominators and motivates combined template output supervision.

## Combined semantic layouts and training

`neural_combined_cell.compose` now forms a sealed descriptor containing both
producer and consumer facts. It preserves destination port positions and appends
unshared producer positions using the ownership plan. Original source/destination
projections are exported together. The descriptor is **not executable code** and
must not bypass the original effect/Run boundaries. Its hash identifies the exact
serialized layout, not arbitrary graph-isomorphism classes.

`neural_cell_chains.chains(combined_owner=True)` uses this whole descriptor as
the prediction target. Source and destination Eq readouts are evaluated separately
as projections of the same generated token. The target labels use synthetic exact
completion only; generated source tokens are consumed directly during training.
No teacher completion tokens enter the recurrent input. The frozen interface
matching head remains unchanged.

Reproduce the two experiments with `train_neural_combined_owner.py TRACE
TRANSITION_WEIGHTS OUTPUT.json --steps 1200`, adding `--unordered-request` for the
pooled request control. The ordered request encodes static slot positions and
source/destination projections, never dynamic object IDs. Both experiments start
from the same preceding transition checkpoint, not from each other's result.

The synthetic training corpus contains 1,261 positive / 1,257 negative chains,
244 producer-consumer rule pairs and 393 combined layouts (up to 18 semantic
ports), within the same 17 context rules. This is bounded observed synthetic
composition coverage, not all possible interactions. On 578 positive test chains:

| Request | Whole owner exact | Source projection exact | Destination projection exact | States with false merges |
| --- | ---: | ---: | ---: | ---: |
| Pooled roles | 261 | 260 | 569 | 130 |
| Ordered static layout | 240 | 244 | 565 | 137 |

Counts use transitive Eq closure; detailed raw counts, input overlap and unseen
subsets are in `combined-owner-results.json`. Neither checkpoint is suitable for
execution. A completed training process is not semantic acceptance. The larger
joint-state task is not directly comparable with earlier destination-only Eq
accuracy. Ordered static mapping alone did not fix source-state retention.

Next: preserve multiple token blocks under one semantic owner and learn their
union-conditioned update, rather than reconstructing the whole ancestry into
one 128-float vector. These measurements motivate that experiment; they do not
prove an intrinsic dimensional lower bound. Runtime combined-owner publication,
third-step consumption, correction transitions and saturation remain unfinished.

## Two-block owner experiment

`neural_owner_blocks.OwnerBlocks` keeps original source and destination port
layouts. It generates the destination block, then adds a learned residual to the
source block using both tokens and the static template/projection requests. The
source residual starts at zero. The shared Eq decoder reads each block in its
original template; a floating cross-block decoder predicts their remaining Eq
relations. Both blocks and their cross edges are audited as one Eq graph, so a
cross-edge false merge cannot be hidden by separate per-block scores.

The training entrypoint is `train_neural_owner_blocks.py TRACE TRANSITION EQ
OUTPUT.json --steps 1200`. Source updates are trained against the source's state
**after** consumer effects. The same synthetic seeds and 17-rule family are used;
no actual Eggcc run is used as training data. All Eq readouts receive floats and
static template information, not exact runtime object identities. Backpropagation
updates source/destination token generation and readouts; matching layers remain
frozen.

`neural_block_handoff` connects these outputs to the existing physical ownership
transfer in the standalone GPU audit. An Entry retains its original port roles
and selects a block of the new semantic owner. `neural_device_candidates` reads
these blocks directly, rather than regenerating source tokens. Generation,
liveness and block bounds are checked. Rejected transfers leave state unchanged.
The old independent `tokens` array is removed on block-mode initialization.

The initial device handoff joins two singleton owners only. Further composition
reports a block-capacity boundary; it does not truncate an inherited owner. The
arena reserves two 128-float blocks per logical row, including initially unused
blocks. This doubles the floating arena allocation versus the old one-token
array, plus 16 bytes/row for owner reference, generation, block selector and block
count. Released logical block storage is not compacted; no memory/speed saving
is claimed.

Run `audit_neural_gpu_rhs.py TRACE BLOCK_WEIGHTS OUTPUT.json --limit 107 --follow
--interface-only --context-capacity 8 --block-owner` for actual handoff and
subsequent GPU candidate consumption. This mode uses its bundled Eq weights,
expands the initial payload budget for composed pairs, and cannot be combined
with the single-token speculative rollback experiment. Its first two RHS steps
still use exact GPU completion and initial bindings supplied by the synthetic
harness. Following candidates are enumerated on GPU. It is not full Eggcc
execution or autonomous saturation, and this different pair selection must not
be compared with earlier 107-case audits as an identical workload.

The 1,200-step block experiment obtained 301/578 fully correct joint states,
391/578 source projections and 574/578 destination projections after transitive
closure. There were still 203 joint states with false merges. Among 23 states
where the consumer actually changed source Eq, the updated source answered 12
correctly versus 1 without its residual update. These are evidence of a learned
update, not sufficient accuracy for trusted execution. Joint pair counts differ
from the deduplicated single-token layout, so pair-level errors are not directly
comparable across representations.

The subsequent actual GPU handoff audit adopted both blocks in all 107 selected
cases. All exact setup graphs, slot interfaces and retained blocks passed their
checks. GPU enumeration recovered 338 subsequent matches without missing or
spurious matches; 274 consumed generated query sources. Floating semantics still
failed in 49/338 subsequent states, including 16 false-merge states. The audit
returns `difference` / exit 1. No model is promoted. See `owner-block-results.json`.
Next training must replay these updated block inputs through later consumers,
not merely decode their state at the two-step boundary.

## Actual third-step replay and frozen-base adaptation

The next dataset is generated **after actual two-block device ownership**:
`neural_third_step.py ... --block-owner --context-capacity 8`. Training uses seed
23001, count 8 and per-pair 2 (475 scenes, 11,251 candidates, 1,378 positives).
Evaluation uses seed 93003, count 4 and per-pair 1 (216 scenes, 5,033 candidates,
625 positives). All scenes completed physical and block ownership transfer.
Runtime-selected inputs distinguish boundary seeds, updated source blocks and
destination blocks. Replay recomputes the first two transitions differentiably;
no reference completion token is fed into the third transition.

This follows the current Bake branch's admission-state lesson: observe states
created by the **current** ownership catalog instead of adding more routes from
an obsolete component distribution. `codex/cell-parallel-admission` remained at
`f3321a3a`, containing `56e28b89`, during this experiment. This does not mean its
native ownership compiler is integrated into the Python prototype.

Use `train_neural_owner_blocks.py ... --third-train TRAIN.npz --third-test
TEST.npz --steps 1200`. `--resume OWNER_WEIGHTS` continues the previous block
checkpoint. Alternatively, `--freeze-base` starts from the supplied original
transition/Eq checkpoints and freezes both, training source updates and cross
readout only. A bytewise parameter comparison verifies frozen weights. Gradient
tests verify that the third-step loss still reaches source updates through the
frozen transition/readout. These two experiments have different starting points;
they are not a single-variable controlled comparison.

| Experiment | Held-out third states correct, before → after | False-merge states, before → after |
| --- | ---: | ---: |
| Continue unrestricted block training | 530 → 517 / 625 | 46 → 100 |
| Frozen original transition and Eq | 541 → 562 / 625 | 10 → 11 |

All correctness counts above use transitive Eq closure. Frozen-base raw pair
prediction has 522/625 exact states; closure yields 89.92%, not a rounded claim
of reaching 90%. Of 391 positive states whose exact inputs were absent from
training, 330 are closure-correct. Disabling the trained source update under the
same frozen checkpoint returns 541/625 overall and 322/391 unseen states, so the
update contributes an observable benefit, but also adds a false-merge state.

The independent 107-scene device audit still adopts all owners and has no missing
or spurious matches. Unrestricted fine-tuning regresses to 72/338 wrong semantic
states, including 70 false merges. The frozen model gives 41/338 wrong states,
including 4 false merges (previous block model: 49 and 16). A replay audit with
`--block-owner --case-limit 107` agrees exactly with those device state/error
counts. These remain `difference` / exit 1, not trusted execution.

Frozen adaptation preserves destination Eq at 578/578 and source Eq at 556/578,
but its complete cross-block Eq audit is only 280/578. The unresolved cross-block
representation is not hidden by improved downstream accuracy. Next separate
relations already guaranteed by Bake's slot aliases/static wiring from genuinely
dynamic predictions; do not train or score a neural re-derivation of known
structural identities as if it were necessary work. General multi-block growth,
new result reuse, correction-token transitions, asynchronous audit and full
multi-stage saturation remain unfinished.

`relational_edges` now contracts matched neighbor roles with a matrix multiply
before multiplying local roles, avoiding the batch × ports × ports × 64 product
tensor. A dense-reference test checks FP32 numerical equivalence. Data generation
for this experiment used the previous implementation; device count parity above
also checks the resulting replay against the new implementation. No timing
speedup is claimed. Full text metrics are in `owner-block-third-results.json`.

## Compile known equalities; do not predict every cross-block pair

`neural_baked_eq` derives positive consequences from sealed constructor facts,
copy/union effects and the ownership layout's shared ports. Multi-argument
congruence requires all arguments; repeated congruence is saturated offline.
It never consumes instance IDs or CPU labels and never proves an unknown pair
unequal. Mutable reads and unsupported effects are explicitly uncovered. During
sample construction and device audit, independent exact labels must agree with
every compiled positive proof. Nonfinite neural outputs remain failures even on
proven pairs.

The `--baked-eq` audit option prepares one shared proof tensor per rule before
execution and applies it on GPU. It also applies before speculative frame
installation when that separate mode is used. Full Eq masks and graph acceptance
remain unchanged. Training can exclude proven positives from its loss, but the
experiments below performed **no new training**.

The cross-block prediction network was not part of the device's next-query
forward path; it was an auxiliary training/readout head. `--omit-cross-predictions`
skips that head and its loss, proposing only within-block Eq and static links.
Missing dynamic cross equalities still fail the full joint audit. They are
unresolved boundary work, not inequalities or excluded tables.

| Same frozen checkpoint, 578 positive owners | Full owner Eq correct after closure | States with false merges |
| --- | ---: | ---: |
| Neural local and cross readouts | 280 | 209 |
| Add static positive proofs | 361 | 209 |
| Static proofs, omit cross head | 565 | 4 |
| Also preserve source block unchanged | 571 | 0 |

All rows audit the same 40,200 typed pair obligations. Static compilation proves
4,909 positive pair occurrences. The last row is 98.79% within-owner Eq accuracy;
seven owners still omit relations (12 pairs after closure). It does not establish
correct external result addressing, scalar evaluation or whole-egraph execution.
Raw pair output is only 317/578 exact in that row: most omitted pair proposals
are consequences of the retained links, not additional required computations.
The archived auxiliary unseen split used the previous input fingerprint without
explicit proof tensors; do not infer a novel-state generalization rate from it.
Future proof-mode runs include those tensors in the fingerprint.

`OwnerBlocks.immutable_source` now bypasses the source-update network rather than
computing a zero update. Tests put NaNs in both skipped networks and verify finite
outputs and bitwise preservation of the source block. The existing two-block
storage still copies/retains the source vector in the destination arena; this is
semantic immutability, not a zero-copy storage claim. The switch is explicit in
the audit CLI (`--immutable-source`); it is not encoded in weight files.

Critically, downstream consumption is not solved. On the same 107 actual GPU
handoffs, adding single-rule static proofs leaves the updated-source model at
41/338 wrong next states, including four false merges. Preserving the source
instead yields 66/338 wrong next states, including nine false merges. All 107
handoffs and matching checks pass, but both semantic audits return `difference`.
Do not promote immutable-source execution merely because owner-state decoding
improves. Consumers currently read original block roles and do not explicitly
consume the combined owner's compiled completion description. The next task is
to make those consumer inputs ownership-aware while retaining positive birth
facts, rather than require every old block alone to represent the entire current
Eq state.

Reproduce owner readouts with `train_neural_owner_blocks.py ... --resume
FROZEN_WEIGHTS --freeze-base --baked-eq --evaluate-only`, adding
`--omit-cross-predictions` and then `--identity-source` for the two ablations.
Use `audit_neural_gpu_rhs.py ... --block-owner --baked-eq` with or without
`--immutable-source` for actual handoff/next-query checks. See
`baked-owner-eq-results.json`. No speed or native-runtime result is claimed.

## Ownership-aware consumer adapter (rejected, 2026-11-14)

The next experiment retains immutable source tokens and supplies consumer edges
with shared-owner connectivity, ordered block positions, and the compiled
64-float completion layout. Owner handles participate only in equality tests;
renumbering them leaves floating features unchanged. Masked, unsettled and stale
sources cannot supply these features. The physical handoff stores the layout
code atomically with its target owner. The replay builder verifies its lineage
reconstruction against actual device candidate features.

An opt-in `--owner-aware` path trains a zero-initialized 64x64 additive edge
adapter for 600 steps. Cell encoder/transition, Eq readout, source update and
cross readout are frozen; source updates and cross prediction are bypassed.
Backpropagation reaches the adapter through the frozen consumer. The zero adapter
is bitwise equivalent to the original consumer. Training uses the existing
synthetic block replay dataset, with no oracle token or label used as input.

This does NOT improve acceptance. Held-out next-state Eq falls from 541/625 to
521/625; false-merge states rise from 10 to 37. Internal owner Eq remains
571/578 with zero false merges. Actual GPU candidate enumeration after 107
successful transfers yields 273/338 correct next states and 23 false-merge
states, exactly matching the corresponding replay prefix. Match false positives,
misses and invalid predictions are zero. Both semantic audits return
`difference`. Context makes both owner blocks available in all 338 prefix cases;
this split does not establish behavior when only one block is available.

Costs are explicit: 4096 learned adapter parameters, 64 floats (256 bytes) of
layout code per allocated arena row, and temporary [batch, inputs, inputs, 64]
features plus their matrix projection. Codes are copied into destination rows;
this is not zero-copy or measured acceleration. Legacy prediction remains the
default. The prototype still allocates this metadata in block-owner mode.

Reproduce training with `train_neural_owner_blocks.py TRACE TRANSITION EQ OUT
--resume FROZEN_OWNER --owner-aware --identity-source --freeze-base --baked-eq
--omit-cross-predictions --third-train TRAIN_NPZ --third-test TEST_NPZ --steps 600`.
Audit with `audit_neural_gpu_rhs.py TRACE WEIGHTS OUT --owner-aware
--immutable-source --block-owner --baked-eq --interface-only --follow
--context-capacity 8 --limit 107`; compare `audit_neural_third_step.py TEST_NPZ
WEIGHTS OUT --owner-aware --block-owner --case-limit 107`.

`owner-context-results.json` records checkpoint/data hashes and rejection.
The checked Bake branch remains `codex/cell-parallel-admission` at `f3321a3a`,
a descendant of `56e28b89`. Its current-owner admission methodology motivates
using actual post-transfer directories, not interpreting old producer paths as
current ownership. The next unresolved obligation is a consumer representation
of specific compiled completion relations; adding a dense owner layout code to
the existing incidence edges is insufficient in this experiment. This result
does not justify refreshing old tokens or promoting this learned adapter.

## Conditional input-partition completion proofs (2026-11-14)

The additive owner adapter is still rejected. The next change uses a concrete
missing fact: successful consumer inputs may already be equal, but unconditional
Bake proofs previously ignored that input partition. `neural_conditional_eq.py`
enumerates typed query-input partitions and compiles the positive consequences
of each sealed Cell, including all-argument and multilevel constructor
congruence. GPU selection uses the existing exact query incidence, not CPU
matched bindings or reference answers. No handle magnitude enters inference.

The 17 context rules compile to 374 cases, occupying 25,956 bytes of NumPy proof
arrays (not total GPU memory). Cases are uploaded once and shared across all
107 scenarios. Selection is a fixed-shape batch comparison and reduction;
there is no device congruence loop. This is an exact proof side channel, not
learned floating computation or a claimed acceleration. The catalog has a
4096-partition budget per rule; unsupported operations or overflow retain only
unconditional proof and report unsupported coverage. No omitted case proves
inequality. Query-incidence shape is checked explicitly.

With the same immutable-source model, weights and 107 device transfers:

| Measurement | Unconditional proof | Conditional proof |
|---|---:|---:|
| Whole next-state Eq correct | 272/338 | 314/338 |
| Wrong next states | 66 | 24 |
| False-merge states | 9 | 9 |
| Missed / false query matches | 0 / 0 | 0 / 0 |

All positive proofs for accepted matches are checked against independent Python
reference execution. The full semantic audit remains `difference`; no typed
pair obligation was excluded. The 3,843 added proof occurrences include rejected
query candidates and are NOT a count of saved operations or committed facts.
The audit has 10 local-state disagreements and 17 states whose target includes
external Eq. These overlapping statistics are not a partition of the 24 errors.
Wrong states occur in rules 0 (14), 4 (1), 5 (8), and 8 (1); rules 4/5 account for
the nine false-merge states. See `conditional-eq-results.json`.

Reproduce with `audit_neural_gpu_rhs.py TRACE FROZEN_OWNER_WEIGHTS OUT
--immutable-source --block-owner --baked-eq --conditional-eq --interface-only
--follow --context-capacity 8 --limit 107`. This adds no backpropagation and does
not modify token vectors. The current audit consumes the proof at Eq readout;
it has NOT yet made that proof available as a generated token's subsequent
floating state. Carrying these particular relations through token completion,
resolving external constructor identity, and eliminating false merges remain
live obligations. Do not confuse the 92.90% next-state result with full Eggcc
saturation correctness or a complete ownership-transfer runtime.

## Target token carries static owner proof features (rejected, 2026-11-14)

`--proof-token` tests an actual change to the generated target block, rather
than a final readout correction. Bake encodes its positive source/source,
target/target and cross-block Eq proofs, with ordered port positions and original
source/target request codes, into 64 dense floats. A zero-initialized 64x128
learned matrix adds a residual to the new target token. The original source
block remains bitwise unchanged. The target token is adopted through physical
handoff and is directly read by subsequent GPU candidates; no refresh is run.

This experiment uses **static owner proofs**. The input-dependent conditional
proof selector from the preceding experiment still operates at the next Eq
readout; its selected dynamic cases are not yet encoded into the new token.
Do not claim that the complete conditional-proof feedback loop is solved.
The dense proof code is a model input, not a lossless proof certificate.

Training freezes the Cell encoder, transition, Eq head, source updater and cross
head. Only 8192 adapter weights train for 600 steps, with third-state Eq loss,
target-state Eq loss and residual magnitude regularization. Old saved replay is
upgraded from compiled template requests/proof codes, without reading label or
teacher-token columns. Ambiguous/missing template mappings fail explicitly.
The prototype stores another 64-float code per replay/chain record and performs
one dense projection per target generation; no speedup is measured.

The outcome is rejected. Held-out raw next-state correctness falls from 541/625
to 535/625, and false-merge states rise from 10 to 44. Internal owner correctness
falls from 571/578 to 568/578 (zero to three false-merge states). In actual GPU
execution with the unchanged conditional Eq proof overlay, all 107 handoffs pass
and matches remain exact. Full next-state correctness is 315/338 versus the
previous 314/338, but false-merge states rise from nine to 21. The apparent one
state improvement is not sufficient to accept the regression. Raw runtime
readout has 51 wrong states, exactly matching the 287/338 replay prefix.

Reproduce with `train_neural_owner_blocks.py TRACE TRANSITION EQ OUT --resume
FROZEN_OWNER --proof-token --identity-source --freeze-base --baked-eq
--omit-cross-predictions --third-train TRAIN_NPZ --third-test TEST_NPZ --steps 600`.
Run `audit_neural_gpu_rhs.py TRACE WEIGHTS OUT --proof-token --immutable-source
--block-owner --baked-eq --conditional-eq --interface-only --follow
--context-capacity 8 --limit 107`. It saves a static `.proof-catalog.npz` alongside
the report. Replay with `audit_neural_third_step.py TEST_NPZ WEIGHTS OUT
--block-owner --proof-token --proof-catalog CATALOG --case-limit 107`.
`proof-token-results.json` records all hashes and the rejected result.

A separate regression fix removes an unsupported `layout_code` keyword from the
legacy single-token handoff call; its one-case non-block GPU smoke passes. The
block path retains that argument. This does not change earlier block metrics.
Remaining obligations include separating established proof from undecided
relations in training and token representation, consuming dynamic conditional
proofs, arbitrary owner growth, and a genuine multi-stage saturation loop.

## Stage-specific execution boundary (2026-11-14)

Following the user's correction, pause universal-adapter tuning and use the
compiler's real stage structure. The captured Eggcc recipe has 548 rules,
30 declared and scheduled rulesets, 145 Run sites, 108 saturation scopes, and
nine repeat scopes (380 control instructions). Thirty-one rules occur in more
than one ruleset. A ruleset is a reusable module boundary, not necessarily one
unique lexical Run: the nested source control remains authoritative.

`lower_device_entries.py` previously assigned stages from rule `source_set`
annotations. Those are provenance and do not describe composed ruleset
membership. It now uses compiler `rulesets[].rule_ids` when present, emits a
static membership mask per Entry, and checks that mask during device proposals.
Rules without membership are marked instead of assigned an invented stage. Legacy
fixtures without formal rulesets retain their previous annotation-based layout.
Existing conservative cross-source Run boundaries remain; this change does not
authorize new cross-stage effects or claim complete query enumeration.

`device_stage_models.py` supplies a bank of compatible parameter tensors and
selects one stage's tensors at a batch boundary, using a device stage index.
It introduces no per-token learned router. `compile_program` derives schedule,
model-bank ordering and Entry stage numbering from the same ruleset ordering.
Missing stage models are explicit boundaries: `device_scheduled_runtime.run`
records `missing_stage_model`, admits no tokens/effects for that Run, and keeps
the control position pending. Existing completion and saturation requirements
remain unchanged. Finite parameters and matching tensor shapes are required;
different layouts need separate compiled batch families.

The compiled MLX GPU test runs two successive stages with distinct parameter
sets. Stage A creates a Cell; stage B consumes that Cell and creates the next
one. Stage B retains the existing token bitwise, and does not recode the graph.
Other tests cover composed membership, shared rule membership, unknown models,
compiler ordering and failure to advance an uncovered stage. This validates the
execution mechanism using the existing ridge Entry fixture, NOT trained
stage-specific neural accuracy or the complete Eggcc workload. Neural prototype
checkpoints remain scoped to the 17-rule context experiment. No accuracy or
speedup improvement is claimed for this change.

Costs remain explicit: compatible stage parameter tensors are stacked in memory,
and the batch chooses a slice. All stages' parameters remain resident; shared
weights are not yet deduplicated. Existing fixed query-block computation is not
pruned by this change. Full ownership composition, trained stage/family modules,
and multi-stage neural saturation remain unfinished.

Reproduce the structural audit with `audit_stage_modules.py TRACE OUTPUT`.
`stage-module-results.json` records the real compiler membership and control
structure; it uses no real Run as training data. The checked iterative Bake
branch remains `codex/cell-parallel-admission` at `f3321a3a`, containing
`56e28b89`. This work modifies the GPU prototype, not the native CPU executor.

## Train an actual second ruleset module: canon (2026-11-14)

The primary direct trainer, Eq trainer, owner trainer, replay builder and device
handoff audit now accept `--ruleset` and select compiler-declared membership via
`select_ruleset`. Source annotations no longer select their training rules.
The helper preserves declared rule order, remaps local IDs, discards stale event
routes/content hashes, and marks the single-Run control as an isolated training
scope with no substitution authorization. It does not replace the real schedule.
Each report retains original rule IDs and the stage manifest.

`train_neural_cell_transition.py --semantic` trains both ordered matching and
floating token Eq readout for a stage, from scratch. All eight canon rules
(global IDs 270–277) participated, including the two four-atom queries. Its batch
layout is four atoms, four fields, a 512-float input encoding and 512 incidence
features, with the existing 128-float token interface. Context checkpoints have
a different input layout and cannot simply be substituted for these weights.

The first real blocker was label reconstruction of constructor/copy literals.
`typed_literal.resolved` now reads exact executed i64 identities without creating
new reference identities. Labels support literal operands and scalar results;
large-i64 tests explicitly preserve values above 2^53. Generated constant facts
can participate in chain samples, but a literal has no producer payload slot.
Its projection is left uncovered instead of fabricating ownership of slot zero.
This is not GPU literal execution support: the device constructor compiler still
marks those sites, and only 80/160 positive evaluation chains have *compiled*
owner opportunities. No actual transfer is implied by that count.

Results (synthetic only; no real execution trained the model):

* Direct: 1024 training candidates, 256 evaluation candidates; matching 256/256
  and Eq 128/128. However 253/256 evaluation inputs overlap training, including
  every positive state. This is not evidence of unseen completion generalization.
* Two-step generated-token replay: 61 producer/consumer template pairs, all eight
  rules represented as producers and consumers. Train 320 positive + 120 negative
  chains; test 160 positive + 60 negative. Matching errors: zero. Whole Eq state
  correctness: 156/160, with two false-merge states. Of 62 unseen positive inputs,
  58 are exact. Zero-token readout is only 5/160; shuffled-within-template tokens
  are 69/160. This experiment actually consumes generated floating state rather
  than a teacher completion token, but CPU-generated routing is still supplied.

Reproduce direct training with `train_neural_cell_transition.py TRACE OUT
--ruleset canon --semantic --samples-per-rule 128 --steps 600`, followed by
`train_neural_eq_readout.py TRACE DIRECT.transition.safetensors OUT
--ruleset canon --steps 600`. `canon-stage-results.json` records full metrics and
checkpoint hashes. These results do not establish closed-loop GPU execution of
canon, cross-stage token compatibility, saturation or all 30 trained modules.
The next concrete execution gaps are literal operand projections and the
four-atom candidate layout; neither may be silently omitted to claim coverage.
No runtime speedup is claimed. The existing context one-case GPU handoff smoke
also passes with the new authoritative stage selection.

## Canon executes literals and four-atom follow queries on GPU (2026-11-14)

The constant-argument boundary is now implemented for exact i64 constructor
arguments. Source constants are reserved in the scalar identity namespace before
result allocation. Bake places their integer handles directly in constructor
site/view parameters; no per-instance constant slot or extra fact relation is
created. Constructor execution, deduplication and later witness projections use
these exact handles. Missing constants remain compiler boundaries, and handles
outside the reserved allocation prefix cannot execute. Tests distinguish
2^60+7 from 2^60+8 on GPU and verify result reuse. This is exact operand metadata,
not floating-number equality or a claim that scalar arithmetic is implemented.
Literal copy effects remain a separate unsupported site kind.

The independent graph decoder now reads literal values from the source operation
and its reserved scalar registry; it does not use compiled GPU view records.
Snapshot setup includes effect-table witnesses as well as query-table witnesses,
so externally existing constructor results are not accidentally omitted from the
oracle or device views. Plans are tied to their identity namespace and must be
rebound if that namespace changes.

Follow queries derive atom/field dimensions from the selected ruleset. Canon
uses four atoms and four fields. A known nullary constructor uses one candidate
lane instead of 16; four-atom canon queries therefore use at most 4096 combinations
rather than 65536. Overflow or conflicting resident nullary results still reports
incomplete coverage. This remains a bounded Cartesian diagnostic, not a scalable
join implementation or a measured speed improvement. A GPU test compares compact
and uncompressed four-atom joins against an independent reference.

Exact shared-slot constraints are now enforced on GPU candidate admission.
Candidate features are not filtered before model inference; raw model mistakes
remain counted as `constraint_rejected_predictions`. This removes nine false
admissions without claiming the learned matching head improved. Predicted tokens
remain floating model outputs; the guard does not prove their Eq contents.

The audit can now include pairs previously excluded by transfer-plan capacity
(`--include-uncovered-transfers`). Initial matching/bindings remain synthetic
CPU-provided inputs; subsequent candidate enumeration and constraints execute on
GPU. Per-pair payload capacity accounts for both lowered Cell layouts; physical
width is 38 or 42 slots here. Wider payloads and copied fields are costs, not free
compression. An uncovered prior plan does not authorize transfer: the local
physical plan is recompiled and checked. Two pairs needing 42 slots previously
retained separate ownership; all 61 now transfer successfully.

Actual standalone GPU results cover all eight canon rules as both producers and
consumers, across 61 observed template pairs (not every possible graph):

* 61/61 complete local graph checks pass; 61/61 physical ownership transfers pass.
  Interfaces and generated tokens are retained. No pending exact completion.
* 26 scenarios contain compiled constant constructor sites. Across independent
  scenarios, kernels create 141 constructors and 50 new equivalences.
* Subsequent matching: zero misses, zero false admissions, zero incomplete rules.
  The nine raw model false admissions are explicitly rejected by slot guards.
* Floating next-state Eq: 186/216 exact; 30 wrong states, including 24 false-merge
  states. Therefore overall status remains `difference`, with no promotion.

Reproduce using `audit_neural_gpu_rhs.py TRACE CANON.transition.safetensors OUT
--ruleset canon --include-uncovered-transfers --interface-only --follow
--eq-readout CANON.eq.safetensors --limit 64`.
`canon-device-results.json` records counts and hashes. This closes real execution
gaps beyond the earlier CPU-routed training experiment. It still does not prove
multi-stage saturation, asynchronous audit/repair or trustworthy generated-token
rollout. The next training/evaluation input must reflect this actual device
follow distribution rather than only the preceding two-step synthetic bindings.

### Canon actual-lineage third-step training

`canon-third-step-results.json` records standalone MLX GPU results. The replay
generator now admits all observed synthetic template pairs, compiles physical
capacity as in the RHS audit, and uses compact nullary query capacities. It does
not grant uncovered semantic-owner plans permission to transfer.

Generate with `neural_third_step.py TRACE DATA.npz --ruleset canon
--include-uncovered-transfers`: training uses `--count 8 --per-pair 2 --seed 23001`;
evaluation uses `--count 4 --per-pair 1 --seed 93003`. Resume the previous combined
canon checkpoint with `train_neural_eq_readout.py TRACE WEIGHTS OUT --ruleset canon
--resume --steps 600 --third-train TRAIN.npz --third-test TEST.npz`. Re-run the
full-width RHS audit with its emitted transition and Eq weights (same invocation
as the preceding canon device experiment).

The training set has 122 physical transfers and 476 positive third inputs; test
has 61 transfers and 216 positives. Tokens are recomputed through all three
steps, with gradients reaching prior transitions; reference labels are used
only in the loss. Exact synthetic routing remains fixed during training.

Full Eq closure accuracy improves from 186/216 to 208/216; false-merge states
fall from 24 to 4. Actual GPU audit reproduces 208/216, with all 61 graph checks
and transfers passing, and zero missed/false admissions after the same GPU
slot guards (9 raw match errors rejected). The unchanged two-step test remains
156/160. This is still `difference`, not successful saturation.

129 positive test inputs overlap training. Among the 87 unseen positives,
closed exact states improve only 76 to 79, and false-merge states 5 to 4. Thus
most improvement is on covered/repeated inputs, not evidence of broad
generalization. No third RHS is installed by this audit. Model and dataset
binaries are archived outside Git in `neural-canon-third-v18.tar.gz`.

### Remaining canon errors: inspect before changing representation

`canon-error-diagnosis.json` contains per-slot mistakes from the actual GPU
audit. Four false-merge states appear on local rules 6/7 after producers 2/4;
four missing-Eq states appear on rules 6/7 after producer 5. All four query
views in each failure come from the same generated Cell. Missing pairs are
absent when re-executing against only query facts, but present with the full
local oracle context. This diagnoses external constructor congruence, not
a general proof that the token cannot express it.

`audit_neural_input_collisions.py WEIGHTS OUT TRAIN.npz TEST.npz` compares exact
floating transition inputs (generated source tokens, edges, masks, requests,
and incidence) against masked Eq labels. The current 692 positive examples
produce 321 distinct inputs and no contradictory identical-input groups.
Thus missing information has not been proved; broaden synthetic four-atom
export-view and external-congruence coverage before adding a new runtime
representation. This test cannot establish sufficiency for unseen states.

The CPU diagnostic uses labels only after inference; it does not correct tokens
or feed labels into GPU inputs. Two unit tests cover transitive false merges,
external missing pairs, masked pairs, and nonfinite outputs. The actual GPU
audit remains `difference`. Neighbor Bake head remains f3321a3a; no new
ownership admission methodology was observed.
