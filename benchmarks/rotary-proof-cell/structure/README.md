# Structural holdout experiment: the recurrent MLP does not generalize reliably

The three frozen runs all pass their training replay and seen-factor test panel,
but fail cross-structure semantic acceptance. **Generated latent recurrence and
retired-payload masking work; they do not ensure preservation of unseen structure
or correct union/transfer composition.** CPU audit reports failures without
repairing them. This is a standalone synthetic experiment, not the egglog runtime.

The preceding model only had input fields for one fixed four-member shape. This
experiment expands the ABI and retrains the same recurrent MLP family from
scratch; it does not pretend that the old checkpoint could express these shapes.

## Frozen experiment

The [protocol](PROTOCOL.md) was fixed before training. Each of three seeds uses
32,768 distinct training examples, 12,000 Adam steps and the final checkpoint.
There was no evaluation-driven model selection or retraining.

A Cell initially contains four leaves and four F/H constructor members. The
network receives their operator/argument plan, an optional union request, an
LHS query `Request(x,x)`, two adjacent-swap layout commands, and four annotation
bits. The three Runs build members, union plus congruence, and conditionally
construct `G(x)` with ownership transfer. Each Run consumes the previous generated
128-float latent. No intermediate teacher state, reference layout or proof enters
inference. Training supplies decoded-field supervision only.

There are 8 training shapes and 2 fully withheld shapes; 10 training union endpoint
pairs and 2 fully withheld pairs; 24 training resulting mappings and 4 fully
withheld mappings. Shapes are checked modulo leaf renaming. Mappings are split by
the final permutation, including deduplication of commuting command sequences.
No shape, union-pair or mapping ID is a network feature. Every individual input
opcode, argument-position feature, union endpoint and swap position occurs in
training. Input features describe the **commands**, not the target alias table.

All panels contain 2,048 distinct cases. The seen-factor panel has no exact
training-row overlap: 1,022 cases repeat a semantic tuple with another annotation,
while 1,026 have a semantic tuple absent from training. All three models pass both
subsets. Thus the model does exhibit some recombination within its training
factor vocabulary; it is not merely reproducing exact input rows.

## Exact results

A pass requires all three decoded states, proofs, obligations, structural facts,
port projections, owner/position bindings and old-reference reads to be correct.
CPU decoding uses the saved latent bytes and agrees with GPU discrete decisions
in all panels. Low average loss does not count as a pass.

| Panel | Seed 1703 | Seed 1709 | Seed 1721 |
| --- | ---: | ---: | ---: |
| Training replay | 2048/2048 | 2048/2048 | 2048/2048 |
| Seen factors, new input cases | 2048/2048 | 2048/2048 | 2048/2048 |
| Held-out complete Cell shapes | 1/2048 | 4/2048 | 0/2048 |
| Held-out union endpoint pairs | 982/2048 | 982/2048 | 982/2048 |
| Held-out composed transfer mappings | 580/2048 | 112/2048 | 0/2048 |
| All three factors held out | 0/2048 | 0/2048 | 0/2048 |

The union and mapping totals hide a more important failure:

- **Union enabled:** 0/1,066 exact post-union equality states for every seed.
  All 982 passing traces have union disabled. The held-out union panel has no
  additional congruence-derived equalities beyond its requested pair; even this
  direct pair generalization fails. It is not a test of novel deep closure there.
- **Transfer required:** 0/370 complete alias tables for every seed in the mapping
  panel. All full-trace successes there are deferred cases. The models correctly
  identify when transfer is required in this panel, but cannot produce its map.
- **Structural information retention:** the held-out shape is already preserved
  incorrectly at Run 1. Exact shape retention is 4, 35 and 0 cases respectively.
  In 1,075, 1,025 and 918 cases, the decoded shape is exactly one of the training
  shapes instead. Remaining failures include hybrid structures.

See [summary](results/summary.json), [failure decomposition](results/diagnosis.json),
and complete [1703](results/seed-1703.json), [1709](results/seed-1709.json),
[1721](results/seed-1721.json) reports. Masks are tested for **predicted** retirement,
including erroneous decisions; mask success is not evidence that retirement was
semantically legal.

## Representative failures

**A new shape gets rewritten into a familiar one before union.** The input is:

```text
u = F(a)       v = F(b)
w = H(u,u)     t = H(v,v)
```

The seed-1703 output instead decodes:

