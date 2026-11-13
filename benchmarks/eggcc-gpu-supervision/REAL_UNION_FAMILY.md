# Real union-enabled GPU Cell completion

This standalone experiment imports two audited pre-Run boundaries from the
training program `024-pascals-row`. It executes the original selected rule
body on GPU, including query, floating ridge token inference, copy/union,
congruence closure, token refresh, semantic deduplication and matched owner
takeover. The device controls saturation; the host launches a fixed tick budget
without intermediate readback. CPU verification runs afterward.

This is not full Eggcc execution. Only the selected constructor tables and one
copy/union rule are covered in each experiment; external constructor collisions
and other rules remain outside this local contract. Exact kernels authorize
union, not ridge scores. There are no new constructors in these particular
rules. Original full stage scheduling and arbitrary mutable/primitive effects
remain unfinished.

## Evidence

| Input | Rule | Seed rows | New Cells | New equivalences by Run | Owner rows freed |
|---|---:|---:|---:|---|---:|
| Before Run 22 | 538, type-helpers | 3 | 1 | 1, 0 | 1 |
| Before Run 467 | 283, context | 15 | 11 | 2, 0 | 9 |

Rule 283 matches `AddContext(ctx, x) -> y` and
`AddContext(ctx, z) -> x`, then unions `y` with `x`. Its independent CPU match
counts are 9 then 11: union enables additional matching before saturation.
GPU partition equality, normalized facts, per-Run equivalence counts and
completed floating target reconstruction all pass. Both Runs allocate zero
constructor IDs. No new facts is therefore insufficient to detect a fixed point.

The independent CPU oracle uses its own union-find and ordinary constructor
congruence over imported rows. It does not call GPU query plans, completion,
Eq kernels or ridge. Stable seed IDs are checked exactly, including scalar
exclusion from union. The oracle is deliberately limited to copy/union effects
and rejects others; it does not silently skip unsupported work.

The context capture contains 11 accepted instances, with **zero** inputs sourced
from generated Cell templates. They consume original seed sources, including
roots refreshed after union and sources whose physical ownership has moved.
Thus this is direct-source evidence, not a successful generated-token rollout.
Capture checks validate joint witnesses, generations and reconstruction of both
ridge inputs and completed targets. Final targets represent the selected-family
saturated partition, not arbitrary intermediate effect states.

Frozen Eq readout, with no fitting:

- CPU target tokens: 11/11 exact partitions.
- Predicted GPU tokens: 9/11 exact partitions; 8 false pair merges after closure.
- 11 dynamic quotient comparisons, 9 positive; 2 distinct final rule partitions.

This isolates a real direct-consumption accuracy gap. The new input-relation
feature replay observes 60 same-source pairs, 9 same-port pairs and 27 current
typed-equality pairs, versus no equality pairs in the earlier Concat family.
It still observes no equal-input pairs across distinct sources. Features agree
between CPU and GPU, but have not yet been fitted/validated on a program-separated
corpus. No improved prediction rate is claimed, and the resident model is intact.

Timings in the JSON include compile/upload/execution for the whole local GPU
experiment and separately CPU verification. Cached graph runs and tiny local
batches cannot establish neural-network-like throughput or a runtime speedup.

## Bake alignment

The latest inspected reference is `codex/cell-parallel-admission` at `85351d46`.
It shares completed-owner epoch/depth metadata while preserving exact per-source
exceptions and independent fact lifecycle. Here physical owner release likewise
must not erase source IDs or generations. The experiment exercises existing
matched takeover and audits original logical-source witnesses after transfer;
it does not treat common physical ownership as an equality proof or add consumer
subscriptions. Native executor code was not changed or merged.

## Reproduction

Artifacts live under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`. Regenerate
`pascals-union-boundaries.json` with the existing `capture_rhs_results` example,
using the saved Pascals `program.json` and `--snapshot-runs=21,466`. The native
observer compares every source Run with an independent unobserved execution.

```
python benchmarks/eggcc-gpu-supervision/audit_union_family.py TRACE MODEL OUTPUT \
  --rule 283 --snapshot-run 466 --capture CAPTURE.npz --corpus-manifest MANIFEST
python benchmarks/eggcc-gpu-supervision/audit_device_match_readout.py CAPTURE.npz DECODER DECODER_REPORT OUTPUT
python benchmarks/eggcc-gpu-supervision/audit_input_relations.py CAPTURE.npz OUTPUT
```

Use rule 538 and snapshot 21 for the second case. The capture schema retains the
existing v2 arrays plus explicit `target_scope: selected-family saturation`.
Binary traces/models remain external; reproducible sources and text results are
tracked. Tests cover typed registry import, union-driven fixed points,
union-enabled joins, GPU ordered union, matched takeover, and witness capture.
