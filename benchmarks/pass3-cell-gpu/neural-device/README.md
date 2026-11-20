# CPU and GPU placement of the same neural policy

All comparisons use an Apple M3 Max, FP32 and seeds 1703/1709. PyTorch uses one inter-op thread. CPU thread counts describe the intra-op pool. The full-pass experiments share the same Metal graph, verifier, ordered commit and exact residual engine. CPU placement moves the network's actual forward pass; it never fills a missing match. A separate, source-closed prefix also runs its verifier on CPU. Each result reports the workload, action domain and device boundary.

The later three-way verifier-placement study treats CPU generation followed by GPU verification as a historical handoff diagnostic. Its primary matrix uses CPU→Rust, GPU→Rust and GPU→Metal.

## Generate an entire forest once

[The forest policy](../whole-pass-generation/README.md) has 12,829 trainable parameters and sees 614 typed candidates on sum-bits, 1,218 on dot-product. It scores static parent-port/consumer choices before the first Run. Both CPU and GPU use the same trained weights, initial graph features, row ordering and activation threshold. Each CPU arm assembles the full five-int32 token envelope on CPU, uploads the contiguous tensor, then uses the same device checker as the GPU arm. This transfers 12,280 or 24,360 logical bytes per Pass. The verifier needs no copy of the intermediate neural latent. The replay control keeps an already sealed packet resident and charges no online forward.

Single-graph microtimings are synchronized latency measurements. Network forward ends at logits, generation includes the activation and token formatting, and ready-for-verification includes the GPU envelope check and any host-to-device upload. These intervals are measured separately; their medians need not add. Complete resident timing starts with initialized graph and weights and ends at synchronized completion of the source schedule. It includes generation, transfer, verification, residual matching and ordered commits. The benchmark checks ordered RHS, effective writes, Spine and the final typed graph for every placement. Source comparison takes place after executing the graph. [Timings and row-level parity](placement.json)

| Whole forest, µs; seeds 1703 / 1709 | CPU-1 forward | CPU-4 forward | PyTorch MPS forward | CPU-1 ready at GPU verifier | MPS ready at verifier |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 136 / 131 | 124 / 136 | 405 / 379 | 569 / 599 | 466 / 387 |
| dot-product | 210 / 221 | 178 / 193 | 383 / 505 | 725 / 704 | 457 / 441 |

With the same GPU verifier, ten interleaved complete resident passes took 884 / 923 ms on sum-bits for CPU-1 and 855 / 892 ms for MPS. Dot-product took 913 / 958 and 909 / 947 ms. The ordering fluctuates across paired trials, including against an already-resident frozen token stream. The isolated per-forward differences are below one millisecond, substantially smaller than the variation in full-pass samples. All discrete tokens and winner ordinals agree. The largest CPU/MPS logit difference is 0.00000191.

## Generate repeatedly while the graph is live

[The pending-parent policy](../recurrent-generator/pending/README.md) reads a live 32-leaf × 8-rank bank every source Run. The CPU actor reads its own previous child token, computes the next two roots and children locally, and uploads those four tokens. The graph observations arrive from the actual GPU graph and never from an oracle. Typed verification, source visibility, residual matching, ordered commits and graph ownership stay on GPU.

* **Metal** keeps observation, both waves and the verifier on device for the fixed scheduling budget.
* **Metal with CPU readback** copies the identical observation bank to CPU and stops at the device's end-of-schedule marker. Both neural waves still run on device. This pays the synchronization while allowing the host to stop issuing padded Runs.
* **CPU** uses the same readback and termination rule, performs both waves on CPU, and uploads 192 bytes of generated token fields per executed Run. The verifier decodes the returned parent pointers and certificate IDs. Every arm records root and child ordinals as well as latent and discrete differences.

Each observation contains 8,192 logical bytes. Reading sum-bits 1,428 times plus its terminal marker therefore transfers 11,706,368 logical bytes to the host. On unified memory the byte counts describe the program's transfers; the timing includes synchronization. The control measures the net effect of readback and host termination together. [Full Pass 3 results](recurrent.json)

| Per-Run policy; full resident ms, seeds 1703 / 1709 | Resident Metal | Metal with CPU readback | CPU-1 | CPU-4 |
|---|---:|---:|---:|---:|
| sum-bits | 995 / 968 | 1,453 / 1,468 | 1,926 / 1,908 | 1,895 / 1,895 |
| dot-product | 1,037 / 1,073 | 1,550 / 1,557 | 2,101 / 2,091 | 2,080 / 2,084 |

## Can the GPU close the small-network gap?

A second paired comparison runs the original PyTorch policy on CPU/MPS and a compiled two-kernel Metal forward on the same GPU. The first kernel evaluates the root linear layer and tanh. One SIMD group per candidate evaluates the second MLP using the same weights and embeddings. Both GPU arms retain the same token generation and envelope checker. We audit the individual logits and latent differences before comparing activations and source winners. [Compiled forward](forest_forward.metal) · [Paired results](compiled.json)

In the three-way paired trial, sum-bits CPU-1 forward took 123 / 130 µs; the two-kernel Metal forward took 203 / 194 µs. Dot-product CPU-1 took 223 / 214 µs and fused Metal took 203 / 199 µs. With token construction and the device check included, fused Metal was fastest in all four pairs at 264–297 µs. The GPU/CPU crossover depends on the implementation as well as the number of candidates.

Fresh-process CPU-1 / MPS medians (ms) were 1,956 / 1,924 and 1,909 / 1,910 on sum-bits, 1,944 / 1,941 and 1,958 / 1,958 on dot-product. Each pair uses four interleaved fresh processes and includes startup, input loading and export. All pairs pass the post-run audit. [Raw CLI timings](fresh-cli.json)

## Source-closed control

The entire verifier can stay on CPU for an admitted, finite initial saturation. With the same 24-wave neural policy, the prior state and next observation then require no device round trip. The native CPU and Metal coverage validators compile the same integer predicate. This contract covers only the first 8 or 10 source Runs of these two programs. [Prefix device-placement study](../coverage-certificate/README.md)

## Reproduction

Run in the established PyTorch workspace with MPS fallback disabled. Each output directory must be new. Only the fresh-process command includes Python startup, weight loading, source initialization and device export. It reuses a precompiled program packet and the OS shader cache; the parent independently verifies each output after the clock stops.

```sh
dir=benchmarks/pass3-cell-gpu/neural-device
e="$EGGFUSE_ARTIFACT_ROOT"
corpus="$e/repair-bake-families-20261120"
ref="$e/pass3-atlas-integration-20261120"
reader="$e/rotary-axes-20261119/packed-1703/final.pt"
weights="$e/whole-pass-generation-20261120"
python "$dir/study.py" "$corpus" "$ref" "$reader" "$weights" "$e/NEW-placement"
python "$dir/study.py" "$corpus" "$ref" "$reader" "$weights" "$e/NEW-compiled" --fused
python "$dir/recurrent.py" "$corpus" "$ref" "$reader" "$e/compound-pending-pass3-v1" "$e/NEW-recurrent-placement"
python "$dir/cold.py" study "$corpus" "$ref" "$reader" "$weights" "$e/NEW-fresh-cli"
```
