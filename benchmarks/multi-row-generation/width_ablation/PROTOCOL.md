# Figure 04 — zero-update expansion of a single-row policy

Freeze primary acceptance before fitting. Use the two actual rule boundaries,
local certificate corpus, two-instance demands, split, and semantic audit of
Figure 20. The pairwise certified encoder is fixed as the representation. The
primary policy trains FROM SCRATCH with a single row of eight positions only.
Replace independent trainable coordinate tables for source and output by
shared linear projections of a fixed packed coordinate feature vector. All
row identities thus have a defined encoding when the row count changes. Keep
both Run boundaries, the same eight unassigned slots per Run, exact static
field projection, and continuous consumption of real GPU-generated tokens.
At width R and row length L=8/R, packed slot rL+t retains the same position
features; in round t each row consumes its own previously generated token.
No new trainable row parameters, CPU answer repair, deduplication, learned
task assignment at expansion time or inter-row reservation.

Fit final checkpoints only, seeds 1703/1709, width=32, 1536 Adam updates at
0.001, batch 32, same unordered pointer/activation, auxiliary field and semantic
supervision, same 7168 training graphs as Figure 20. All widths evaluated for
a seed use the SAME frozen state_dict and static encodings. Primary environment:
Apple Metal, PyTorch eager, MPS CPU fallback disabled.

Primary held-out panels: for each Fig.20 held-out template (134,135,143) take
32 new eight-graph counterfactual groups numbered 720 through 751 from the fixed
test generator. Keep all four states, both origin variants, and report the blind
subset. Verify the exact input tuples are disjoint from the old 128-graph
per-template tests and old training inputs (allow legitimate duplicates between
templates in the deliberately shared blind panels). Include the old panel as a
separate comparison to legacy checkpoints. Results do not select duration,
coordinate features, position schedule or checkpoint.

Compare (make rows, finish rows)=(1,1),(2,2),(4,4) for zero-shot expansion,
plus (1,2),(2,1),(1,4),(4,1) for attribution. At equal widths also serialize
the SAME per-lane dependencies as a numerical/speed control, and erase history
as a distinct diagnostic. Baseline performance is itself subject to acceptance.
Report nonempty complete graphs, true-source duplicate/omission counts, same-round
versus later duplicates, illegal and wrong origins, consumer success when
both layouts supplied all required parents, and paired wins/losses stratified
by the eight related graphs. Repeat on the unchanged Figure 20 historical
pairwise weights with eight learned coordinate slots, labelled separately.
Time batch-one host integer upload, per-owner state selection, both Runs and
materialized token synchronization with cached template banks, interleaving
arms and checking each timed output after generation. Also report correct
nonempty graphs/s; a latency reduction without comparable coverage cannot
establish a useful inference speedup. Figure 05 training is outside this test.
