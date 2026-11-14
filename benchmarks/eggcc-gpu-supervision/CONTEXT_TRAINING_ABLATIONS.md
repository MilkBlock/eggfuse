# Two rejected explanations for remaining completion errors

Both trials reuse all 641 synthetic inputs, fixed joint random features and
alpha 10. Real programs remain development validation only. No gradients,
accuracy-based input selection, additional feedback rollout, or promotion.

| Offline complete-state accuracy | Existing head | Mean shared context | Ambiguous-only training |
|---|---:|---:|---:|
| GCD | 26/41 | 10/41 | 26/41 |
| LCM | 65/99 | 20/99 | 65/99 |

`--mean-context --shared-context` replaces sqrt-count normalization in the new
shared-context encoder with means. It preserves its output under uniform
replication of the entire boundary in the tested fixture, including GPU/scatter
parity. This does not prove invariance under duplicating only one neighbor, and
does not modify older base-context columns. The runtime reads the choice from
head metadata; capture verification reconstructs the appropriate variant. The
feature extension loader verifies captured columns under their original schema
before building a different experimental schema. The default sqrt reference
arithmetic remains unchanged. Mean normalization regresses badly and is rejected.

`--ambiguous-only` excludes a training row only when its exact input Eq constraints
leave precisely one compiled legal completion state. It does not inspect the
model's correctness. Runtime constraints still choose legal states as before.
712 rows in the first head are determined this way; the other two heads exclude
none. The final stable-arithmetic run gives unchanged validation counts. The flag
rejects a head with zero ambiguous training rows rather than inventing training
labels. This is not an inference speedup or an established accuracy improvement.

Tests cover constraint-based selection, impossible constraints, uniform
replication, GPU parity, and extension reconstruction/schema mismatch. Binary
weights, full reports and exact fitter argv are under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/matched-entry-gpu-v1`, named
`mean-*` and `ambiguous-stable-*`. The earlier `ambiguous-*` artifact used an
incidental reference precision change; it is preserved but not the reported
comparison. The tracked result JSON identifies the reports actually used.

The current feedback result remains GCD 25/41 and LCM 65/99 from matched-entry
training. These ablations do not resolve the outstanding full GPU Cell-runtime
or correctness goals.
