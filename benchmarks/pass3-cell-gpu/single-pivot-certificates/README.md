# Certify singleton proposal omissions from exact scalar function ports

On a real 3mm Pass 3, the whole-Run learned engine considered 845,168 singleton lanes. The Concat, Get and Single Expr-size rules alone accounted for 531,487 of them and 80,303 winners. The existing keyed freshness frontier already rejects many other lanes using shared port signatures. A surviving signature may still refer to the wrong exact key, and a fresh pivot can still lack a required function result.

The compiler inspects the existing singleton plan. It accepts a seminaive rule if its pivot is a table atom and every other table atom reads a unique, unary, equality-sorted function key bound directly by a pivot column. Repeated reads of the same function/column pair share one check. Typechecked, side-effect-free checked integer arithmetic may consume or constrain those outputs. Other primitives decline the plan, including operations that can update floating-point intern state. It conservatively passes every unrecognized rule/representation through the normal learned issuer.

For each scored lane, obtain its actual current pivot row and verify its table, live header and source epoch. For each necessary suffix key read the native canonical function directory, which already follows the runtime's union/rebuild publication. A missing key forbids this lane even with a fresh pivot. If all keys exist, the maximum of the pivot and named result epochs bounds the freshest witness of any successful binding. When that maximum falls below the Run watermark, seminaive evaluation rejects it. A surviving lane still goes through the entire original exact verifier and ordered RHS. Classification uses no source trace, accepted tickets or known final graph.

Network scoring, advancement of the original singleton token serial, detailed decisions and recurrent inputs are identical. An omitted lane consumes no root-page slot and no ordinary verification. Root-page wire serials are therefore local to each encoding. Source audits compare the winners with their original learned scores, singleton serials and parent versions, as well as the independent source schedule, ordered RHS, writes, union, Spine and final graph, the root producing rule, input, epoch, parent addresses, and physical root/nested Cell IDs. In a separate detailed run the original source checker actually rematches each dropped lane and must reject it. Timing disables that independent rematch. Tests use the live native Rust runtime, a common group-wave build, seed 1703 and the same complete frozen two-view model on both workloads. Load and export are included in the separate resident request wall measurements.

## Held-out full runtime

| Per-workload median, six interleaved samples after warmup | CG | 3mm |
|---|---:|---:|
| Independent default CPU inference, ms | 337.66 | 851.36 |
| Learned inference, original → proof, ms | 642.46 → 605.75 | 1,790.01 → 1,684.60 |
| Search interval, original → proof, ms | 451.58 → 419.85 | 1,327.32 → 1,213.69 |
| Full resident request wall, original → proof, ms | 753.52 → 721.14 | 2,016.33 → 1,906.93 |
| Actual sealed / verified singleton lanes, original → proof | 243,383 → 133,565 | 845,168 → 334,594 |
| Emitted root wire bytes (all providers), original → proof | 6,182,696 → 3,454,136 | 20,817,600 → 8,415,216 |

The new engine took less inference time in six of six paired samples on both workloads. It examined 159,196 / 604,303 eligible lanes and read 238,637 / 888,666 exact scalar-function epochs. Missing keys eliminated 11,075 / 32,978 lanes; the watermark eliminated another 98,743 / 477,596. All 620,392 eliminated lanes across both workloads were independently rematched and rejected. Compilation admitted 19 / 17 rule identities exercised in the held-out executions. The original default CPU remains faster: the trained path retains other singleton, multi-parent, verification and publication costs. The sample includes two workloads and one frozen seed.

| 3mm rule | Original lanes | Certified missing | Certified old | Remaining lanes | Source winners |
|---|---:|---:|---:|---:|---:|
| 154, Concat Expr-size | 234,483 | 12,334 | 193,295 | 28,854 | 28,854 |
| 153, Get Expr-size | 227,262 | 12,086 | 175,158 | 40,018 | 40,018 |
| 155, Single Expr-size | 69,742 | 4,398 | 53,913 | 11,431 | 11,431 |
| 151, Bop Expr-size | 29,877 | 1,248 | 25,946 | 2,683 | 2,683 |

For example, an old Concat only needs the two exact Expr-size keys to test freshness. Arbitrary recent writes to other Expr-size keys used to keep this candidate alive. When both required keys exist but both of their visible values predate the Run watermark, the packet cannot produce a source RHS, even if the integer sum itself would be legal. In these four rules every remaining lane produced a binding on 3mm. This observation does not generalize to arbitrary LHS result predicates. All original per-Run source checks and physical winner/ID audits passed on 2,896 / 4,260 Runs. [Individual samples and per-rule counts](results.json) · [Pinned source/model identities](manifest.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/single-pivot-certificates
python "$d/build.py" "$EXP/single-pivot-build"
python "$d/study.py" "$EXP" "$EXP/single-pivot-build/session" "$EXP/single-pivot-study"
python "$d/verify.py"
```
