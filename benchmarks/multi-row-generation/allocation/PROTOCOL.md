# Unanchored multi-row set generation

Standalone neural experiment, not the egglog runtime. The goal is complementary
output generation, not compression. Freeze this protocol before fitting.

Four A(key,value) and four B(key,value) inputs are shuffled over a single graph's
2x4 or 4x2 input layout. Each legal equality join A.key=B.key is one obligation.
Unlike the anchored experiment, an A may have zero, one or multiple matches.
Eight output slots (rows containing multiple tokens) each predict active/null,
both source pointers and key/left-value/right-value. No slot is assigned a source
anchor, key, matching pair or subset. All slots see all original inputs.

Loss matches the predicted set to offline truth by a minimum-cost bijection with
padded null targets (Hungarian assignment). This CPU training operation is not an
inference step. No target slot order is supervised. Inference consists only of
GPU neural blocks, argmax and address decoding, with no top-k suppression,
matching repair, sorting, deduplication or CPU completion. Independent CPU audit
follows generation. GPU verification, when timed, must not alter outputs.

- Same 64-dimensional decoder with three blocks, shared source-pointer and field
  heads, separate row/position rotary coordinates. Initial queries depend on
  output row/position only; they contain no matched facts.
- Joint query communication versus within-row-only communication, both with full
  original-input visibility. Two seeds 1703/1709, all final models retained.
- Train 4096 graphs, balanced across feasible obligation counts 0,1,2,3,4,5,6,8;
  each key occurs at most twice on either source side. Key vocabulary 8, values 4.
- Adam 4000 steps, learning rate 0.001, batch 32; alternate the two layouts.
- Fixed final checkpoint, no test-driven checkpoint/seed selection.
- Fresh IID: 256 graphs, seed 51917, drawn from training multiplicity shapes but
  reject any exact labeled input already in training.
- Held-out multiplicity: 256 graphs, seed 51918, at least one key occurs three
  times on A and at most twice on B, with 1..8 obligations. Its multiset of
  (A multiplicity,B multiplicity) pairs must not occur in training. Training and
  held-out inputs still use the same finite key alphabet and four sources/side.
- Evaluate both layouts; one row is not one independent batch sample.

Report full legal complete graph rate; legal unique output count; duplicate,
missing, illegal binding, field and address error counts; predicted count error;
per-cardinality results. No correctness credit for duplicates. Ablate inter-row
messages without retraining as a diagnostic, separate from the trained mask
control. Passing this task does not prove latent recurrence, union, ownership,
new layouts/sizes, arbitrary keys, learned stopping or full egraph saturation.
