# Whole local completion states: bounded GPU representation experiment

This is a standalone diagnostic on actual selected-family GPU captures, not an
installed full Eggcc runtime optimization. No gradients, refitting, threshold
search, or new graph execution are used. The frozen five-program model and
readout remain unchanged. All four captures retain validation provenance.

## Representation

Bake enumerates every same-sort partition of a semantic Cell's Eq slots after
quotienting completed static copy/union effects. Enumeration does not inspect
training or validation labels. These are type-compatible states, **not proofs of
reachable completion**. A budget of 4096 states fails explicitly before excessive
allocation; arbitrary large Cells need another representation or fallback.

The three selected templates have 2, 15, and 15 states, with 1, 6, and 6 dynamic
quotient-pair columns. Static state matrices consume 8, 360, and 360 bytes.
A batch of frozen ridge/readout scores selects the nearest binary state using:

```
utility = (2 * scores - 1) @ states.T
utility = mask_out_states_that_split_proven_input_equalities(utility)
chosen = argmax(utility)
```

This equals squared-distance minimization after removing the candidate-independent
term. Exact ties prefer fewer additional equalities. Selection uses fixed batched
operations; no per-instance traversal or iterative union-find on the GPU. This
small output consistency operation is not presented as the main floating inference
engine or a replacement for its learned dense calculations.

Two variants isolate static-state consistency from preservation of actual current
input equalities. Current equalities come from captured valid query-slot roots,
with original typed slot identity. They are never derived from final labels.
All current input constraints are independently checked against final labels.

## Full floating token reconstruction

For each state, Bake precomputes the equality contribution to the class-balanced
128-dimensional token: first and second message moments, plus class count.
Runtime adds `tanh(scalar_role + actual_scalar_code)` moments and normalizes.
It does not use a codebook of observed scalar values. The current family has only
query scalars; a new scalar effect would require its actual result and is rejected
by this diagnostic. Stable IDs and ownership metadata stay in their exact slots.

Moment tables cost 1032, 7996, and 7740 bytes, including scalar roles. Every one
of 280 saved instances (41 GCD + 99 LCM, exact-source and feedback captures) has
its oracle state represented. Reconstructing its true-state token with actual
input scalars agrees with the independently generated CPU target within 1.20e-7.
GPU reconstruction of selected predicted-state tokens agrees with CPU within
1.20e-7, and GPU/CPU state selection agrees exactly. Oracle states participate
only in representation validation, never prediction.

This makes the selected state encodable in the existing full floating token
format. It does **not** establish correct prediction or subsequent feedback
stability. Reconstructed tokens have not yet replaced birth predictions in a
resident rollout, and cannot authorize new equalities.

## Results

Exact-source and saved predicted-source feedback captures give the same table:

| Workload / variant | Exact Cell partitions | Expanded false merges after closure | Missed expanded equalities |
| --- | ---: | ---: | ---: |
| GCD original | 35/41 | 0 | 16 |
| GCD whole state | 35/41 | 0 | 16 |
| GCD whole state + current Eq | 35/41 | 0 | 10 |
| LCM original | 82/99 | 13 | 35 |
| LCM whole state | 83/99 | 7 | 35 |
| LCM whole state + current Eq | 83/99 | 7 | 21 |

The one LCM nontransitive result becomes consistent. Input preservation avoids
forgetting established equalities in generated-source consumers. Expanded counts
include alias multiplicity; they are not committed unions or unique repairs.
The JSON also reports quotient precision/recall and direct/generated splits.

**Direct-source accuracy is unchanged:** GCD 23/26 and LCM 71/78 in every variant.
Therefore output consistency and input preservation address a real but limited
failure mode. They do not explain or solve the direct-source information deficit.
Seven LCM false merges remain, so this is not adopted as semantic authority and
no broad GPU performance run is justified.

## Latest iterative Bake connection

Inspected `codex/cell-parallel-admission` at `2b12f110`, including
`native-binding-census.md`. Its native-address layout is conditional on an actual
bound result and must survive owner relocation or fall back. This experiment
likewise consumes actual captured query slots; state identity is not a substitute
for an executed operation, actual returned constructor, ownership transfer, or
visibility. No parallel fact graph or consumer list is introduced. The latest
CPU branch reports a storage opportunity, not an executed GPU takeover.

## Reproduce

With the project's MLX Python, run `audit_completion_states.py DECODER
DECODER_REPORT OUTPUT --capture CAPTURE ...`. Artifacts are under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee`:

- `five-program-boundary-decoder.npz` and `.json`;
- `gcd-live-boundary-labeled.npz`, `lcm-live-boundary-labeled.npz`;
- `gcd-feedback-labeled.npz`, `lcm-feedback-labeled.npz`.

Output: `completion-state-projection.json`. Binary datasets remain external;
reproducible sources and text results are versioned. Unit tests cover Bell counts,
static quotient, type separation, budget rejection, required equalities,
transitivity, tie policy, actual dynamic scalar effects, and compiled GPU parity.
