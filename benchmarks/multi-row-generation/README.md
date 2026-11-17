# Neural complementary token generation in one graph

This is a neural two-stage relational Cell-generation experiment. One graph has
multiple rows, each with multiple A and B source tokens. Stage 1 locates B partners
for A anchors and generates Pair latents; stage 2 consumes only those GENERATED
latents and generates Chain tokens referring to other generated Pair tokens.
Original A/B encodings are not passed to the second stage. CPU audits happen only
after generation, controls and timing; there is no correction or answer fill.

The two shared templates represent A(key,value) + B(key,next,value) -> Pair,
then Pair(...,next,...) + Pair(key=next,...) -> Chain. Each output carries learned
field values and an NN-selected partner pointer with a row/position address.
Template and source-anchor roles are supplied; the partner binding is not.
Output positions follow source anchors. Free row allocation, variable matching
multiplicity, union, ownership conflicts and native eggcc are NOT covered yet.

Each graph is `[rows, tokens_per_row, latent_width]`; independent graph batching
is separate. Attention uses row and within-row rotations plus content scores.
Both joint and independent-query variants may read the same complete previous
memory. Independent-query mode masks current query-to-query interaction to the
same row; the current implementation still uses dense masked matrices, so it is
an architectural ablation, not an optimized sparse implementation.

## First frozen experiment: failure retained

The first protocol trained on graphs whose successor maps have only 1/2-cycles.
All four runs (two modes, seeds 1703/1709) fitted training replay and the seen
panel, but failed every whole graph in the held-out long-cycle and larger panels.
Second-stage pointers selected the PREDECESSOR, not the required successor:
2,048/2,048 long-cycle pointers match the inverse permutation for every run.
Those directions are identical on the training involutions. This is a genuine
training-identifiability failure, not evidence that the CPU needs to repair output.

The decoded Chain values can be consistent with the WRONG selected parents;
therefore value accuracy alone is insufficient. The independent relational guard
rejects the incorrect binding and the complete graph fails. Results, source hashes,
all seeds, the direction diagnosis and unit checks are in `results/involution`.

Timing in that experiment serializes the same query function with shared input
preparation and cached pointer K/V. It is explicitly NOT a trained autoregressive
baseline. Timing invalid outputs cannot establish useful completion throughput.

## Runtime and audit boundaries

`task.py` builds initial source relations and OFFLINE supervision. `network.py`
imports only vocabulary/template constants, never the interpreter or labels.
Its two-stage recurrence uses generated floating Pair states directly. Supervision
is on both pointer choices and decoded fields; no teacher Pair state is injected.
`run.py` runs generation and controls before calling the independent CPU join
checker. The CPU re-decodes actual latent bytes with the frozen readout weights.

The next experiment must break the forward/backward ambiguity in training and
freeze fresh structural holdouts. The inspected first holdouts are now diagnostics,
not untouched final acceptance. The full architecture goal remains unproved.
