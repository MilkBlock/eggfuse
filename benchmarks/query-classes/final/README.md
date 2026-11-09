# Final simple class ranges and publication receipt demand

This checkpoint implements checked cross-stage operator coverage, immutable
signal classes, class-range candidate filtering, and receipt capture only when
the admitted Entry wiring requires it. It also replaces a linear membership
scan in the final ownership report with the existing ordered-set lookup,
preserving the assertion. The bounded-lookahead/Drop-counter experiment is
withdrawn. Results measure the **standalone Cell CPU**, not native egglog.

The feature is implemented, but **the two-workload inference/process performance
gate has not passed**. Raytrace improves relative to the shared-code experiment;
sum-bits inference improves while its process improvement remains uncertain.
The archived fastest path still wins both workloads. Report-time improvement
is kept separate from RHS execution improvement.

## Final normal measurements

The normal candidate is `out/condition-bake/runtime-query-classes-final`,
SHA-256 `07a0863144730e4d1f89d2a7b3e122c88bf5d18c9d64abc035431679196523a7`.
It is built **alone** with release `sparse-cells,view-ports,storage-metrics`.
Neither allocator nor ordered-audit instrumentation is present.

`baseline` uses checkpoint `86800d89` frozen `runtime-code` and the original
baked artifact. `final` uses the classified copy of that same artifact. Both
use `--local-congruence`. `fast_archived` uses source `8fffff65`, the original
artifact and `--repair-ports --entry-publications`. Exact paths, artifact hashes,
source hashes and build command are in the manifests and `metadata.json`.

Each invocation is a new process. The three lanes run sequentially in a
shuffled interleaved order; blocking `waitpid` measures whole-process time.
sum-bits has one warmup and 15 measured repetitions per lane. Raytrace has two
measured repetitions per lane without another warmup and remains a bounded
pilot. The parent held production source fixed and did no CPU/Cargo work during
timing. No observations were discarded, and no repetitions were added to seek
a favorable result.

| Workload | Lane | Inference median | Process median |
| --- | --- | ---: | ---: |
| sum-bits | baseline | 32.073 ms | 194.077 ms |
| sum-bits | final | 30.173 ms | 195.039 ms |
| sum-bits | fast_archived | 21.609 ms | 144.300 ms |
| Raytrace | baseline | 13.627 s | 23.184 s |
| Raytrace | final | 12.234 s | 15.525 s |
| Raytrace | fast_archived | 8.270 s | 10.631 s |

Final versus shared-code baseline reduces Raytrace median inference by 10.22%
and process time by 33.03%; both pairs improve. The sample size does not support
a precise general speedup claim. sum-bits median inference improves 5.92%,
with a descriptive paired-bootstrap 95% ratio interval `[0.9357, 0.9530]`.
Its process interval `[0.9800, 1.0181]` crosses one and the process median is
slightly worse. The paired median ratio and ratio of separate medians need not
agree under variation; both are preserved in the JSON results.

The preceding four-lane campaigns remain under the parent directory and
`adaptive/`. They show that receipt pruning plus class infrastructure alone
did not demonstrate a speedup, and that bounded lookahead did not improve
Raytrace inference over simple class ranges. Those negative ablations are not
replaced by this final comparison.

## Timing attribution

| Workload / lane | Load | Setup | Export | Report | Residual after report |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum baseline | 112.066 ms | 3.434 ms | 6.681 ms | Unmeasured | Unavailable |
| sum final | 111.988 ms | 3.051 ms | 6.686 ms | 10.865 ms | 30.645 ms |
| Raytrace baseline | 0.539 s | 0.005 s | 1.773 s | Unmeasured | Unavailable |
| Raytrace final | 0.545 s | 0.005 s | 1.760 s | 0.698 s | 0.283 s |

Baseline Raytrace has 7.239 seconds not attributed to load/setup/inference/export;
it did not separately measure report construction. The preceding ranges versus
adaptive campaign directly measured report dropping from 7.280 to 0.694 seconds
while preserving the same membership checks. The final candidate retains that
report correction. This explains most of the large process improvement beyond
the execution-phase class filtering benefit.

`report_seconds` includes report construction and additions before export.
Remaining residual includes serialization/output, teardown and other unmeasured
intervals; it is not a direct measurement of drop. The archived executable
omits load time, so no complete phase decomposition is invented for it. Old
report fields remain missing rather than zero. Individual phase medians need
not add to median process time; `phase-attribution.json` includes all per-sample
phases and residuals, plus additive paired-mean decompositions.

## Work accounting

| Work | sum baseline | sum final | Raytrace baseline | Raytrace final |
| --- | ---: | ---: | ---: | ---: |
| Domain signal visits | 58,494 | 12,048 | 55,413,157 | 14,543,598 |
| Domain slice visits | 59,462 | 19,268 | 63,490,061 | 14,378,473 |
| Class probes | Absent | 48,367 | Absent | 16,067,446 |
| Range jumps | Absent | 34,109 | Absent | 11,076,813 |
| Domain results | 5,693 | 5,693 | 6,235,405 | 6,235,405 |
| Exact key candidates | 17,491 | 17,491 | 8,475,767 | 8,475,767 |

