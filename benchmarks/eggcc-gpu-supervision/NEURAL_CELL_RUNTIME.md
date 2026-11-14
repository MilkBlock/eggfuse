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
