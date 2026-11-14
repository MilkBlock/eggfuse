# Trainable Cell runtime: execution contract and implementation plan

The user has authorized backpropagation. This supersedes the earlier requirement
that all trainable weights come from ridge regression. The objective remains
GPU-led Cell continuation, with generated tokens consumed on device and CPU
semantic audit. Training a classifier on CPU-provided successful matches does
not meet that objective.

This document separates implemented experiments from the proposed runtime. None
of the neural experiments below establishes an autonomous Eggcc saturation run,
executed ownership transfer, or a speedup over the CPU engine.

## Representation

A logical instance consists of a learned dense token and its existing exact
interface. Bake owns the template, typed slot layout, permitted successor
interfaces, source Run boundaries, and static storage-transfer maps.

The token carries reusable computed state, rather than a bag of node IDs. Seed
interfaces are encoded once. A generated token enters the next transition
without reconstruction of its node fields. Multiple output tokens are allowed
per input group: a template group has a bounded output block plus validity bits;
compaction and additional blocks accommodate dynamic information growth.
Overflow is unresolved work, never evidence of saturation.

Exact interface columns retain identity handles, scalar values where exact
semantics require them, instance generations, liveness, and storage ownership.
They are the instance's interface, not a second independently maintained fact
graph. Integer IDs are not cast into learned floating embeddings. Float tokens
cannot certify equality of arbitrary external identities.

Ownership transfer changes which live frame supplies an interface's storage;
it must not delete logical facts merely because their original storage is
retired. Compile the transfer from actual returned slot projections, including
constructor reuse, and preserve the source's still-live observations. Check
liveness, generation, readers, aliases, and destination capacity against the
existing ownership mechanism. Learned confidence alone cannot authorize a move.

## Learned computation

For a bounded family batch, use a shared encoder and transition:

```
seed interface -> encoder -> persistent token Z
(Z sources, interface incidence, template request)
    -> relation-conditioned attention + MLP
    -> accept logits + successor token block + proposed transfer selector
```

The currently implemented transition outputs one token and one accept logit per
candidate. The multi-output block and transfer selector are proposed extensions.
They must not be represented as completed functionality in coverage reports.

Do not pool away which ports are connected before processing the relation.
Current `neural_cell_samples.py` sums products of fixed port-role vectors into
one edge vector. The next representation should retain ordered interface-port
incidence up to the bounded template width, then use trainable projections for
edge keys/values. Padding is static and masked. This increases relation storage;
measure it against the old 64-float edge representation before promotion.

The main arithmetic remains batched floating matrix multiplication, attention,
MLPs and nonlinearities. Typed routing, address gathers and validity compaction
remain necessary; this is not a claim that arbitrary identity matching has
become a dense floating operation. Group work by compiled layout, avoiding
per-instance Python dispatch and a neural launch for each graph node.

Bake should supply bounded admissible interface routes. Whole table-pool
Cartesian products are useful for completeness audits but are not the scalable
runtime candidate generator. Routing must retain a residual or unresolved
indicator for uncovered connections; silently truncating candidates is invalid.

## Training

Use rule definitions and Bake interfaces to generate synthetic local instances.
Do not train directly on real Eggcc Run snapshots. Split by structural binding
patterns and producer-consumer combinations, not only by random numeric values;
report duplicate feature patterns explicitly.

Generate positive cases and typed hard negatives: exactly one violated shared
slot, several satisfied slots with one wrong relation, alias patterns, repeated
constructors, scalar boundary values, extra irrelevant neighbours, competing
consumers, and transfer attempts against retired or occupied storage. Legal
finite template connectivity does not imply a finite small scalar state space.

The initial implementation jointly optimizes:

- match cross-entropy;
- positive successor-token loss;
- initial encoder alignment;
- second-step loss using the first step's **predicted** token, with gradients
  flowing through both steps.

Extend this to bounded recurrent unrolls, branched outputs and converging routes.
Add auxiliary port-relation and continuation-observation losses so that a low
latent MSE cannot hide a wrong equality. Equivalent routes should preserve
observable interface facts; they need not have bitwise identical vectors.
Train transfer selection separately from its exact runtime authorization.

Ridge remains a controlled baseline and optional readout initialization. Do not
claim that adding backpropagation removes ambiguity already erased by the input
representation. Retraining must preserve single-step and other-family tests;
chain accuracy alone cannot justify promotion.

## GPU execution and CPU audit

