# Who verifies the same Cell certificate?

A single neural forest is generated in full before the first source Run. Every candidate references a concrete producer root and effect port. The comparison admits universally proved one-table queries with distinct variable columns. The compiler supplies their output projection. Other activated candidates remain in the original tensor and are declined by every verifier; residual source execution supplies the uncovered work. The candidate specification, root and child slots, active bits and typed certificate bytes agree across CPU and GPU generation. The much larger combined single/multiple-witness CPU vocabulary has no common independent GPU verifier here.

| Source workload | Neural children, seeds 1703/1709 | All source RHS | CPU network + Rust | GPU network + Rust | GPU network + delta verifier + CPU commit | GPU network + all Metal |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 89 / 90 | 7265 | 25.84 / 25.22 | 27.71 / 27.13 | 80.22 / 78.89 | 877.71 / 873.79 |
| dot-product | 185 / 185 | 6704 | 22.40 / 22.52 | 23.26 / 23.76 | 87.07 / 88.04 | 905.75 / 932.03 |
| gemm-bias-relu | 207 / 207 | 15462 | 48.67 / 48.83 | 51.25 / 50.81 | 136.61 / 134.21 | 2821.64 / 2769.81 |
| stable-argmax | 128 / 128 | 8190 | 27.24 / 28.76 | 28.14 / 29.51 | 74.52 / 80.00 | 918.66 / 948.14 |

Times are median milliseconds for the full Pass 3 schedule with ten rotated/reversed repetitions per arm. The CPU policy path runs the actual single-threaded trained forward in Rust. The GPU policy paths run the same weights on MPS. Every assisted arm checks original ordered RHS, effective writes, Spine resumes, source identity, the full canonical typed graph and distinct actual neural RHS ordinals. The frozen comparison includes two static initialization roots per program. Completely disabling residual execution diverges from the complete source schedule. Rust with GPU projection and the all-Metal executor still agree on the partial trajectory, every credited ordinal and the resulting graph. [Measurements and cross-engine audits](results.json)

## Incrementally mirroring the proof boundary

The CPU Cell graph remains authoritative. The reserved Metal buffers hold a typed static claim catalog, a versioned port-state bank, scheduled rules' watermarks, final commit acknowledgements and reusable projected-result slots. For each subscribed root output, Rust sends the unique physical identity, mirror generation, current cursor producer and effect port, table, native row epoch, hidden flag and values. Values are interned into a stable native dictionary; equal integers/classes/strings are transported losslessly by dictionary index. Raw graph pointers and floating approximations do not cross this interface.

The GPU rejects inactive or already published claims, unscheduled consumers, absent or invalid generations, wrong producer/effect/table and obsolete or hidden source rows. For an admissible universal claim, Metal projects the values of the requested RHS fields from the mirrored row and returns their exact dictionary indices. The native ordered cursor delivery supplies the original scheduling order and source visibility. Rust checks that the returned source handle and mirror generation still match, rebuilds its slot frame from the **GPU output values** and commits the RHS in source order. It never recomputes the universal projection on that successful path. Other rule matching, union/rebuild, index upkeep and all residual completion still belong to the authoritative CPU graph. The standalone all-Metal arm uses the same compiler projection in the device's own graph.

A counterfactual corrupts the *publisher's effect* in every mirrored state while the native graph remains intact. GPU-delivered children drop to zero in every case; Rust's explicit residual execution still restores the complete source outputs. This separates having a compiled verifier from actually consuming its decisions. [Native graph hook](build.py) · [Persistent mirror and handshake](sidecar.rs) · [GPU checks and returned values](sidecar.metal)

## What transfer volume buys

The delta and snapshot variants inspect the same subscribed source rows and use the same GPU check. The snapshot arm writes the entire current port bank on every source Run. The delta arm writes only changed source records. In sum-bits seed 1703, 56 subscribed port slots across 1,428 Runs required 79,968 CPU inspections. Only 297 records changed: 34,452 bytes of state writes versus 9,276,288 in snapshot mode. Both scheduled 171 GPU submissions. Full-pass median was 80.22 vs 77.28 ms. In dot-product seed 1709, 61,944 bytes replaced 20,833,020 bytes and both variants still made 181 GPU submissions. Counters separately report schedule writes, commit acknowledgements, projected-value result reads, host publication, dispatch/wait and GPU execution. These are logical shared-buffer reads/writes on Apple unified memory rather than measured PCIe traffic. Each GPU-to-native model route also pays for materializing the generated certificate in host words and transmitting it to the native service.

Before each timed trial the native service creates a fresh graph from its already loaded source and signals readiness. The timer includes model forward, any device readback/IPC, packet validation, per-trial graph mirror buffers, authoritative inference, sidecar sync and native reply. The Metal shader pipeline is reused within the process. The all-Metal arm starts from the same previously initialized device graph and includes network emission, the complete original schedule, residual search, ordered commit and synchronization. Graph serialization, hash comparisons and disk export are outside the resident timers. These different runtime setup costs are explicit in each sample.

## Follow-up from the observed synchronization cost

The second paired ablation retains subscriptions from each scheduled rule to the active generated claims and their parent ports. At each original Run it first discards claims already committed. If no remaining subscription has a published parent, there is no device call. Otherwise Rust refreshes only the still-needed ports. Readiness considers subscription, schedule, publication availability and commit acknowledgements; it does not approve the row, compare source versions, infer fields or bypass the GPU projection. The GPU still checks the exact current state and returns the projected values. This moves the polling cost as well as the submission count.

| Source, seed 1703 | GPU submissions, all subscribed ports → currently needed | CPU port inspections | Full paired median ms |
| --- | ---: | ---: | ---: |
| sum-bits | 171 → 2 | 79,968 → 60 | 96.39 → 35.63 |
| dot-product | 181 → 2 | 179,595 → 121 | 101.48 → 33.61 |
| gemm-bias-relu | 242 → 2 | 219,716 → 141 | 171.98 → 63.60 |
| stable-argmax | 150 → 2 | 91,920 → 85 | 81.70 → 35.28 |

All eight stream comparisons reached the same source graph with exactly the same credited child ordinals in two GPU submissions. These children originate in the small static initialization forest. Their activations are unusually concentrated in the source schedule. Two submissions cannot be assumed for the larger general single/multiple-witness stream. Compare new timings within this eight-repetition matrix; its baseline is independently timed. [Per-stream follow-up](ready-results.json)

## Reproduction

Each command needs a new output directory. The repository-local overlay only instruments a temporary copy of the native runtime; all ordinary source scheduling, graph mutation and repair are shared with the baseline. No CPU-generated-network/GPU-verifier timing is included.

```sh
dir=benchmarks/pass3-cell-gpu/verifier-deltas
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-delta-build"
python "$dir/study.py" "$e/repair-bake-families-20261120" "$e/pass3-atlas-integration-20261120" \
  "$e/rotary-axes-20261119/packed-1703/final.pt" "$e/whole-pass-generation-20261120" \
  "$e/NEW-delta-build" "$e/native-forest-20261120/paired" "$e/NEW-delta-study"
python "$dir/ready.py" "$e/repair-bake-families-20261120" "$e/pass3-atlas-integration-20261120" \
  "$e/whole-pass-generation-20261120" "$e/NEW-delta-build" "$e/native-forest-20261120/paired" \
  "$e/NEW-delta-study" "$e/NEW-delta-ready"
```
