# Genuine causal cached baseline for the two-round task

This baseline does not serialize a precomputed joint query function. Each emitted
token sees the actual earlier generated output states in the same stage through
a K/V cache. All known source queries and the complete prior-stage memory remain available,
as for the parallel model. Only future generated outputs are unavailable. K/V for that
memory is computed once per stage; each generated history token is projected once.
Unit tests check prefix independence from future generated outputs and dependence
on actual past generated states; all known input queries remain visible.

Keep parameter dimensions unchanged. Initialize from the two joint two-round
checkpoints (seeds 1703/1709), then train 3,000 additional Adam steps, lr 0.0003,
batch 64, on exactly the original 4,096 short-cycle graphs. Train only serial
emission, two stages, no teacher outputs in the cache. Use final checkpoints.
This gives the AR baseline MORE optimization than the original parallel models;
training cost and initialization must be reported rather than called matched.

Final acceptance uses the frozen structural families in typed/PROTOCOL.md: two
long tails, seed 41817, layout 8x2; a tail into a 2-cycle, seed 41818, layout 3x4.
Neither final result selects weights or duration. Old two-round panels remain
diagnostics. A baseline with poor semantic accuracy cannot establish a useful
speed comparison. This is an autoregressive conditional Cell decoder with anchored
outputs, not a general language model or free-output allocation benchmark.


Source-visibility revision: the first baseline accidentally restricted known
future-anchor inputs as well as generated outputs. It is retained under
results/limited-source and is not the fair baseline. The corrected version
prefills query K/V from ALL known source states, then appends actual generated
output K/V. It retains the same parameter shapes, initialization, optimizer,
training data and 3,000-step budget. Unit tests distinguish legitimate access to
known inputs from forbidden access to future generated outputs. Use corrected
results in the final timing comparison.
