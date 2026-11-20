# Bounding fresh single-parent proposals by shared typed slots

On a seminaive rule every effective binding needs at least one visible source at or above its watermark. A fresh parent always passes this prefilter. For an old parent, every remaining table whose maximum visible epoch is still fresh must be checked. If any such table may contain a compatible fresh row, the original model sees the parent and the ordered verifier makes the final decision.

The compiler identifies equal source slots in the pivot and suffix. For each suffix field it can maintain a directory of the maximum epoch seen at each of the frozen model's 1,024 key signatures. A parent whose supplied slot maps to bucket 93 can only match rows in bucket 93 on that field. If that bucket is old, that table cannot supply the required fresh row. A rule with several suffix tables can discard the parent only if **every** currently fresh suffix atom is excluded by at least one of its constrained fields. Constant operands participate with canonical values. An unconstrained table, a missing directory, or a signature collision can leave an extra proposal. Primitive evaluations do not publish source epochs. The original graph still decides every accepted binding.

Two parents sharing a signature can reuse a decision when one source column supplies the dynamic fields of a rule occurrence. The runtime computes a verdict at the first encounter with that signature and broadcasts it to later parents. Stable parent address and version remain distinct, including after union. Source, signature directory and optional graph frame must agree on table generation and union generation. If a frame's row offset has a different dependency or epoch, the runtime reads the original dependency. Surviving proposals retain the original signed source pointer and go through the full allocator.

## Upper bound, training and admission

The experiments replay the original four training programs with the frozen seed-1703 actor on the checked CPU engine. Their archived training traces lack rejected suffix fields and contemporary index state. The oracle therefore reruns the actual matching schedule and checks its RHS, writes and Spine against the archived traces and its full endpoints against an independent vanilla runtime. It observes hidden/visible rows at the original Run and leaves the model's inputs and generated tokens unchanged.

For each remaining old parent it measures three bounds under the same observable source snapshot:

1. Exact compatibility with the tuple of projected original values on each possible fresh suffix row. This is the strongest test using those projected fields alone.
2. One maximum epoch per individual learned key signature on each available projected column. If every candidate table is excluded, the parent can be removed. The oracle asserts every negative agrees with the exact compatibility calculation.
3. The work covered by directories the existing multi-parent generator had already built at the matching versions, with the subset for which a current pivot frame is also available. It additionally counts distinct per-rule groups of old-parent signatures, fully excluded groups, and complete input banks that can be dropped.

The real arms either consume only existing directories or additionally maintain a fixed-size private directory cache. A new scan is admitted by the initial old-parent count, old-parent fraction and a per-call scan limit in proportion to the old bank. One directory costs 8 KiB. The experiment compares 8, 64 and 256 KiB; stale versions expire before admission. The budget counts private epoch-array payload bytes. Temporary scan rows, output headers, the existing native indexes, allocator metadata and a 1 KiB group-verdict array are additional. The result checker compares Run schedule, RHS, effective writes, union order, Spine and final graph. It also verifies the surviving single and multi-parent addresses and source ordinals plus every directly attributed root and nested Cell ID. Dropping old intermediate candidates can change the generated stream, model scores and temporary packet numbers.

Training uses affine-twins, clamped-ramp, segmented-prefix and window-laplacian. The budget is frozen to the lowest geometric mean of complete per-workload latency ratios among the four nonzero-budget candidates. A zero-budget control measures the cost and coverage of resident indexes with the selected row gates. Only then are sum-bits, dot-product, jacobi-1d and conjugate-gradient examined. Timing uses five resident measurements after warmup with rotating, reversed arm order and explicitly includes graph scans, code lookup, model execution, validation, repair and commit.

## Complete-pass results

