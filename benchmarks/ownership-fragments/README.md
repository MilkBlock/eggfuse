# Baked local repair fragments

This extends `c4bad788` in the **standalone Cell CPU**, using the existing frozen
208-unit sum-bits catalog. It does not modify or measure the native egglog runtime.
The previous execution exposed 1,348 cold shape materializations, 21,618 copied
instruction handles and 10,572 obsolete owner-anchor reads during inference.
Its smaller boundary directory did not beat the ordinary fast baseline.

The opportunity is to discharge this work when loading a baked descriptor and
at a checked Entry transition. Actual checked receipts prove the substitutions;
future unions and predicted matches never establish equality. Exact congruence
key probes, source-order effects, late external aliases and visibility boundaries
remain obligations of the executing graph.

## Changes

The old lifetime-owner system is removed, including owner selection, its separate
capacity checks, per-Cell/per-fact owner IDs and the retirement queue. Components
already account for live facts and retain source frame addresses until their last
consumer dies. There is no replacement owner membership list or internal
eclass-to-consumer reverse index.

`profile-cell-ownership` is an explicit diagnostic training command. It records
checked applications that actually create owned bodies, and the first actual
cross-frame reuse of a consumer's input binding. It also projects each observed
last edge into a local producer/receiver pair, so that the same suffix can be
selected independently of its earlier prefix. These alternatives overlap; their
scores cannot be added as whole-execution savings.

`bake-cell-ownership --profile FILE` consumes this evidence without executing the
workload. It ranks repeated candidates by avoided binding/boundary record
operations minus transition probes, relative to their instruction count. Each
candidate needs at least two observed activations and positive record-operation
credit. Selection is limited to 256 descriptors and a ranking budget of 16,384
instruction handles, charging each required prefix once before code interning.
That instruction-count budget is not a physical-memory cap. Shared code, prefix
closure, loading, instance maintenance and missed transitions must still be paid
for in the whole-execution comparison. The score is not calibrated latency.

A fragment contains at most four frames. Its ports are local symbolic parameters;
runtime frame/eclass IDs and the history preceding the root do not identify its
code. Equivalent local programs and port wiring are interned together, even when
different Entry guards reach them. Guards remain distinct and are checked against
actual receipts. The loader rederives all selected wiring and the complete v4
marker descriptor; a valid checksum cannot authorize an invalid route.

Production execution only activates these prepared states. A continuation updates
the component's frame parameters and selects existing immutable slices. It never
inserts a new recipe key, materializes a shape or copies instructions. Unknown
continuations and full fragments keep external boundary notifications. Rules with
no selected continuation skip Entry receipt collection entirely. The uncomposed
control therefore performs no fragment dispatch.

This is bounded local composition. It does not promise that arbitrary chains or
joins between existing components become internal. Cutting a chain can increase
the boundary count relative to the previous dynamic 16-frame composition. The
point of the comparison is whether eliminating construction and duplicate
bookkeeping pays for those remaining boundaries.

Ordinary source programs now defer ownership preparation until it is enabled.
Artifacts containing ownership descriptors are still validated when loaded.
Routine reports contain a small plan summary; the full descriptor remains in
`markers.json`. Thus ordinary execution does not construct or serialize an unused
ownership plan. Cold loading and reporting still count in the process clock.

Canonical artifact hashing traverses borrowed JSON values in sorted-key order,
preserving the existing ASCII/UTF-16 escape format without cloning the complete
tree. Frame addresses use dense slots with a sparse-ID fallback; boundary buckets
inline singletons. These storage choices do not establish an allocation win:
the final execute allocation count is still higher than the ordinary backend.
The frame directory retains its dense high-water capacity, which remains a
limitation for long-lived workloads.

## Verification and evidence

The workspace passes **220 tests**, with four preexisting ignored. All **24**
focused tests pass in sparse and non-sparse configurations, and a runtime build
without default features passes its compile check. Fixtures cover late union,
origin deletion, dynamic aliases, capacity overflow, candidate completeness,
invalid routes, inactive-plan loading, local suffix reuse across distinct
prefixes, different guards sharing code, and an active marker encountering an
unseen prefix. Semantic fixtures compare each Run with the ordinary backend
and execute their source in native egglog; these are correctness checks, not
native egglog performance results.