Filtering reduces instance/slice reads while exact candidate/Eq work remains.
Counters are identical across every measured/warmup sample within each lane.
Rejected groups are not scanned to manufacture a skipped-member count. The
final implementation does not contain the withdrawn lookahead key-read metric.

The classified artifacts are identical to those used by the first experiment:
541 classes / 3,780 mask words / 2,410 symbol slots on sum-bits, and
583 / 4,074 / 15,666 on Raytrace. They add 26,181 and 71,198 artifact bytes.
These are static storage quantities, not execution savings.

## Full ordered execution and allocation audit

A separate diagnostic executable uses
`sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics`.
Its SHA-256 is
`5c65ec667e66eeb516bf0c10aceb72312f6d7e79b0d3f3c5dd129e6748e8b795`.
Both it and the frozen shared-code allocator executable complete sum-bits
(1,428 Runs) and Raytrace (16,883 Runs).

**State, ordered RHS, effective writes, resumes and source schedule hashes match
exactly. Spine contents also match after removing only the artifact's
`program_sha256` metadata field.** Different certificate artifacts necessarily
have different program hashes; no execution fields or array order are discarded.
The checks compare executed effects, not logical match counts.

| Execute cost | sum baseline | sum final | Raytrace baseline | Raytrace final |
| --- | ---: | ---: | ---: | ---: |
| Allocation calls | 212,388 | 203,944 | 48,838,533 | 45,700,561 |
| Reallocation calls | 20,731 | 20,731 | 3,344,754 | 3,344,754 |
| Requested bytes | 36,043,378 | 35,655,666 | 10,753,237,208 | 10,615,312,740 |

Execution allocation calls decrease 3.98% on sum-bits and 6.43% on Raytrace;
requested bytes decrease 1.08% and 1.28%. Both lanes include identical audit
instrumentation. Diagnostic elapsed times are not used for performance admission.

Setup costs are counted separately. Setup allocation calls decrease
70,380→68,061 on sum-bits and 121,390→119,071 on Raytrace; setup requested bytes
decrease 8,090,491→7,901,667 and 13,107,983→12,484,055. These scopes exclude parsing.
However, the total live requested bytes after setup increase by 493,740 and
1,381,840 bytes, including the larger parsed artifact and compiled static plans.
Lower allocation traffic does not mean lower retained memory. Requested bytes
and allocator live bytes are not RSS. Full counters and scope descriptions are
preserved in `validation.json`.

The final source passes 343 workspace tests with four preexisting ignored,
then eight non-sparse query-class/ownership-receipt tests and the no-default
runtime check. Source hashes remained unchanged through normal timing,
diagnostic build, audits and final checks. Commands, environments, timestamps,
log hashes and historical patch hashes are recorded in `validation.json`.
These semantic and cost results do not override the failed normal performance
gate described above.

## Reproduction and source boundaries

Normal source and artifact manifests are frozen separately from the diagnostic
build. The original joint runtime/compiler build mismatch is documented in the
parent directory; no timings from it are admitted. Build the runtime package
alone to preserve the same dependency feature set as the baselines.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/private/tmp/eggfuse-union-digest/target cargo build --release --locked -j 2 -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
python3 benchmarks/raytrace-parallel/measure.py benchmarks/query-classes/final/sum-bits-manifest.json out/query-classes-final/sum-bits --repeat 15 --warmups 1 --timeout 30
python3 benchmarks/raytrace-parallel/measure.py benchmarks/query-classes/final/raytrace-manifest.json out/query-classes-final/raytrace --repeat 2 --warmups 0 --timeout 180
python3 benchmarks/query-classes/collect.py out/query-classes-final benchmarks/query-classes/final --ablation final
```

Preserve named executables before changing Cargo features; measurement output
directories must be new. The collector checks the frozen source manifest and
does not execute a workload. The historical `first.patch` and `adaptive.patch`
archives are based on `86800d89`; the retained implementation is this checkpoint's
production source. Complete diagnostic validation is recorded separately in
`validation.json`.

The diagnostic build and audits are independent of normal timing:

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=/private/tmp/eggfuse-union-digest/target cargo build --release --locked -j 2 -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics
python3 benchmarks/result-port-repair/audit.py out/condition-bake/runtime-code-allocator benchmarks/query-classes/final/audit-baseline-manifest.json out/query-classes-final/baseline-audit
python3 benchmarks/result-port-repair/audit.py out/query-classes-final/runtime-final-allocator benchmarks/query-classes/final/audit-final-manifest.json out/query-classes-final/final-audit
python3 benchmarks/query-classes/final/collect-audit.py out/query-classes-final benchmarks/query-classes/final
```

Copy the newly built executable to the named diagnostic path before auditing;
keep the frozen normal binary separate. These commands require new audit output
directories. The final collector validates the saved audits and check logs; it
does not rerun them.