Across the four training sources the original table-wide prefilter left 123,393 single-parent addresses. A raw-value tuple oracle can exclude 102,179. Individual 10-bit keyed epoch directories exclude 101,335, including 75,062 of 79,664 distinct old-parent signature groups and 1,868 whole input banks. Only 1,260 of the negative parents have pre-existing compatible suffix directories; 262 of these also have an up-to-date pivot frame available. The oracle examined 673,412 suffix rows across overlapping queries, including 38,239 at or above their watermarks. These visits show the opportunity and its construction cost; this diagnostic does not change a proposal.

Training runtime ratios to the original execution were 1.008 for resident-only, 0.995 for 8 KiB, 0.904 for 64 KiB, 0.909 for 256 KiB and 0.962 for the stricter 64 KiB admission. The frozen 64 KiB rule needs at least 16 old parents comprising at least half the input bank. Cold scans are admitted up to twice the old-parent count per occurrence. Directories and current row sources are still checked at invocation time. [Training upper bounds](training-upper.json) · [Calibration](calibration.json) · [Frozen policy](admission.json)

| Held-out source | Single-parent packets before → after | Semantic upper bound with existing signatures | Already-built directories alone | Full ms off / resident / bounded | Vanilla ms |
|---|---:|---:|---:|---:|---:|
| sum-bits | 27,299 → 8,378 | 21,561 | 901 | 40.29 / 40.76 / 38.31 | 22.76 |
| dot-product | 31,745 → 10,990 | 25,643 | 889 | 37.45 / 36.99 / 33.16 | 18.32 |
| jacobi-1d | 320,752 → 61,416 | 280,034 | 3,048 | 292.45 / 288.29 / 236.91 | 107.32 |
| conjugate-gradient | 1,671,823 → 279,611 | 1,460,032 | 10,390 | 1,413.79 / 1,418.04 / 1,109.93 | 364.08 |

The source of the largest conjugate-gradient opportunity is rule 153: `Get(tup, i)` and `Expr-size(tup)` imply a size for the Get result. For an old Get whose operand has signature 93, the maximum epoch for signature 93 in the size table is sufficient to exclude the proposal when stale. A size update for a different tuple can raise the table-wide maximum without invalidating that proof. The full-signature bound excludes 448,685 of rule 153's 501,327 old Get candidates. None has a sufficient pre-existing directory in the previous runtime.

On conjugate-gradient, the bounded path spends 466,607 first-signature decisions and broadcasts 623,927 additional single-column verdicts across repeated parents. It skips 589 complete parent banks. It still performs 999,369 exact source row reads in the absence of a usable ordered pivot frame, and visits 859,854 suffix source rows while establishing directory contents. These are counted row visits; one visit can populate multiple signature fields. The maximum private directory payload across the held-out cases is 48 KiB. Total process memory is outside this measurement. [Held-out oracle](heldout-upper.json) · [Production costs and endpoint evidence](timing.json)

The four held-out speed changes are 4.93%, 11.44%, 18.99% and 21.49% lower median complete inference time in order. All four retain 100% of RHS tickets and the same fresh directly allocated IDs (5,867/5,868, 5,666/5,682, 32,721/32,819, and 97,026/97,139). The comparison uses a single frozen seed on one host and a checked native Cell runtime with the constant-key transaction guards enabled in every neural arm. On conjugate-gradient, this leaves complete inference 3.05× the vanilla time.

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/single-signature-frontier
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-frontier-build"
bin="$e/NEW-frontier-build/session"
python "$d/measure.py" oracle "$bin" "$e" "$e/NEW-frontier-training-upper"
python "$d/measure.py" calibrate "$bin" "$e" "$e/NEW-frontier-calibration" --repeats 5
python "$d/freeze.py" "$e/NEW-frontier-calibration/results.json" "$e/NEW-frontier-admission"
python "$d/measure.py" oracle "$bin" "$e" "$e/NEW-frontier-heldout-upper" --cases sum-bits dot-product jacobi-1d conjugate-gradient
python "$d/measure.py" time "$bin" "$e" "$e/NEW-frontier-heldout-time" --admission "$e/NEW-frontier-admission/admission.json" --cases sum-bits dot-product jacobi-1d conjugate-gradient
```
