# Relocatable frozen CPU proof bundle

This is an internal native inference entry point for the measured Cell CPU configuration. The native compiler reads the compiled source program, the settings and the two frozen checkpoints embedded in the profile-aware executable. It needs no GPU ingress or execution trace. It ties the original query/key projections, asks that executable to Bake the finite-domain port table, and writes one directory atomically. Training traces, the original image, Python, the workspace path and the input compiler are unnecessary when subsequently running that artifact.

The directory holds the source program, static multi-parent plans, the single and multi-parent weights, merge-child configuration, root layout settings, the derived port table, a local request and a hash manifest. The profile name identifies the fixed settings in frozen-options.json, including complete generation, immutable pages of at most 8,192 tuples, two salted views, a one-row issuer and bounded directories. File references are local names. Existing untagged research bundles still use their earlier contract. A versioned bundle is checked against the compiled settings and its SHA-256 file list before inference. A source without a function-constructor merge route explicitly permits an empty optional merge library and still uses its own active root proofs.

```sh
dir=benchmarks/pass3-cell-gpu/frozen-cpu-bundle
python "$dir/build.py" "$EXP/frozen-cpu"
cargo cell-compile --source app.egg --output "$EXP/app-compiled"
"$EXP/frozen-cpu/session" --compile-bundle "$EXP/app-compiled/program.json" "$EXP/app-bundle" 1703
"$EXP/frozen-cpu/session" --bundle "$EXP/app-bundle"
"$EXP/frozen-cpu/session" --audit-bundle "$EXP/app-bundle"
```

The ordinary entry returns compact JSON with the actual backend, neural source count, remaining RHS, physical recipe count, learned profile, state hash and full resident inference time. The second form runs the original program with detailed provenance, all Run boundaries, effective writes, Spine and physical allocation IDs. It is intended for independent audit. Model-specific plan preparation in this study supports the source grammar accepted by the current compiler and policy. This is an experiment bundle; a distributed Python runtime remains conditional on meeting the default CPU performance gate.

## Verified relocation

The tested sum-bits bundle reproduced the frozen plan's full sealed multi-parent digest, all 7,265 winning RHS, the original physical allocation ledger (5,867 direct / 5,868 fresh), and 7,970 sealed multi-parent tuples. It ran from an unrelated current directory after relocation, with all EGGFUSE-prefixed environment variables removed. The typed two-parent fixture also ran, with two winning RHS and an empty merge-route library. A changed port table, plan, request, incompatible pinned setting or unrelated static image was rejected. An unsuccessful preparation leaves no final bundle directory. [Native run, audit and negative controls](relocation.json)

This is a research profile. The frozen executable names its supported settings and reports the actual number of views, issued tuples and prefix probes. A successful manifest check establishes consistency of a supplied immutable directory; it is not a signature from a separate trust authority. The fresh CLI includes parsing, manifest reads, initialization and export in addition to inference.


## Source-only Rust lowering

The native compiler first computes the minimum independent source width by closing complete table keys and forward primitive operands. Breadth-first search then finds a connected independent prefix, followed by the original uniquely determined suffix instructions. Source order breaks ties. Unknown inverse computations are never inferred. Slot sets use actual source slot IDs and support more than one machine word. Each returned plan retains the minimum proof width separately from the number of independent picks in the connected prefix.

The existing Python `prepare.py PROGRAM IMAGE EXECUTABLE NEW_DIR` is an independent compatibility reference. Building the isolated research executable from this checkout still uses its existing experiment build driver. With the binary available, compiling the sealed bundle from a Rust compiler artifact and executing or auditing the bundle require only native programs. The optional seed defaults to 1703; seed 1709 uses its own embedded checkpoints.

The parity study starts from a copy of each program in a new directory. The Python reference also receives the old ingress image. It checks byte identity of source, sealed plans and port tables, exact binary32 checkpoint coefficients, and equality of parsed request and root settings. The four full audit calls cover sum-bits and a typed two-parent fixture at both seeds. On the other five programs the compact native call checks Run count, neural winner count and final graph against the default CPU. Each invocation must report that the learned policies executed and that issuance preceded verification. Detailed Run checks on the other programs belong to the separate executor studies.

```sh
python "$dir/check_native.py" "$EXP" "$EXP/frozen-cpu/session" "$EXP/new-compiler-comparison"
cargo test --manifest-path "$EXP/frozen-cpu/tree/Cargo.toml" --target-dir "$EXP/frozen-cpu/target" \
  --release --locked --offline -p eggfuse-cell-runtime --lib \
  --features precomputed-forest,slot-transfer-audit native_width_tests
python "$dir/verify.py"
```

Nine compilations covered six real Pass 3 programs and the one-rule two-parent fixture. Each Pass 3 program contained 582 rules and compiled 341 sealed multi-parent plans. The six independently timed native compilations at seed 1703 took 1.62–2.00 s each, including port-table construction and disk output. These are single offline observations per program. Compaction and inference have their own timing boundary. Both sparse-slot unit checks passed. [Compiler and runtime checks](native-parity.json)

## Compile the measured joint CPU configuration

With the same binary and compiled source, select the composed profile to use shared published single-parent headers and delayed arithmetic ports during multi-parent issuance. The default profile remains frozen-ports/v1. Native compilation and inference require no Python interpreter after the experiment executable has been built.

```sh
"$EXP/frozen-cpu/session" --compile-bundle "$EXP/app-compiled/program.json" "$EXP/composed-bundle" --profile composed-ports/v1
"$EXP/frozen-cpu/session" --bundle "$EXP/composed-bundle"
"$EXP/frozen-cpu/session" --audit-bundle "$EXP/composed-bundle"
```

The optional checkpoint seed precedes the profile flag. Both profiles use the same program, proof plans, trained weights, root configuration and compiled port table. The request and its hash manifest identify the chosen execution strategy. The compact execution report includes the actual number of published header updates, lazy arithmetic evaluations and signature cache hits on the composed path.

Six relocated real Pass 3 bundles reproduced the exact counts and final states of the measured joint CPU configuration, including its computed ports and header publications. The independent full source, raw-receipt and fresh Cell-ledger audits were repeated on sum-bits and conjugate-gradient. Recompiling sum-bits without a profile flag reproduced the original native bundle byte for byte. Separate negative controls covered a rehashed modified composed setting, a rehashed composed-only override on the frozen profile and an unknown compilation profile. [Measured portable execution](composed-profile.json)

```sh
python benchmarks/pass3-cell-gpu/frozen-cpu-bundle/check_composed.py "$EXP" "$EXP/frozen-cpu/session" "$EXP/check-composed"
```