1. Import a canonical stage input and encode initial interfaces once.
2. GPU routes active Cell interfaces through Bake-compatible candidate blocks.
3. Batched learned transitions produce successor tokens and proposed actions.
4. Fixed typed checks/compiled transfer maps authorize supported local actions;
   ambiguous or unsupported operations produce explicit unresolved marks.
5. Retain generated tokens and updated interfaces on device. Consumers read the
   resulting state directly. There is no CPU-style intermediate Entry packet
   publication within this device region.
6. Repeat the original ruleset Run schedule. A speculative fixed-point proposal
   requires no novel semantic action, no unresolved capacity/coverage marks,
   and no outstanding input changes. Vector equality or low confidence alone
   does not establish saturation.
7. CPU audits immutable batches with stage/Run provenance. It independently
   looks for omitted matches as well as checking accepted proposals. A CPU
   correction invalidates affected speculative descendants; stage results
   remain provisional until their dependency window is certified.

During the current validation phase, CPU verification remains authoritative.
Asynchronous audit does not permit irrevocable graph changes before their
prerequisites are certified. Later speculative execution needs versioned audit
windows and bounded recovery, not merely a queue of accepted GPU predictions.

## Implemented evidence

`3e6dfa48` introduced a learned encoder and relational transition for all 17
`context` templates. `508ffd63` trained two-step generated-token continuation.
Second-only loss reaches the first encoder, and tests reject teacher-token
leakage. Training uses synthetic inputs.

The two-step held-out candidate set has 1,154 tuples, of which 503 have feature
patterns seen during training. All 1,154 match labels were correct after
training; token MSE was 0.003883. Candidate connectivity was provided by synthetic
execution. A separate single-step check regressed from 543/544 to 542/544.
This model was **not promoted**. Compiled transfer opportunities were counted,
but no runtime ownership transfer was executed.

`neural_snapshot_candidates.py` now tests the missing candidate-distribution
boundary: actual GCD Run 437, all 17 context templates, 269 visible seed Cells.
It imports table pools once, encodes each seed once, constructs candidate tuples
and relational edges on GPU, and runs the trained transition. CPU successful
matches are not used to select model inputs. CPU independently enumerates the
reference matches after inference for each rule.

Results in `neural-snapshot437-results.json`:

| Measurement | Result |
| --- | ---: |
| Type-compatible candidate tuples | 5,111 |
| Evaluated / unresolved | 5,111 / 0 |
| CPU legal matches / GPU recovered | 40 / 40 |
| Accepted invalid tuples | 74 |
| Accepted tuples total | 114 |
| Precision / recall on this snapshot | 35.09% / 100% |
| Import / one-time encoding | 23.97 ms / 6.73 ms |
| Candidate computation and neural outputs | 102.08 ms |
| CPU audit, including reading predictions | 47.33 ms |
| CPU reference initialization | 14.82 ms |

Timing includes dispatch and first-use compilation and is a single diagnostic
run. It is not a CPU/GPU performance comparison. All successor vectors are
computed, but this audit does not validate or commit their effects. Six templates
have zero candidates in this snapshot: compiling all 17 does not mean exercising
all 17 at runtime.

The discrepancy between synthetic matching and this snapshot means the current
training distribution/representation does not establish reliable runtime
matching. It does not establish that a larger model alone fixes the problem.
Keep the real snapshot for evaluation; broaden synthetic interaction patterns.

## Next acceptance gates

1. Preserve ordered port incidence and generate exhaustive bounded equality
   patterns for supported template interfaces, with sampled scalar values.
   Compare against the current weights on synthetic structural holdouts and the
   frozen real snapshot. Report false acceptance and missed matches separately.
2. Replace diagnostic Cartesian enumeration with Bake-compatible routing. Use
   the exhaustive diagnostic as an oracle for routing omissions. Charge scans,
   gathers, compaction, encoding, relation construction and capacity handling.
3. Execute generated-token continuation plus actual ownership transfer, checking
   logical views before/after storage movement. Measure bytes moved, aliased and
   retained; a compiled opportunity is not an executed takeover.
4. Audit complete original ruleset fixed points and multi-stage control. Report
   false stopping, unresolved marks, CPU correction rate and audit throughput.
   Only then benchmark full GPU-led execution against the current CPU runtime.

Reproduce the current scoped checks:

