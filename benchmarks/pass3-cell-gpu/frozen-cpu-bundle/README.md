# Relocatable frozen CPU proof bundle

This is an internal native inference entry point for the measured Cell CPU configuration. Offline preparation takes a compiled program and its static compiler image, frozen weights from the repository, and the profile-aware executable. It ties the original query/key projections, asks that executable to Bake the finite-domain port table, and writes one directory atomically. Training traces, the original image, Python, the workspace path and the input compiler are unnecessary when subsequently running that artifact.

The directory holds the source program, static multi-parent plans, the single and multi-parent weights, merge-child configuration, root layout settings, the derived port table, a local request and a hash manifest. The profile name identifies the fixed settings in frozen-options.json, including complete generation, immutable pages of at most 8,192 tuples, two salted views, a one-row issuer and bounded directories. File references are local names. Existing untagged research bundles still use their earlier contract. A versioned bundle is checked against the compiled settings and its SHA-256 file list before inference. A source without a function-constructor merge route explicitly permits an empty optional merge library and still uses its own active root proofs.

```sh
dir=benchmarks/pass3-cell-gpu/frozen-cpu-bundle
python "$dir/build.py" "$EXP/frozen-cpu"
cargo cell-compile --source app.egg --output "$EXP/app-compiled"
python benchmarks/pass3-cell-gpu/codec.py "$EXP/app-compiled/program.json" "$EXP/app-image"
python "$dir/prepare.py" "$EXP/app-compiled/program.json" "$EXP/app-image" "$EXP/frozen-cpu/session" "$EXP/app-bundle"
"$EXP/frozen-cpu/session" --bundle "$EXP/app-bundle"
"$EXP/frozen-cpu/session" --audit-bundle "$EXP/app-bundle"
```

The ordinary entry returns compact JSON with the actual backend, neural source count, remaining RHS, physical recipe count, learned profile, state hash and full resident inference time. The second form runs the original program with detailed provenance, all Run boundaries, effective writes, Spine and physical allocation IDs. It is intended for independent audit. Model-specific plan preparation in this study supports the source grammar accepted by the current compiler and policy. This is an experiment bundle; a distributed Python runtime remains conditional on meeting the default CPU performance gate.

## Verified relocation

The tested sum-bits bundle reproduced the frozen plan's full sealed multi-parent digest, all 7,265 winning RHS, the original physical allocation ledger (5,867 direct / 5,868 fresh), and 7,970 sealed multi-parent tuples. It ran from an unrelated current directory after relocation, with all EGGFUSE-prefixed environment variables removed. The typed two-parent fixture also ran, with two winning RHS and an empty merge-route library. A changed port table, plan, request, incompatible pinned setting or unrelated static image was rejected. An unsuccessful preparation leaves no final bundle directory. [Native run, audit and negative controls](relocation.json)

This is a research profile. The frozen executable names its supported settings and reports the actual number of views, issued tuples and prefix probes. A successful manifest check establishes consistency of a supplied immutable directory; it is not a signature from a separate trust authority. The fresh CLI includes parsing, manifest reads, initialization and export in addition to inference.
