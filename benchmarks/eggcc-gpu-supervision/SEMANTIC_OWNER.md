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