```sh
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p 'test_neural*.py'
python benchmarks/eggcc-gpu-supervision/neural_snapshot_candidates.py \
  TRACE.json WEIGHTS.safetensors OUTPUT.json --snapshot-run 437
```

The saved result records trace and model hashes. This work does not change the
Cell CPU runtime; its Cargo benchmark campaign and final-state sum-bits contract
are not evidence for this standalone neural experiment.

## Follow-up: synthetic pooled candidate training

`neural_candidate_training.py` generates canonical constructor snapshots from
rule interfaces only. It combines independently generated Cells, optionally
sharing existing typed identities across instances. Reservoir sampling keeps
positive and negative candidates from bounded Cartesian enumeration. This is
sampled coverage, not an enumeration of all possible Cell interactions.
`train_neural_candidates.py` retains the original single-step and generated-token
two-step losses while adding matching loss on these pooled candidates.

The frozen GCD snapshot remains evaluation-only. Results and model hashes are in
`neural-pooled-candidates-results.json`.

| Training variant | Synthetic held-out FP / FN | GCD FP / FN | GCD recovered |
| --- | ---: | ---: | ---: |
| Original two-step model | — | 74 / 0 | 40 / 40 |
| Independent synthetic pools | 0 / 0 of 1,194 | 55 / 0 | 40 / 40 |
| Cross-instance sharing probability 0.35 | 2 / 0 of 1,256 | 55 / 0 | 40 / 40 |

The independent-pool test already had zero errors before fine-tuning. For the
sharing-aware test, 1,006 feature patterns overlap training. On the 250 unseen
patterns, errors decreased from three to two. Two-step matching retained zero
errors on its existing 1,154 tuples; positive-token MSE changed from 0.003883 to
0.003442 for sharing-aware training. These are local regression checks, not an
autonomous rollout acceptance test.

Real snapshot acceptance precision is still only 40/95 = 42.11%. Neither model
is promoted or allowed to commit graph effects. The follow-up supports changing
the relation representation before another data-only training sweep. Twelve
neural tests pass. The neighboring Bake branch remains `f3321a3a`; this experiment
introduces no alternative ownership representation.

```sh
python benchmarks/eggcc-gpu-supervision/train_neural_candidates.py \
  TRACE.json PARENT.safetensors OUTPUT.json --shared-fraction 0.35
# Use --shared-fraction 0 for the independent-pool control.
```

## Ordered interface relation experiment

The optional `--ordered` path retains actual ordered port incidence and the
query's required slot-sharing matrix. For the 17-template context family this
adds 200 floats per candidate (two 10-by-10 matrices), alongside the existing
pooled relation representation. Runtime creates incidence from identity handles
on GPU. It does not receive CPU match labels. These are structural inputs, not a
claim that identity comparison has become neural floating computation.

`OrderedCellTransition` learns a relation MLP and corrections to the match logit
and successor token. Zero-initialized output layers preserve the parent network
before training. The same projected query-interface features are available when
one input is a whole generated producer token; that token is not re-encoded.
Training gradients flow through the two-step token chain. The 15 tests include
second-only gradients reaching the initial encoder, invariance to ID renumbering,
and distinguishing different port connections with the same equality count.

Controlled 400-step training retains the same synthetic shared-pool dataset,
parent weights and chain objectives as the prior experiment. Results in
`neural-ordered-interfaces-results.json`:

- Synthetic pooled matching: 1,253/1,256, with three false positives.
- Unseen pooled feature patterns: 247/250 (three false positives).
- Two-step matching: zero false positives or negatives on 1,154 tuples.
- Positive two-step token MSE: 0.002769, versus 0.003442 without ordered features.
- Real GCD Run 437: unchanged 55 false positives and 40/40 recovered matches.

This did not improve real matching and is not promoted. Lower token loss is not
semantic completion. Next training should enumerate bounded typed interface
alias patterns rather than rely on a small random sample; retain the real
snapshot as evaluation-only. No graph effects or ownership transfers were
executed by this experiment.

Backpropagation currently updates the initial encoder, relational attention,
transition MLP, accept/token heads, and optionally this relation correction.
It does not update Bake, identity incidence, the reference target-code
construction, or ownership authorization. Forward GPU execution uses the trained
weights and does not perform gradient updates.

## Exhaustive typed interface patterns

`neural_typed_patterns.py` enumerates restricted-growth strings for each type's
query-port positions and takes their Cartesian product. This includes partial
sharing that random input generation missed. The 17 context templates have
1,480 raw typed partitions in total. Constructor congruence canonicalizes each
local input before labels are assigned; duplicate feature patterns are removed.
A capacity overrun raises an unresolved-coverage error, never silent truncation.

