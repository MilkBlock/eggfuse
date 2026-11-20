# Shared projection programs and held-out CPU scaling

Each recurrent root proposal fixes a specific source rule, template and versioned physical witnesses before validation. The original encoding repeats the compiler's typed slot projections inside every token. This comparison freezes the certified policy, trained weights, proposal budget, nested merge gate and source executor. Each accepted bound recipe actually supplies its template and operand buffer to the allocator. Only fresh physical ids count. Rust keeps the source scheduler, exact projections, verification, commit and rebuild; both ordinary matching residuals are disabled.

* **Full** preserves the previous little-endian wire packet, including every projection.
* **Shared wire** sends the dynamic words and named template, and refers to the program-local immutable layout. The decoder checks the identity of the installed layout as well as the source atom, physical reference and version.
* **Resident** stores a typed recipe with an immutable layout reference, template and concrete source references. It emits no serialized bytes at this boundary, but it still allocates instance descriptors and keeps the projected input buffer.
* **Checked slots** additionally consumes facts already checked on the same read-only source graph. It checks their table, identity, visible epoch and typed slot, constructs the recipe's projected inputs and transfers that owned buffer to the winning source commit. A second consumption fails. The comparison with this variant is separately paired.

## Full source results

M3 Max. The vanilla driver links the normal default-feature Rust CPU runtime without the neural providers, with the same dependency versions, release optimization and mimalloc allocator used by the standalone CLI. Audit builds run separately. The timer encloses a complete inference from a fresh initialized graph to the end of the source schedule. A transaction validates ordered RHS, writes, Spine, union sequence, schedule and graph against the vanilla audit. Per-variant post-run checks include the winning root/child ordinals, raw choices, versioned references and fresh physical IDs. Each timed result is the median of eight interleaved runs after warmup; graph initialization, static plan loading and export are excluded from both clocks.

Jacobi-1d and conjugate-gradient were chosen from the frozen eggcc suite before scoring. Historical suite times indicated larger computations. Each input was compiled from its existing source parts; both use the same frozen training-family weights as the anchors. These are two larger programs for this research track. Subsequent optimization that uses their results should disclose their role as development benchmarks and reserve other programs for a fresh test.

| Program / seed | Vanilla ms | Full wire ms | Shared wire ms | Resident ms | Neural / source RHS | Direct / fresh physical Cells |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits/1703 | 20.64 | 78.03 | 76.47 | 77.27 | 7,265 / 7,265 | 5,867 / 5,868 |
| sum-bits/1709 | 20.36 | 78.18 | 75.62 | 73.03 | 7,265 / 7,265 | 5,867 / 5,868 |
| dot-product/1703 | 17.38 | 78.57 | 75.30 | 73.50 | 6,704 / 6,704 | 5,666 / 5,682 |
| dot-product/1709 | 19.42 | 85.66 | 81.41 | 80.14 | 6,704 / 6,704 | 5,666 / 5,682 |
| jacobi-1d/1703 | 126.11 | 1038.28 | 1003.23 | 992.94 | 41,319 / 41,319 | 32,721 / 32,819 |
| jacobi-1d/1709 | 119.71 | 1001.30 | 975.00 | 969.98 | 41,319 / 41,319 | 32,721 / 32,819 |
| conjugate-gradient/1703 | 351.14 | 6174.42 | 6075.47 | 5910.15 | 131,371 / 131,371 | 97,026 / 97,139 |
| conjugate-gradient/1709 | 366.29 | 6114.17 | 6014.45 | 5907.82 | 131,371 / 131,371 | 97,026 / 97,139 |

Jacobi-1d seed 1703 emitted 209,945,952 cumulative wire bytes with the full recipe and 70,898,784 with a shared layout. Conjugate-gradient went from 1,000,816,992 to 345,638,584 bytes. The resident path shortened complete inference in all eight pairs, yet the fastest resident case still took several times as long as vanilla. Cumulative serialization volume differs from peak process memory. [Paired traces and timings](encoding-results.json) · [Checked input buffer comparison](checked-results.json) · [Deliberately invalid recipes](negative.json)

A separate diagnostic checked the eliminated full root-row decodes, source header checks and transfers of the actual owned input buffer for three programs, with wrong-source controls. [Decode counters](decode-counters.json)

A separate five-second process sample on jacobi-1d attributes 2,625 of 3,753 joint inference samples to multi-parent generation/verification and 784 to the single-parent provider. Of the exclusive leaves, 777 samples landed in the shortlist closure. These counts use symbolized stacks within the executor; inlined functions can appear under their caller. Sampling time is excluded from the wall-clock comparison. This motivated baking the finite-domain learned port map and testing stronger incremental generation. [Inference-only sample summary](profile-jacobi.json)

## Reproduce

Use the external workspace environment. Build new binaries and bundles in fresh experiment directories. The offline bundle command for the two anchors is described in the [joint executor instructions](../joint-witness/README.md).

```sh
dir=benchmarks/pass3-cell-gpu/compact-recipes
python "$dir/holdouts.py" "$HOLDOUTS"
python "$dir/build_vanilla.py" "$VANILLA"
python benchmarks/pass3-cell-gpu/joint-witness/build.py "$NATIVE" --shortlist --merge-child --root-recipe --cli-allocator
python "$dir/study.py" "$NATIVE/session" "$VANILLA" "$HOLDOUTS" "$OUT"
python "$dir/check_results.py"
```

For each anchor / seed place the matching previously compiled package in `$HOLDOUTS/PROGRAM-SEED`. The new runtime remains experimental. The preexisting Python package provides offline tools; parity with vanilla remains a gate for shipping the neural runtime as a Python API.
