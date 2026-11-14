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