Training uses scalar bases 0 and 3; evaluation uses -9 and 17. Both enumerate the
same bounded structural patterns. Each dataset contains 1,559 feature tuples;
1,395 evaluation tuples overlap training features, so this is intentionally not
an unseen-structure generalization claim. It is also not exhaustive coverage of
scalar values, mutable state, hidden facts, lifecycle conflicts or long rollouts.

Two successive 400-step training phases retain generated-token chain losses.
The original model made 642 false acceptances on the exhaustive evaluation set.
After phase one it made four; after phase two it made one. All 164 feature tuples
not seen in training were classified correctly. The existing two-step test
retained zero false positives/negatives on 1,154 tuples, with positive-token MSE
0.002484 after phase two. Exact semantic token execution remains unverified.

Frozen actual-input snapshot audits after phase two:

| Snapshot | Candidates | Legal / recovered matches | False positives | False negatives | Uncovered typed patterns |
| --- | ---: | ---: | ---: | ---: | ---: |
| GCD Run 437 | 5,111 | 40 / 40 | 1 | 0 | 0 |
| LCM Run 514 | 13,288 | 109 / 109 | 1 | 0 | 0 |

All candidate patterns were present in the finite structural catalog. This
separates structural coverage from learned correctness: coverage is complete for
these query-interface patterns, but the network still makes a false acceptance
on each snapshot. The model remains unpromoted. No effects, ownership transfers,
or saturation claims follow from these match counts. Real snapshot data was
not used as training input. Details/hashes: `neural-typed-patterns-results.json`.

```sh
python benchmarks/eggcc-gpu-supervision/train_neural_candidates.py \
  TRACE.json PARENT.safetensors OUTPUT.json --ordered --typed-patterns
python benchmarks/eggcc-gpu-supervision/neural_snapshot_candidates.py \
  TRACE.json OUTPUT.safetensors AUDIT.json --snapshot-run 437 \
  --ordered --typed-coverage
```

Nineteen neural tests pass, including Bell counts through seven positions,
independent matching of normalized patterns, and explicit capacity failure.
The neighboring Bake branch remains `f3321a3a`.

## Generated-token / ownership integration

`neural_owner_handoff.py` connects a generated token proposal to the existing
sealed-payload transfer mechanism. A successful transfer adopts the target token
atomically. Model rejection, missing certification, nonfinite output, stale
generations, incompatible values or lack of quiescence leaves both token and
ownership state unchanged. The old logical Cell remains live through the new
owner's static field projection; storage release does not retire logical facts.

`audit_neural_owner_handoff.py` runs the two-step trained model and the ownership
kernel on GPU. Source tokens are encoded in one batch and directly consumed by
the second transition; transfer candidates do not re-encode their sources.
The audit uses the held-out synthetic chain fixtures. CPU exact execution
initializes both sealed interfaces, including RHS results, and independently
checks that all readable interface columns survive the move. It also poisons
released storage and checks that the original Cell still reads correctly.

Result: 276 attempted transfers, 276 completed, 770 copied fields, zero interface
or token-preservation failures. These are independent two-frame fixtures, not
276 successive moves within one live graph. They measure executed physical
storage takeover, not logical activation retirement or complete neural Cell
execution. Source and target tokens stay at logical addresses; the payload's
physical owner changes. The target token changes because it is the newly
computed continuation output, not because storage compaction changes semantics.

Twenty-one neural tests and seven existing owner tests pass. Negative transfer
cases run on both NumPy and MLX GPU. Details are in
`neural-owner-handoff-results.json`. No speedup is claimed. This uses the existing
Bake-derived projection/alias plans; the neighboring branch remains `f3321a3a`.

```sh
python benchmarks/eggcc-gpu-supervision/audit_neural_owner_handoff.py \
  TRACE.json WEIGHTS.safetensors OUTPUT.json
```

The next missing execution boundary is GPU creation/completion of the target's
exact interface before this takeover. This experiment deliberately does not
claim that CPU-prepared RHS values were generated by the neural network, nor that
byte-preserving token adoption proves the token's predicted semantics.

## GPU target RHS completion before takeover