```text
u = F(a)       v = F(b)
w = H(u,c)     t = H(v,c)
```

That is an exact training shape. No source rule authorizes replacing the second
arguments with c. The original information-preservation contract has failed,
even though many later equality decisions remain correct. Every individual
output symbol/slot value needed by this shape was seen during training.

**An unseen union pair is changed.** For a request `union(role1, role3)`, one
certificate emits `union(role2, role3)` and does not perform the expected transfer.
The checker rejects both the premise mismatch and missing equality.

**Correctly retained commands do not imply their correct composition.** One
transfer case retains swap commands `[2,1]`, but generates:

```text
expected alias: [0,2,3,1,5,6,7,8]
decoded alias:  [2,0,1,2,5,6,7,8]
```

Two old members now alias the same target slot. In seed 1703, 157 required-transfer
cases retain both commands correctly, yet none produces the correct full map.

## Why this is not a clean universal test of neural reasoning

The output-support audit identifies an architectural confound worth making
explicit. The decoder uses independent equality bits for specific endpoint pairs
and independent categorical heads for specific role/slot choices.

- Withheld union pairs `(1,3)` and `(4,6)` never have a positive equality bit in
  training. Their individual endpoints are seen, but those output coordinates
  are trained only toward false.
- Every required held-out mapping includes an alias/layout coordinate with a
  target class never positive at that coordinate in training. The inputs' two
  primitive swaps are familiar, but the decoder has no parameter-sharing contract
  that derives their composition.
- This confound does **not** explain away the shape-retention failure: all output
  atoms required by the shape panel occur in training, yet its strict acceptance
  is almost zero.

The evidence supports limited factor recombination, loss of unseen structural
information in the latent encoder/decoder, and missing systematic parameter
sharing in relation/port outputs. It does not prove that all network computations
are table lookup, that a neural model cannot learn the rules, or that the earlier
20-pattern checkpoint specifically memorized every case.

The next architectural experiment should preserve the input Cell structure through
a faithful GPU-side path and use shared functions over port pairs/pointers,
instead of a different output classifier for every possible relationship. Reuse
these cases as diagnostics and reserve a **fresh** structural holdout for final
acceptance after development; these reported test cases are now inspected.

## No teacher or CPU repair on the inference path

- Every inference and old-reference read runs on Metal; CPU constructs initial
  inputs and launches work, then performs independent audit.
- Direct `advance(generated_latent_2)` equals the third rollout tensor bit for bit.
  The final-stage gradient to initial inputs is nonzero. Clearing the second
  latent changes the third decoded state in 32/32 probed cases for each seed.
- Retired old payloads are poisoned with NaNs and masked before arithmetic.
  Reads are unchanged for every predicted retirement in all runs.
- The source interpreter used for supervision uses union-find with signatures.
  The independent checker uses relational transitivity and pairwise congruence.
  Six contract tests plus one GPU recurrence test pass.
- Separate NumPy-only audit processes reproduce seen-factor 2048/2048 (exit 0)
  and union 982/2048 (exit 1). The latter is a recorded failure, not a corrected
  result. Saved checkpoints remain audit artifacts, not runtime fallback state.

The runtime's rotary operators, discrete routing and masking are fixed GPU
operations. Rotations are addressing features, not proofs. This remains fixed
size, fixed three-Run scheduling and a manually specified proof vocabulary. It
has no automatic Bake, arbitrary graph matching, bitwise canonical latent claim,
compression result or performance comparison.

## Reproduce

Use the parent `requirements.txt` on an Apple Silicon Mac with Metal. Keep binary
outputs outside Git. On the shared machine, use the experiment queue:

```sh
# Repeat with seeds 1709 and 1721, changing the output directory.
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/experiment.py \
  /path/to/artifacts/seed-1703 --seed 1703

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/test_structure.py
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/test_network.py

# Independent CPU audit, no MLX import or model forward execution:
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/audit.py \
  /path/to/artifacts/seed-1703/union-checkpoints.npz

# Post-hoc diagnosis and text evidence collection:
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/diagnose.py \
  /path/to/artifacts /path/to/artifacts/diagnosis.json
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/structure/collect_results.py \
  /path/to/artifacts /path/to/text-results
```

Model and source hashes, data hashes, environment, actual artifact paths and the
full training curves are in the reports. The experiment exits 1 when any semantic
panel fails; a completed experiment is not synonymous with semantic acceptance.
