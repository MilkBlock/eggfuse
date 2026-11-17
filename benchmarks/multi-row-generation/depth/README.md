# Generated-state depth stress

Standalone MLX/Metal experiment; not the egglog engine. See [PROTOCOL.md](PROTOCOL.md)
for the explicitly extended homogeneous path-composition contract. Requested depth
is explicit, and no saturation or arbitrary-rule generalization is claimed.

The four frozen two-round models fail continued execution. On the replay/seen
panel, cumulative exact graphs at rounds 2, 4 and 6 are:

| Model | R2 | R4 | R6 |
| --- | ---: | ---: | ---: |
| joint / 1703 | 256 | 24 | 0 |
| joint / 1709 | 256 | 24 | 0 |
| independent / 1703 | 256 | 41 | 0 |
| independent / 1709 | 256 | 87 | 0 |

All denominators are 256. `results/frozen/` preserves full panels, including
failures on larger inputs. Two-round correctness is insufficient evidence for a
stable recurrent representation.

We then fine-tuned all four checkpoints for 3,000 steps through their own generated
states, with training depths 2/3/4. All pass four rounds on training replay, but
all have **0/256** cumulatively correct graphs by round 11 on training replay and
both fresh tail panels. Full outcomes are in `results/trained/`; no failed seed
is excluded. This result motivates the separately controlled
[own-symbol interface experiment](../typed/README.md).

`probe.py` preserves the exact executed historical probe/audit. `contracts.py`
is a later NumPy-only stricter audit: it rejects nonfinite arrays and additionally
checks canonical symbol format for typed outputs. `audit_saved.py` binds the
readout to saved model weights or the declared exact typed decoder and never
executes or repairs the network. It does not import MLX.

Eight targeted tests across the probe, tail data, typed interface, audit, and
causal baseline passed; logs are in `results/checks/`. `results/provenance.json`
records source-hash verification, job outcomes and supplemental dependencies.

Example (use the shared compute queue):

```sh
~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python \
  benchmarks/multi-row-generation/depth/probe.py \
  /Volumes/EggFuseWorkspace/experiments/multi-row-generation-direction-20261118/joint-1703 \
  /Volumes/EggFuseWorkspace/experiments/NEW-depth-probe.json --rounds 8
```
