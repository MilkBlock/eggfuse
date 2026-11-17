# Frozen first neural multi-row generation experiment

This is the first neural-generation milestone, not a proof of full architecture
feasibility. Compression is not an acceptance criterion. Rows are parallel
sequences containing multiple tokens in the SAME graph; graph batches are a
separate dimension.

Each graph initially has A(anchor,key,value) and B(key,next,value) facts at
shuffled B positions across rows. Stage 1 must generate one Pair Cell for each
source A anchor by locating the matching B anywhere in the graph. Stage 2 must
consume the GENERATED Pair latents and generate Chain Cells joining Pair.next to
another Pair.key. Original A/B encodings are not passed to stage 2. Templates are
shared. Targets and the independent relational interpreter exist offline only.

Output positions follow the source A anchors: the first appended block in each
row holds Pair tokens; the next block holds Chain tokens. Thus this experiment
DOES NOT learn free allocation of obligations to rows or variable output counts.
It must still predict unsupplied partner bindings, decoded values and cross-row
references. No CPU provides a correct B or successor to an output row at inference.

Input positions: A at (row,t), B at (row,L+t); generated Pair at (row,2L+t),
generated Chain at (row,3L+t). Pointer attention uses separate row and token-position
rotations, in addition to content scores. Pointer metadata is gathered from the
NN-selected candidate index on GPU, not repaired by a reference interpreter.
There is no independent learned classifier for each candidate or output position.

Train two architectures from scratch: joint query interaction and within-row
query interaction. BOTH can read the same complete old graph memory, including
cross-row generated Pair tokens. The latter is not an isolated-input or separate-
graph baseline. Use two fixed initializations (1703,1709), 6,000 Adam steps at
0.001, batch 64; same corpus and final checkpoint only. Hidden width is 64.

Training layouts: (rows,length)=(2,3),(3,2),(2,4),(4,2), with 1,024 graphs each.
Their successor maps contain only 1/2-cycles. Evaluation includes distinct
in-distribution graphs, held-out long cycles at trained size, and larger 12/16-token
layouts. Key vocabulary is fixed at 16 and payload vocabulary at 4; this is not
arbitrary-ID generalization. Random key assignments must prevent ordinal shortcuts.

Report exact whole-graph correctness across BOTH stages, missing/invalid
obligations, duplicated partners, decoded field correctness and cross-row successor
correctness. Raw token count or a small loss is insufficient. Preserve all seeds
and both modes, including failures. Do not tune against final evaluation.

Timing initially compares joint and independent models and a diagnostic serial
execution of the same query function with shared input preparation. That diagnostic
is explicitly NOT a trained autoregressive baseline. A strong cached autoregressive
and single-row block baseline remain required later. No speed claim for eggcc or
full ownership/union inference can follow from this finite relation task.

No union events, arbitrary fact multiplicity, free ownership transfer, saturation,
real Bake discovery, locality scheduler or native eggcc execution are implemented
by this milestone. These remain in the active goal ledger.
