# Canonical ownership uses the worker constructor registry

The preceding worker-birth experiment moved 329,913 Raytrace constructor
operations to workers and eliminated 358,328 counted queries, but inference
regressed 8.98%. Source adoption still installed every ownership row. The
existing catalog already supplies operation coverage, component wiring and
actual-result demands; more witness recipes do not remove that backend gap.

This change admits canonical ownership to the existing terminal constructor
registry. Workers install original fact slots, hash buckets, table members and
deferred change entries. Source acceptance binds the compiled ownership ports
and advances publication versions; it no longer repeats `activate_fields` for
these rows. Constructor-only ownership regions do not lease or execute a reverse
subscription owner. Regions with Unit rows retain their required subscriptions.

The compiler must cover every constructor operation. Existing admission still
requires settled ownership keys, a terminal effect region, valid parent order
and the original Run/error fences. Rows waiting for source acceptance remain
unowned and have no port bindings. An unaccepted suffix removes physical indexes
and deferred changes without touching ownership relations. Actual foreign
results reach the source Entry before the first new row binds its ports.

There are two existing execution forms. A closed terminal producer region keeps
its directory owner through construction and registration. An already-completed
region registers through the independent worker owner. Neither changes the
source admission/visibility boundary or establishes independent concurrent
ownership of the entire graph. Port binding and component selection remain
ordered source work; this is not a claim of full worker utilization.

Source port binding borrows existing row fields. The independent path retains a
shared reference and range into its existing registration input; the fused path
retains its original Piece rows until acceptance. It does not copy bindings or
introduce a runtime consumer graph. These longer-lived fragments and enlarged
publication records still have costs. Existing registry/frame byte counters
charge their structures; the byte counters are cumulative, not peak heap.
`constructor_registry_owned_rows` and `constructor_registry_owned_fragments`
measure accepted ownership coverage, not extra committed mutations or speedup.

Job 448 passes 218 runtime unit tests and 119 compiler/runtime integration tests.
Both independent and fused registry tests compare all source acceptance prefixes
with ordinary installation, then apply union/repair after suffix invalidation.
They require identical graphs, ownership reports and versions, and no constructor
reverse edges in ownership mode. Integration checks retain actual foreign returns,
composed Entries, every fixture Run graph, deletion/recreation and first-error
ordering. Full-workload validation and timing are separate from these checks.
Job 455 additionally passes all 76 ownership tests with storage instrumentation
and the no-default-feature runtime compile.

Reproduce the workload check with `owner_workers.py`, retaining the original
`62c5f984` control and reusing its already-validated exports. Then run
`prepared_timing.py --include-ordinary --previous-experiment PREVIOUS` under one
timing lease: the entire original control, the entire `cf65e4b1` worker-birth
candidate, and the entire current candidate. Never interleave individual samples.

## Full-workload result and admission

Implementation `5bb451e3` passes job 457's complete workload check. Native
sum-bits choice acceptance is `pass`. The original sum-bits and Raytrace Programs
preserve final state, all 1,428 / 16,883 Run summaries, and logical effect counts.
The unchanged 408-recipe sum-bits catalog also preserves state, Run summaries
and effects. Raytrace and the learned catalog are differential checks, not native
proofs or full-program per-Run graph checks. Original control exports are reused
only after checking their source, binary and input identities.

Job 459 times the actual standalone Cell runtime with four workers and canonical
ownership. All 114 process-boundary guards pass. Each case has one warmup, then
five sum-bits samples or three Raytrace samples. Entire lanes run in order.

| Inference median | Original `62c5f984` | Births `cf65e4b1` | Registration `5bb451e3` | vs. births |
| --- | ---: | ---: | ---: | ---: |
| Sum-bits | 21.449 ms | 26.300 ms | 27.647 ms | +5.12% |
| Raytrace | 4.533512 s | 4.843889 s | 4.888871 s | +0.93% |
| Existing sum-bits catalog | 21.928 ms | 26.823 ms | 28.238 ms | +5.28% |

These are fresh comparisons within one lease; absolute times from the preceding
experiment are not reused. Versus the original control, current inference is
28.90%, 7.84% and 28.78% slower respectively. **Speed admission fails.** Keep the
branch experimental and unmerged. The small Raytrace difference alone is not a
precise estimate of a stable slowdown, but this run establishes no speedup.

Raytrace registers 190,981 ownership rows on workers, 54.1% of its 352,977 local
births and 23.3% of all 820,311 owned births. Only 6,288 rows use fused producer
registration. The remainder still goes through a second registration handoff.
Registry and frame structures charge 15,345,112 + 14,821,144 cumulative bytes;
108,979 original frames return to source acceptance. These are not peak heap
measurements. Port binding still creates 2,151,665 signal bindings. Queries stay
essentially unchanged from worker births (3,974,644 to 3,974,638); logical effects
remain exactly equal. Minor task/query-count changes can follow event grouping.

The source/worker boundary was moved, but the dominant short-job population was
not removed: 216,390 jobs still carry about 329,921 worker constructor operations.
The coverage result therefore does not support expanding dispatch merely to
raise a row counter. The next opportunity is to remove the second handoff and
let the same compiled component owner perform construction, port binding and
registration. Its ownership domains must permit source admission to continue
without borrowing the whole constructor directory. Until that proof exists,
actual-result identity, source error order, cross-component equality and legal
Run publication remain live obligations. This experiment does not isolate one
overhead as the sole cause of the measured result.

Exact samples, hashes, coverage and validation are indexed in
`owned-worker-registration.json`. A separate storage incident interrupted queued
work before it started. Job 454 copied and SHA-256-verified 1,613 historical
artifact files to the external disk, retained their original paths as symlinks,
and released their old physical storage before validation/timing. No interrupted
job or observer timeout is counted as a completed measurement.