`audit_neural_gpu_rhs.py` removes CPU-prefilled target effects from the preceding
integration test. The CPU supplies an initial graph, a completed producer and a
consumer's input binding. Every non-query target slot starts invalid. GPU
constructor/copy/union kernels create and fill exact target metadata; the learned
successor token remains resident throughout completion. Original constructor
assignments are lowered to construct-plus-union, and an independent CPU oracle
executes the original, unlowered selected instance for post-execution comparison.

The GPU executes two bounded completion passes, then attempts the static owner
transfer on ready targets. The existing registry handles exact identities;
this does not claim that the neural network predicts integer IDs. Neural
acceptance gates target activity. These fixtures are valid bindings, so this
experiment is not a new false-positive audit or autonomous candidate enumeration.

All 107 collected producer/consumer template pairs were executed:

- 107/107 final graphs agree with the independent CPU oracle.
- 396 effect operations executed; 169 constructor result identities allocated;
  109 equivalence-class merges; zero pending completion marks.
- 84 transfers executed and moved 290 unshared fields.
- 23 transfers were statically uncovered because the lowered temporary slots
  exceed the fixed payload capacity. Their original storage remains in use.
- All 107 interfaces were preserved, and all 107 neural successor tokens were
  retained rather than overwritten by exact-slot encoding.

These are independent local snapshots, not a growing global graph. Allocation
and operation counts are not logical rule-match counts or memory speedup claims.
The 33-second audit includes fixture generation, CPU oracle checks and dispatch;
it is not an execution-time comparison. Details: `neural-gpu-rhs-results.json`.

Twenty-two neural tests pass, including a case that starts with an empty RHS
slot, executes its constructor on GPU and checks the resulting graph. The
neighboring Bake branch remains `f3321a3a`; no CPU runtime paths were changed.

```sh
python benchmarks/eggcc-gpu-supervision/audit_neural_gpu_rhs.py \
  TRACE.json WEIGHTS.safetensors OUTPUT.json --limit 107
```

The remaining execution gap is constructing the next consumer's inputs from
these device-produced interfaces, repeatedly applying learned continuation and
handling boundaries without CPU-supplied successful bindings. Full Run/stage
fixed points and dynamic ownership conflicts are still unverified.

## Device-produced interfaces feeding another learned query

`neural_device_candidates.py` compiles query interface routes against the current
Cell templates. On GPU it projects through the ownership directory, removes
same-fact duplicates (preferring later producers), compacts a bounded per-atom
pool, and constructs type-compatible candidate tuples. It does **not** filter
those tuples by successful query bindings. Whole generated source tokens and
current ordered interface relations enter the learned transition directly.
Seed tokens are encoded once; source and target predictions are preserved across
exact completion and ownership changes. No CPU successful bindings are supplied
for this following query round.

The `--follow` audit evaluates all 17 context queries on each of the 107 local
post-completion states, then independently checks candidate consistency and
complete match sets on CPU. Runtime constructor identities are mapped to the
CPU oracle only after exact whole-local-graph comparison passes. Missing mapping,
incomplete routing, nonfinite predictions, false acceptance and omissions cannot
establish acceptance. The command returns exit 1 when following matches fail,
even if the preceding RHS graph comparison passed.

Observed result (`neural-device-follow-results.json`):

| Following-query measurement | Count |
| --- | ---: |
| Live type-compatible candidates | 1,659 |
| Model accepted | 1,382 |
| Accepted invalid candidates | 1,070 |
| Legal matches / recovered | 312 / 312 |
| Recovered candidate tuples using the generated target Cell | 240 |
| Incomplete query enumerations / nonfinite predictions | 0 / 0 |

The audit status is **difference**, exit 1. No following prediction was committed
as an effect. This demonstrates device-to-device data delivery, but contradicts
reliable learned continuation. These results must not be combined with the
seed-snapshot 40/40 and 109/109 results to claim a correct recurrent runtime.

The current ordered model adds a relation correction to a token-conditioned
match logit. Consequently, the same required interface conditions can receive
different acceptance decisions when the source token/layout changes. For the
current slot-only constructor queries, exact interface incidence determines
binding consistency independently of latent token content. The next architecture
change should enforce that separation rather than train a residual to cancel an
unbounded token-dependent match score. Future scalar guards need their actual
predicate inputs; they are not covered by this slot-only conclusion.

The bounded Cartesian device pool is a diagnostic. It is not the final efficient
routing mechanism or a full multi-stage saturation loop. Source token semantics
also remain independently unproven; moving a vector without CPU reconstruction
does not prove it encodes a correct completed Cell.

