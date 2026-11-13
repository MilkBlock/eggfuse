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