The sum-bits audit compares the ordinary control, uncomposed ownership and baked
fragments. Exact state, schedule, ordered RHS, effective writes, resumes and
normalized Spine traces also match the committed `c4bad788` audit. Logical rule
matches are never counted as committed mutations.

`profile.json` retains the observations, `bake.json` the selection and coverage,
`monitor.json` every publication barrier, and `audit.json` the semantic hashes.
`timings.json` retains all samples from the final normal-build comparison;
`allocations.json` comes from a separate allocator diagnostic. Allocation requests
are measured during execute only, exclude setup/export, and are not RSS.

The timing lanes are the ordinary fast baseline (`8fffff65`), the previous
composition implementation (`c4bad788`), current ordinary control, current
uncomposed ownership, and current baked fragments. Each uses one warmup and 31
interleaved fresh processes. The admission rule is unchanged: the upper 95%
paired-bootstrap ratio must be below one for both inference and process wall
against the ordinary fast baseline. The profile and evaluation use the same
frozen workload; this is not held-out evidence or a claim about larger workloads.
Separate profiling and Bake are preprocessing costs that need amortization.

## Result: acceleration rejected

The final comparison uses equal-length executable/input symlinks and numeric
output paths. Medians in milliseconds:

| Lane | Inference | Whole process |
| --- | ---: | ---: |
| Ordinary fast baseline, `8fffff65` | 21.335 | 147.397 |
| Previous composition, `c4bad788` | 24.548 | 181.120 |
| Current ordinary control | 21.472 | 147.238 |
| Current uncomposed ownership | 22.156 | 152.869 |
| Current baked fragments | 22.246 | 187.626 |

Fragments reduce inference time **9.4% versus the previous composition**, but are
**4.3% slower in inference and 27.3% slower in whole-process time than the ordinary
fast baseline**. The respective 95% paired-bootstrap ratio intervals are
`[1.0315, 1.0527]` and `[1.2600, 1.2936]`. Against current uncomposed ownership,
inference is effectively unchanged (ratio `1.0041`, interval `[0.9909, 1.0135]`).
Current ordinary control is consistent with the frozen fast baseline. This
backend remains opt-in; structural improvements do not admit it as an acceleration.

The compiler selects 256 descriptors: 259 guarded transitions reach 630 prepared
shapes, including 376 initial shapes. Runtime uses 1,066 baked transitions, with
zero shape construction, zero instruction-handle copies, and zero old owner-anchor
reads. Those counters were 1,348 materializations, 21,618 copies and 10,572 reads in
the predecessor. Uncomposed ownership now has zero fragment receipt/dispatch work.

| Structural work on sum-bits | Previous composition | Current uncomposed | Baked fragments |
| --- | ---: | ---: | ---: |
| Live external bindings | 3,434 | 4,922 | 4,016 |
| Binding records created | 6,873 | 8,909 | 7,665 |
| Binding lookup/read operations | 12,430 | 12,430 | 12,430 |
| Typed repair field checks | 2,098 | 2,098 | 2,098 |
| Key completions | 1,046 | 1,046 | 1,046 |

The bounded design cuts external bindings 18.4% relative to uncomposed ownership,
but retains more boundaries than the previous dynamic 16-frame design. Its 2,994
transition probes include 1,928 misses. All 2,895 eligible live facts remain owned,
with 878 result publications and identical ordered semantics. Ordinary repair
needs 3,773 field checks, so sharing reduces repair work; it has not reduced total
execution time below ordinary repair.

Execute allocation requests are 116,981 for current ordinary control, 129,430 for
uncomposed ownership, and 129,207 for fragments: fragments still allocate 10.5%
more often than ordinary control. Fewer binding records do not imply fewer total
lookups, field attachments, retirements or allocations. In particular, the 12,430
binding reads remain unchanged. The next useful target is direct access to baked
local signal slots during attachment/retirement and dispatch, reserving the
boundary directory for external aliases. Adding descriptors without removing
these operations is not supported by this result.

