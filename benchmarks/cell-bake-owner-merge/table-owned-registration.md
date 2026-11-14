# Table-owned constructor continuation during admission

The preceding actual Raytrace execution registered 190,981 ownership rows on
workers, but only 6,288 were registered directly by the producer continuation.
The other rows still returned to source and entered a second worker dispatch.
The whole constructor directory had to leave Graph, so this fused path could
not accompany ongoing source admission. That is an ownership boundary wider
than the Cell's typed operations require.

The existing constructor instruction plans already identify all written tables,
the terminal cone, allowed aliases and actual result slots. No additional Bake
catalog or runtime fact representation is needed to use that information.
Canonical hash storage is now partitioned by authoritative table, preserving
ordered exact-key candidates within each table. Workers lease only the written
table indexes, member sets and deferred changes. Unrelated tables stay attached
to Graph. A leased index is explicitly unavailable; neither an empty bucket nor
the nullary member shortcut may misinterpret it as proof of absence.

Canonical ownership's background Cell producer can now continue straight from
construction into physical registration, using the existing completion slot and
source-ordered directory owner. Source acceptance consumes the returned original
fact slots and publication certificate. This deletes the second registration
dispatch, its flattened row input and registration-event queue for the covered
region. Source admission can continue through pure calculations, valid prepared
witnesses and operations on other tables. An unresolved access to a leased table
waits for that table owner to return. No new per-producer consumer list is built.

The shared constructor directory still has one mutating owner at a time within
each continued wave. This does not make arbitrary same-table writes concurrent.
Port binding and component selection remain source ordered, and later waves can
still wait on the existing bounded queue. The change replaces a whole-directory
restriction with explicit table ownership; it does not claim full utilization.

Open-admission takeover requires canonical ownership, original empty fact frames,
covered operations, pure terminal constructor tails and valid parent order. Old
fact prefixes must remain readable during admission. Unit tails and other storage
backends retain their existing path. Actual foreign results are checked at source
adoption before ownership binding; source errors restore every original owner,
then invalidate only the unadopted suffix. Source Run visibility, equality epochs,
mutable effects and all exact key checks outside existing proofs remain live.

The cost includes per-table index headers, directory fragments and table wait
checks. Existing storage accounting includes the new headers. New counters record
background fused regions/Cells and encounters with a leased table; they measure
coverage and boundary encounters, not CPU utilization or time spent waiting.
The full-workload comparison must charge them together with event/registry bytes,
source work and inference time.

Validation includes a deliberately paused producer: while it retains one table,
source constructs and reads another table before that producer is released.
Only one earlier Cell is then adopted, all later rows are invalidated, and a
subsequent cross-input union/repair retains correct lookup. Equal hash values
in different tables also retain independent order and retirement. Existing
ownership integration tests require the new background path to run, while still
comparing every fixture Run graph, ordered bindings, foreign returns, learned
composition choices, deletion/recreation and first-error behavior.

Job 469 passes 220 runtime tests and 119 compiler/runtime integration tests.
Job 470 passes the final 220 runtime tests, 76 ownership tests with storage
instrumentation, 100 default-backend runtime tests and a no-default-feature
compile. Complete workload checks follow separately. Reproduce
workload validation with `owner_workers.py`, reusing the verified `62c5f984`
control. Time the entire original control, the entire `5bb451e3` registration
candidate and the entire current candidate under one lease with
`prepared_timing.py --include-ordinary --previous-experiment PREVIOUS`.
