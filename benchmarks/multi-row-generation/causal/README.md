# Trained causal baseline with cached generated prefixes

This standalone conditional neural decoder sees all known input queries and
the complete previous-stage memory. Only not-yet-generated outputs are hidden.
It caches known-source and external-memory K/V, then appends each actual emitted
state to its history. There is no teacher prefix or CPU answer repair. Both seeds
pass 512/512 fresh two-round graphs. This is not a general language model.

The first implementation mistakenly hid future known source queries along with
future outputs. Its exact code snapshot and reports are retained in
`results/limited-source/` but excluded from the headline comparison. The corrected
implementation was retrained with identical initialization and budget. Tests
distinguish legitimate known-input visibility from future-output leakage, and
show dependence on actual generated history. See [PROTOCOL.md](PROTOCOL.md).

## Timing method and limits

`benchmark_causal.py` measures the final corrected models on the same 32 inputs
per fresh family as the block models. Four warmups precede measurement; model
order rotates between samples. GPU-resident and host-prepared lanes are separate.
The latter includes feature building/upload, two generated rounds, address
decoding, semantic readout and GPU validity checking. Afterwards an independent
CPU audit checks every timed graph. All three models, both seeds and both panels
pass 32/32. Compilation, training and the independent post-hoc CPU audit are not
part of the reported steady-state latency.

| Layout / seed | Block continuous | Block own-symbol | Causal serial |
| --- | ---: | ---: | ---: |
| 8×2 / 1703 | 1.245 ms | 1.486 ms | 12.037 ms |
| 8×2 / 1709 | 1.191 ms | 1.488 ms | 11.585 ms |
| 3×4 / 1703 | 1.222 ms | 1.520 ms | 9.221 ms |
| 3×4 / 1709 | 1.211 ms | 1.509 ms | 8.949 ms |

Each row is one graph's two-round generation: 32 tokens at 8×2, 24 at 3×4.
Hardware/runtime and job evidence are in
[provenance.json](../depth/results/provenance.json). Raw samples, model hashes,
resident timings and effective complete-graph throughput are retained in
`results/full-source/checked-benchmark-*.json`.

The causal model uses 6,000 steps of joint pretraining plus 3,000 causal fine-tuning
steps on the original short-cycle data. Block controls use 6,000 steps from scratch
on mixed short-cycle/functional data and depths 2–4. They have the same parameter
shapes but different masks and training. Therefore these are measured systems on
the same checked task, **not an architecture-only matched training ablation**.
The causal baseline has not been tuned to an optimal implementation; speedup
against this implementation does not establish a universal AR lower bound.

The own-symbol interface costs more than raw continuous outputs for two rounds,
but passes the separate 12-round recurrence test where continuous controls fail.
No 12-round performance claim follows from this two-round timing.

Output placement is fixed by source anchors. No variable output allocation,
union or ownership arbitration is included. The results support batch generation
with correct references in this bounded task; they do not yet show learned
cooperative scheduling of egraph inference.

```sh
~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python \
  benchmarks/multi-row-generation/causal/benchmark_causal.py --seed 1703 \
  /Volumes/EggFuseWorkspace/experiments/NEW-causal-benchmark-1703.json
```

The benchmark checks hashes of the recorded checkpoints at its declared artifact
roots. Do not silently substitute different weights or train/evaluation panels.