Cold loading also remains material: the fragments median is 116.868 ms versus
81.007 ms for current ordinary control. Baked descriptors are reconstructed and
revalidated at load time; they are not a ready-to-map execution image. Profiling
and Bake themselves are additional offline costs, excluded from the table.

`intermediate.json` retains the rejected earlier implementation, whose full-tree
source hashing and preparation reached a 398.7 MB peak RSS. The final fragments
peak is 187.8 MB, versus 177.0 MB for the fast baseline. The subsequent unnormalized
campaign is retained in `loading-sensitivity.json`: with the same binaries and
input hashes, its control/uncomposed load medians were 79.969/117.621 ms despite
identical parse inputs. Equal-length command paths bring them to 81.007/80.871 ms.
The allocator/layout mechanism is not established; do not attribute the earlier
gap to ownership preparation. Both campaigns reject acceleration. No failed
campaign is presented as a successful speedup.

`composition_entry_reads` now counts checked Entry receipts; the predecessor
counted individual source columns, so these values must not be subtracted as
identical work. Shape construction counters cover diagnostic training but must
remain zero in production. `marker_anchor_reads` stays zero to make removal of
the old owner-selection path explicit. Bindings count logical records; actual
allocation requests are reported separately.

## Reproduction

Use new output directories. The frozen source catalog comes from the
[producer-receipts experiment](../producer-receipts/README.md). Retain or rebuild
the two archived comparison binaries at their stated revisions. Build compiler
and runtime separately to preserve exported JSON ordering for exact hash checks.
Only sum-bits is executed; no Raytrace run or union-frequency survey is needed.

```sh
mkdir -p out/ownership-fragments
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2 > out/ownership-fragments/workspace-tests-final.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test cell_ownership -j 2 -- --nocapture > out/ownership-fragments/focused-final.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test cell_ownership -j 2 > out/ownership-fragments/non-sparse-tests-final.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2 > out/ownership-fragments/no-default-check-final.log 2>&1
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake -j 2
cp target/release/eggfuse-cell-compiler out/ownership-fragments/compiler-final
out/ownership-fragments/compiler-final profile-cell-ownership --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-fragments/profile-sum-final
out/ownership-fragments/compiler-final bake-cell-ownership --program out/producer-receipts/learn-sum-bits/program.json --profile out/ownership-fragments/profile-sum-final/profile.json --output out/ownership-fragments/baked-sum-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/ownership-fragments/audit-runtime-final
python3 benchmarks/result-port-repair/audit.py out/ownership-fragments/audit-runtime-final benchmarks/ownership-fragments/audit-manifest.json out/ownership-fragments/audit-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics -j 2
cp target/release/eggfuse-cell-runtime out/ownership-fragments/runtime-final
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics -j 2
cp target/release/eggfuse-cell-runtime out/ownership-fragments/allocation-runtime-final
out/ownership-fragments/allocation-runtime-final --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-fragments/allocation-final-control --repair-ports --entry-publications
out/ownership-fragments/allocation-runtime-final --program out/producer-receipts/learn-sum-bits/program.json --output out/ownership-fragments/allocation-final-uncomposed --cell-ownership
out/ownership-fragments/allocation-runtime-final --program out/ownership-fragments/baked-sum-final/program.json --output out/ownership-fragments/allocation-final-fragments --cell-ownership
python3 benchmarks/leaf-completion/measure.py benchmarks/ownership-fragments/timing-manifest.json out/ownership-fragments/timing-normalized --repeat 31 --normalize-paths
python3 benchmarks/ownership-fragments/collect.py out/ownership-fragments benchmarks/ownership-fragments
```

The collector also retains an optional existing `timing-final/samples.json`
campaign without path normalization as loading-sensitivity evidence. Historical
`intermediate.json` records the earlier binary and does not regenerate from the
final implementation.
