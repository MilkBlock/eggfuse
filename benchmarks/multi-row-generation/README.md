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

## Direction-identifiable follow-up

`DIRECTION_PROTOCOL.md` freezes a second experiment. Only the training family is
changed: 3-cycles distinguish successor from predecessor. No architecture, loss,
training duration or model parameter is changed using the final test results.
The original long-cycle panels are now diagnostics. Two new panels contain
non-bijective successor functions, so generated tokens may share a valid downstream
parent. These structures are absent from all bijective training graphs.

Exact complete-graph results, including both generated stages:

| Mode / seed | New 8 x 2 fan-in graphs | New 3 x 4 fan-in graphs |
| --- | ---: | ---: |
| Joint / 1703 | 256/256 | 256/256 |
| Joint / 1709 | **251/256** | 256/256 |
| Within-row query mixing / 1703 | 256/256 | 256/256 |
| Within-row query mixing / 1709 | 256/256 | 256/256 |

All modes retain global access to the previous generated memory. The within-row
variant does not isolate rows from their cross-row input dependencies. This
experiment does not establish that current-query all-row mixing is necessary;
its extra interaction fails on five fresh graphs for one fixed seed. Those
failures are retained. No model is selected after seeing final acceptance.

The fresh panels contain 3,571 and 2,062 genuinely cross-row second-stage bindings.
Three models get every one correct; joint seed 1709 has 3,564/3,571 on the first
panel. Erasing the first generated latent gives 0/256 whole-graph passes on the
long-cycle control for every model. A direct second-stage call on the generated
first latent reproduces the ordinary second output exactly. Original encodings
and reference states are never reintroduced between these calls.

## Checked generation latency

`checked_forward.py` decodes the ACTUAL generated latent on GPU, checks agreement
with advertised values, and verifies the proposed partner bindings against the
source relations. It returns verdicts only and never fills a correct binding or
patches a latent. The input-family check uses key counts/membership, not a map of
correct matching rows. An independent CPU audit agrees per graph after timing.

For 8 rows with two anchor tokens per row, two neural stages generate 32 new
tokens. The timed lane includes initial feature construction/upload, both neural
stages, address decoding and GPU verification. It uses the first 32 frozen fresh
fan-in graphs, alternating run order. Median per-graph times:

| Mode / seed | Parallel checked generation | Cached serial-query emission / parallel | Complete timed graphs |
| --- | ---: | ---: | ---: |
| Joint / 1703 | 1.380 ms | 3.60x | 32/32 |
| Joint / 1709 | 1.549 ms | 3.34x | **28/32** |
| Within-row query mixing / 1703 | 1.465 ms | 3.83x | 32/32 |
| Within-row query mixing / 1709 | 1.451 ms | 4.03x | 32/32 |

Parallel and serialized query emission have the same decoded results on every
timed graph. The serial path caches the source encoder, query preparation and
pointer K/V; it does not redundantly re-encode the input for every token. However,
it is still serialization of the same query function, **not a trained cached
autoregressive model**. The reported ratio must not be described as beating a
strong AR baseline or native egglog. Invalid graphs remain in time denominators
and are not counted as complete results. Full timing samples and effective rates
are retained in `results/direction/*-timing.json`.

## What this establishes and what remains

There is positive bounded evidence that a real NN can produce multiple related
tokens per row in the same graph, reference generated tokens in other rows, and
continue from its own latent without CPU answer correction. Batching that
particular neural query function reduces its measured emission cost.

It does NOT prove free allocation of obligations across output rows, variable
matching multiplicity, learned exclusivity/ownership coordination, union handling,
saturation, real eggcc execution, general template discovery, arbitrary key
identities or canonical floating representations. Source-anchored output placement
already provides a division of work. The task has two known templates and a fixed
key/payload vocabulary. Those limits must not be hidden under the word
“complementary”. The full architecture goal remains active.

All results are collected in `results/direction/summary.json`. The exact executed
training driver bytes are preserved in `executed-driver.json`; the tracked driver
subsequently had one trailing space removed, with identical Python AST. Model and
data-generator source hashes match the recorded executions. Binary checkpoints
remain on the external workspace under
`/Volumes/EggFuseWorkspace/experiments/multi-row-generation-direction-20261118`.

## Reproduction

Use the external workspace launcher and compute queue. Repeat for both modes and
both seeds, with distinct output directories:

```sh
~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python benchmarks/multi-row-generation/run.py \
  /Volumes/EggFuseWorkspace/experiments/FRESH-RUN \
  --mode joint --seed 1703 --train-family short_cycles

~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python benchmarks/multi-row-generation/benchmark.py \
  /Volumes/EggFuseWorkspace/experiments/FRESH-RUN \
  /Volumes/EggFuseWorkspace/experiments/FRESH-RUN/checked-timing.json

~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python -m unittest discover \
  -s benchmarks/multi-row-generation -p 'test_*.py'
```

A semantic difference exits 1 after writing all reports. Eight unit/contract tests
pass; they are separate from neural acceptance, which has the failures above.
