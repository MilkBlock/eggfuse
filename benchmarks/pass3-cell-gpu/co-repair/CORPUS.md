# Pass 3 pre-union corpus

The eight native eggcc inputs use the original source-family split, frozen before any tracing: four train, two development and two held out. Sum-bits and dot-product are additional named anchors. The new inputs cover 10,376 source Runs; with the two anchors the census covers 13,339 Runs and 11,239 effective unions. There are two independent Rust executions and one complete Metal execution per input. Additional observation is compiled only with `slot-transfer-audit` and enabled only by `--audit-repair-inputs`. Production timing excludes observation.

Before linking a losing root, Rust records **every existing reverse subscriber**, including function rows, immutable fact addresses, subsumed facts and subscribers without a matching current column. It records which columns contain the losing root, resolving through the pre-link partition. Each ordered constructor key check identifies the exact physical survivor on collision. A subsequent retirement is a separate event. The stable fact address contains the actual owner Cell and instruction position. An unresolved or function subscription always remains an external obligation in the following size bound.

| Input | Effective unions | Cross-owner result and key in same union | All registered work fits ≤2 owners | Fits ≤3 owners |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 1,039 | 231 | 19 | 70 |
| dot-product | 611 | 109 | 12 | 21 |
| gemm-bias-relu (held out) | 2,317 | 554 | 64 | 181 |
| stable-argmax (held out) | 1,230 | 283 | 20 | 78 |

The last two columns are necessary owner-count bounds within the cross-owner cohort. They do not certify cheap execution, exclusive ownership, or the absence of a whole-key collision. Multiple instructions already owned by the same CPU Cell count once. Counts of registered incidences before a union differ from dirty repairs after coalescing. Constructor signatures, stable row identities, declared Run boundaries and effective writes remain authoritative.

The collector checks compiler and source identities, full final graph bytes, per-Run RHS, effective write and Spine digests, and controls against the ordinary CPU observer. The separate GPU audit aligns constructor births, compares the ordered evidence and class partition at each Run, and checks the final typed graph. The resulting labels are for the standalone Cell engine using real eggcc inputs. Native interpreted Bril outputs and dataset split provenance are recorded separately in the diversity manifest.

```sh
ws=/Volumes/EggFuseWorkspace
root="$ws/experiments/NEW-repair-corpus"
base="$ws/experiments/pass3-atlas-integration-20261120"
weights="$ws/experiments/rotary-axes-20261119/packed-1703/final.pt"
cargo build --release --locked -p eggfuse-cell-compiler
cargo build --release --locked -p eggfuse-cell-runtime --features slot-transfer-audit
~/.local/bin/eggfuse-job submit --kind compute -- "$ws/bin/run-eggfuse" env PYTORCH_ENABLE_MPS_FALLBACK=0 python benchmarks/pass3-cell-gpu/co-repair/collect.py "$ws/experiments/eggcc-diversity-20261119-pass3-v2" "$base" "$weights" target/release/eggfuse-cell-compiler target/release/eggfuse-cell-runtime "$root"
```

After collection, `census.py CORPUS REFERENCE OUTPUT` regenerates the owner counts. Full traces remain external. [Frozen source split](../../eggcc-diversity/manifest.json) · [CPU/GPU audit manifest](corpus.json) · [Owner bounds](owner-census.json)