Twenty-seven neural tests pass. New checks cover initial seed-encoder parity,
reading a GPU-created result through transferred storage, retaining invalid
candidate tuples for the classifier, explicit overflow, and rejecting an audit
with failed or missing following-query evidence.

```sh
python benchmarks/eggcc-gpu-supervision/audit_neural_gpu_rhs.py \
  TRACE.json WEIGHTS.safetensors OUTPUT.json --limit 107 --follow
# Current trained model: expected semantic audit exit is 1, not 0.
```

## Matching isolated from latent source content

`InterfaceCellTransition` specializes the current slot-only constructor family.
Its match logit comes exclusively from the learned ordered-interface MLP. Whole
Cell tokens still enter relational attention and successor generation, and token
loss still backpropagates through the recurrent computation. Matching remains a
GPU floating neural forward pass; no CPU match result is used as its input.
The interface incidence itself remains exact metadata, not a learned identity.

This specialization is explicit (`--interface-only`) and does not silently change
the old checkpoint interpretation. It is not valid for arbitrary scalar guards,
mutable reads or other predicates without supplying their required inputs.
Tests establish that changing source tokens, attention edges and requests while
holding the interface fixed cannot change the match score, while successor
tokens and their source gradients remain nonconstant.

After 800 synthetic-only joint training steps:

| Evaluation | Correct / expected | False positives | False negatives |
| --- | ---: | ---: | ---: |
| Typed-pattern evaluation | 1,559 / 1,559 | 0 | 0 |
| Existing two-step tuple evaluation | 1,154 / 1,154 | 0 | 0 |
| Actual GCD Run 437 | 40 / 40 | 0 | 0 |
| Actual LCM Run 514 | 109 / 109 | 0 | 0 |
| Following queries on 107 device-completed local states | 312 / 312 | 0 | 0 |

The last row uses 1,659 live candidates, of which exactly 312 are accepted; 240
accepted candidate tuples read the generated target Cell. Routing was complete
and all predictions finite. The preceding exact RHS checks and 84 covered owner
transfers still pass; 23 layouts retain their earlier capacity boundary. The
following-query audit now returns `pass` / exit 0. It does not yet commit these
following matches into another RHS round or establish a stage fixed point.

`audit_neural_interface_patterns.py` additionally enumerates all 1,480 typed
partitions and checks the 1,075 distinct ordered-interface signatures (258
positive, 817 negative). All classify correctly at batch sizes 1, 64 and 256.
The minimum signed logit is approximately 1.18235, and maximum observed batch-size
variation is 0.00000763. This is exhaustive finite-domain empirical validation
on the current backend, not a formal floating-point roundoff proof or a proof
of routing/lifecycle correctness.

The typed-pattern evaluation intentionally shares structural patterns with
training: 1,395 of its 1,559 feature tuples overlap. All 164 unseen scalar-feature
tuples pass; since this matching head does not consume scalar magnitudes, that
is not generalization to scalar predicates. Positive two-step token MSE is
0.000308; latent accuracy alone still does not prove downstream semantics.
Both architecture and training duration changed, so this is not an isolated
performance or optimization ablation.

Twenty-nine neural tests pass. Details, hashes and reproduction commands are in
`neural-interface-head-results.json`. This variant remains opt-in, with no
full-runtime performance or multi-stage saturation claim. The next step is
committing these device-produced following bindings and iterating at original
Run boundaries with semantic deduplication and explicit capacity obligations.


### Semantic token readout (synthetic training, real evaluation)

`train_neural_eq_readout.py` jointly trains the encoder, Cell transition and
`neural_eq_readout.py` through two generated-token steps. The previously trained
interface matching layers are frozen. The readout receives only a 128-float
successor token and the 64-float template request, never exact IDs or incidence.
Targets are same-sort Eq pairs in the completed local Cell; scalar/cross-sort
pairs and invalid matches are masked. Adam updates use direct and chained Eq
losses plus the existing token/alignment losses. Real snapshots are evaluation
only. This remains a standalone prototype: Eq predictions do not mutate graphs.

The 800-step run produces 576/578 exact synthetic states after closure, with no
false merges; 324/326 states with unseen chain input fingerprints are exact.
There are 503 overlapping chain fingerprints (including negative examples), so
this is not an entirely unseen evaluation set. Within-template token permutation
reduces exact states to 410/578 and creates 86 states with false merges, supporting
that dynamic token contents affect semantics. Fixed reference codes are not an
upper bound after decoder/encoder co-adaptation.

