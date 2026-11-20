# Native profile-guided code generation on complete Pass 3 programs

This experiment uses Rust/LLVM instrumentation on two independently linked executables. The first is the default standalone Rust Cell CPU runtime with its ordinary source provider. The second uses the complete two-view learned CPU issuer, published single-parent headers and delayed arithmetic ports. Both retain the CLI allocator. The learned weights, compiled query plans, program input, ordered mutations and source verification remain fixed. The evaluation programs are conjugate-gradient and 3mm at checkpoint seed 1703.

## Matched native compilation

Each provider first receives its own instrumented build. Sum-bits, dot-product and Jacobi produce three measured-source executions each in three fresh resident processes (one process per donor). The training includes normal graph initialization, inference, export and process housekeeping. Every donor contributes one entire raw profile per backend. The merge preserves observed counts, so a longer donor can contribute more edges. No reference RHS, source event count or test profile is a planner input. Each compiler's profile-use invocation receives only that backend's own merged donor profile; the exact engine never uses the learned engine's training profile.

The ordinary release binaries are the same six-workload reference binaries used by the composed CPU benchmark. To inspect actual code generation, a Cargo compiler wrapper adds LLVM IR emission to the runtime crate during the very compile that provides the linked library. On this toolchain that changes its default codegen-unit count: the original learned release contains 16 object units, while the IR-emitting builds use one. For each engine we therefore measure **three** controls: the original release, the one-unit release without PGO, and the matching one-unit release using its own donor profile. The PGO-specific comparison is between the latter two. Generated IR must carry positive `function_entry_count` metadata for the graph, and in the learned engine for both parent issuers. The driver rejects logged profile hash mismatches and stale-profile diagnostics. Plain module IR is checked for zero positive function-entry metadata.

The independent default audit binary provides per-Run ordered RHS inputs, effective writes, Spine, union, schedule and final graph. Every learned executable also has to reproduce the earlier complete-run sealed proposal, winner, root parent and actual allocated Cell digests, with full source RHS ownership and at least 98% directly recipe-allocated fresh Cells. Every timed exact or learned run checks its graph, Run count and RHS count. Default-feature exact timing uses its uninstrumented execution; its independent audit binary is run separately.

Reported resident inference time is the native duration of the source execution itself. API round-trip includes graph/model setup, complete export, hashing, reply serialization and local JSON decoding. The build manifest records native compilation seconds, donor executions and profile sizes. The resident intervals exclude offline work and process startup. Six rotated measured repetitions after warm-up put every executable in each position once. No timing from the instrumented donor binaries enters the performance comparison.

## Measured inference

| Workload | Provider | Original release ms | One-unit release ms | One-unit + PGO ms | PGO over one unit | Faster pairs | Original → PGO API round-trip ms |
|---|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | vanilla | 353.98 | 343.06 | 311.61 | 9.17% lower | 6/6 | 461.76 → 411.18 |
| conjugate-gradient | learned | 666.02 | 645.72 | 569.76 | 11.76% lower | 6/6 | 772.48 → 665.14 |
| 3mm | vanilla | 925.54 | 882.01 | 806.13 | 8.60% lower | 6/6 | 1,163.89 → 1,021.18 |
| 3mm | learned | 1,980.70 | 1,956.59 | 1,730.21 | 11.57% lower | 6/6 | 2,211.76 → 1,941.12 |

PGO improved every matched inference pair. With both compilers using their own profile the learned path took 1.83× the exact time on conjugate-gradient and 2.15× on 3mm. Compiling the exact engine also helps, so treating its ordinary release time as the only baseline would overstate the algorithmic benefit of neural generation. The measured 131,371 / 294,917 source RHS, all signed proposals, source Run events and physical winners remain identical across the three learned binaries. These full CPU runs use one Apple arm64 host and frozen weights. [Timings and endpoint digests](results.json)

Rust 1.94.0 (LLVM 21.1.8) generated the instrumentation; Apple LLVM 21.0.0 merged it. The donor profiles cover 5,212 / 6,210 instrumented functions in the exact / learned binaries. In the linked profile-use runtime IR, 752 / 848 functions carry positive donor-derived entry counts versus zero in the two matching plain libraries. Both Executor paths record exactly nine donor entries. In the learned runtime the most frequently entered profiled single-parent / multi-parent routines record 27,432 / 383,232 entries. These counts establish that observed hot code received the profile; unobserved code need not have a positive count. [Compiler identities and recorded metadata](build-evidence.json)

After freezing the binaries, a separate instrumented run on each held-out program compared its normalized edge-count distribution to the donor profile. LLVM reported 76.72% / 79.34% edge overlap on conjugate-gradient (learned / exact) and 68.63% / 70.34% on 3mm. Both donor hashes remained unchanged. Edge overlap describes compiled control flow over the complete process, including common setup and export; it is a different quantity from neural source coverage. [Post-training overlap](overlap.json)

## Reproduction

From the repository root, in an environment with aarch64 Apple Rust, offline Cargo dependencies and Xcode's llvm-profdata:

```sh
d=benchmarks/pass3-cell-gpu/native-backend-pgo
# Prepare the composed-cpu-profile-v1 source tree using the composed-cpu/build.py recipe.
python "$d/build.py" "$EXP" "$EXP/native-backend-pgo"
python "$d/study.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/native-backend-timings"
python "$d/overlap.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/native-backend-timings" "$EXP/native-backend-overlap"
python "$d/archive.py" "$EXP" "$EXP/native-backend-pgo" "$EXP/native-backend-timings" "$EXP/native-backend-overlap"
python "$d/verify.py"
```
