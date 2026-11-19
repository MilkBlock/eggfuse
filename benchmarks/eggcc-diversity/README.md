# Bril workloads for eggcc diversity experiments

These eight original programs exercise data and control dependencies relevant to Cell generation. The existing frozen `workloads/pass3/suite.json` has eleven cases, including `dot-product`, `fenwick_tree`, `jacobi-1d`, `3mm` and `raytrace`. These additions provide small, inspectable examples with explicit corner cases. Similarities between kernels, such as shared loops and memory subscripts, are intentional. New names alone do not establish novel EggFuse rule coverage.

| Split | Source | What changes the valid computation | Golden output contract |
| --- | --- | --- | --- |
| Train | `affine-twins` | One loop-invariant scale and an activation used by two consumers | Print Σx² and Σ(x−i), where x=(shift+2)i+1 |
| Train | `clamped-ramp` | Two range checks converge before reduction | Print Σclamp(3i−n, 0, ceiling) |
| Train | `segmented-prefix` | Segment boundaries reset two loop-carried values | Print the sum of all within-segment prefixes and the final prefix |
| Train | `window-laplacian` | Neighboring triples read overlapping locations after initialization | Sum the discrete second difference of i³ at interior points, equal to Σ6i |
| Development | `histogram-scatter` | Later updates observe stores to the same bucket | Add the post-increment bucket count at every update, equivalent to Σ(⌊i/buckets⌋+1) |
| Development | `gated-state` | Two states are updated together under a gate on their old values | For old `(a,b)`, use `(a−b,a+b+i)` if `a>b`, and `(a+b+i,b−a)` otherwise |
| Held out | `gemm-bias-relu` | Nested row, column and reduction loops finish the reduction before bias and activation | Sum max(0, Σₖ(r+k)(k−c)+c) over all row/column pairs |
| Held out | `stable-argmax` | Repeated maxima must retain the first contributing index | Print the earliest argmax and score of min(i,cap), or `−1 −1` on empty input |

`manifest.json` freezes the split by source family and three input/output fixtures per program. Keep every argument case and all derived graphs, schedule variants, Run windows, bindings and token encodings of a program in that program's split. The corpus has eight source programs. Arguments give extra interpreter checks but do not add distinct compiler workloads. The matrix case generates integer operands procedurally; these fixtures carry functional compiler semantics and supply no hardware cost measurements. `heldout` describes the intended split for subsequent training. Inspection and execution of its sources here are disclosed.

## Reproduce

Use the eggcc CLI from the checkout matching the frozen upstream suite (`ae80f82a403c1209fb084b115ee89470c7e66d0e`). Pass a fresh directory to export `*.egg` inputs. The verifier invokes the Bril parser/interpreter and the tree-DAG round trip at every fixture. For `--pass3-dir`, it additionally runs `optimize --interp --eggcc-schedule parallel --stop-after-n-passes 3` on each default fixture and checks the resulting program's printed tokens. A second invocation with `--run-mode egglog` captures Pass 3's input after the first two passes. `RAYON_NUM_THREADS=1` limits host parallel work; `parallel` names the eggcc ruleset schedule.

```sh
python3 benchmarks/eggcc-diversity/verify.py \
  --eggcc /path/to/eggcc/target/release/eggcc \
  --report /path/to/new-report.json \
  --pass3-dir /path/to/new-pass3-dir
```

The report records exact compiler binary SHA-256, source SHA-256, static Bril instruction/label counts, validated interpreter arguments, and SHA-256 of each captured input. A capture is an executable egglog source program **before** Pass 3. Per-Run mutation records and training certificates require a separate trace capture. The two-rule neural ablation uses its own controlled family holdouts.

## Recorded run

On 2026-11-19 the verifier completed on all eight programs using the local `check_statewalk/target/release/eggcc` executable, SHA-256 `162b82499bcc131dead74e00fe21f5ecbfe2dd4c4e3e1cb9a78a2b6383402897`. Its adjacent checkout was at `ae80f82a403c1209fb084b115ee89470c7e66d0e`; the recorded binary digest identifies the executable used. All 24 golden cases passed direct interpretation and interpretation after DAG round trip. All eight default fixtures passed interpretation after three native optimization passes. The verifier also captured eight Pass 3 inputs and their hashes were rechecked from disk. The programs span 20–35 Bril instructions and 3–12 labels before lowering. Instruction counts do not measure rule coverage.

`validation.json` holds the per-program results. The raw Pass 3 inputs are on the external volume at `/Volumes/EggFuseWorkspace/experiments/eggcc-diversity-20261119-pass3-v2/`. They are native eggcc exports. To package them for an EggFuse suite that expects flattened sources, apply its flattening and semantic checks first. This run did not replay these programs with the neural model or derive training labels from the optimizer's final result.