Real first-Run evaluations are **not accepted for semantic execution**: GCD has
36/40 exact states and LCM 104/109; each has two states with false merges. All
errors occur in source rule 287. An independent oracle restricted to the supplied
query facts gives exactly the same Eq labels as the full imported oracle on these
cases, so missing external context does not explain these failures. The full
oracle remains the target; this diagnostic never excludes boundary errors.
Matching remains exact on these selected candidates. Neither these counts nor
the earlier exact RHS kernel prove a floating-token saturation runtime.

Reproduction (use the MLX environment and artifact paths in the result manifest):

```sh
python train_neural_eq_readout.py GCD_TRACE INTERFACE_WEIGHTS OUTPUT.json
python train_neural_eq_readout.py GCD_TRACE OUTPUT.safetensors ABLATION.json --evaluate-only
python neural_snapshot_candidates.py GCD_TRACE OUTPUT.transition.safetensors GCD.json --snapshot-run 437 --ordered --interface-only --eq-readout OUTPUT.eq.safetensors
python neural_snapshot_candidates.py LCM_TRACE OUTPUT.transition.safetensors LCM.json --snapshot-run 514 --ordered --interface-only --eq-readout OUTPUT.eq.safetensors
```

Weights and full logs are archived outside Git; `neural-semantic-eq-results.json`
records hashes, metrics, CPU audit times and the archive location. CPU audit times
include per-candidate oracle cloning/completion and are not a production auditor
throughput claim. Next work must address rule 287 using synthetic counterexamples,
then connect accepted semantic state to subsequent GPU computation; do not merely
loop the exact RHS path and call the floating token an executor.


### Typed semantic coverage and post-transfer consumption

The typed partition generator now optionally labels the completed Eq state,
including aliases introduced by RHS constructor reuse. `--typed-patterns` adds
this supervision to the floating-token loss. Invalid matches have no Eq labels;
semantic batches sample valid states by default. `--typed-all-candidates` retains
the initial ablation, and `--resume` loads the combined transition/readout weights
(the Adam optimizer is restarted). Both still use synthetic states only.

Reproduce the two updates from the previous semantic checkpoint:

```sh
python train_neural_eq_readout.py GCD_TRACE PREVIOUS.safetensors TYPED.json --typed-patterns --typed-all-candidates --resume --steps 800
python train_neural_eq_readout.py GCD_TRACE TYPED.safetensors POSITIVE.json --typed-patterns --resume --steps 2400
python audit_neural_gpu_rhs.py GCD_TRACE POSITIVE.transition.safetensors FOLLOW.json --limit 107 --follow --interface-only --eq-readout POSITIVE.eq.safetensors
```

The second update fits all 398 valid enumerated training states. Real seed
snapshots reach 40/40 GCD and 109/109 LCM completed Eq states with zero false
merges. These are finite first-Run checks, not real saturation runs. The synthetic
two-step set regresses from 577/578 to 574/578 closed exact states, with two
false-merge states. No model is promoted on the strength of the seed results.

The optional Eq readout in the GPU ownership audit evaluates the next generated
token after device candidate gathering. It uses the existing token directly;
CPU completion labels are computed afterwards and never enter inference.
Matching, exact RHS correctness, physical ownership transfer, and learned
semantic correctness are separate checks. A semantic mismatch makes the audit
exit 1 even when exact RHS and matching pass. Nonfinite Eq scores cannot count
as correct negative predictions. The exact RHS path is still an oracle-backed
prototype scaffold, not the final floating semantic executor.

Across 107 local snapshots, all exact graphs/interfaces/tokens pass; 84 physical
transfers execute. Following device queries recover all 312 expected matches
(240 accepted tuples read the generated target), but 32 completed states are
wrong and 12 have false merges. Restricting the oracle to the actual query facts
still leaves 18 wrong states; 16 states have additional equalities induced by
external facts. These counts overlap and must not be subtracted as disjoint
error categories. Full-context audit status is `difference` / exit 1.

Thus matching/ownership correctness does not establish semantic token
continuation correctness. Next work needs synthetic generated-source training
coverage and explicit representation or marking of unavailable boundary context,
not just more single-step fitting. Sources, hashes and aggregate failures are in
`neural-semantic-typed-results.json`; full reports/weights are in its archive.
