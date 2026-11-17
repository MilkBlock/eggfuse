# Direction-identifiable training and fresh fan-in acceptance

The first experiment is frozen at commit 576063f5. All four models learned the
inverse successor; on involutions this exactly fits every training label. Do not
hide or reinterpret that failed generalization.

This follow-up changes ONLY the training graph family to permutations with cycles
of length 1, 2 or 3. It uses the same architecture, two modes, two initializations,
4,096 training graphs, 6,000 Adam steps, learning rate 0.001 and batch 64. Three-
cycles distinguish predecessor from successor. No new template or oracle feature
is added. Stage 2 continues to consume generated Pair latents only.

All previously inspected panels are development diagnostics. Before fitting,
freeze two new 256-graph panels: eight rows of length two (seed 19403) and three
rows of length four (seed 19404). Their successor relations are non-bijective
functions: some generated Pair tokens have several consumers and some have none.
Every training graph is bijective, so in-degree signatures distinguish the fresh
structures even modulo key renaming. The shape of the last shared consumer cannot
be inferred by reversing a permutation.

Output position remains anchored, not learned. All anchors still require exactly
one valid successor because the key universe is closed. There are no union events
or ownership conflicts. These limitations remain explicit and the full goal stays
open. Use the final checkpoint and report all seeds/modes; no fresh result chooses
training duration or weights.
