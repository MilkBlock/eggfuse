# Match-derived owner takeover at completed Run boundaries

The earlier integration manually transferred a source before execution. This
opt-in bounded GPU path derives proposals from actual successful multi-source
queries, retains their minimal evidence through effects, and attempts physical
takeover when the Run completes. No CPU binding reconstruction or intermediate
device readback is used in the compiled test.

## Compile, admit, complete, transfer

`compile_catalog` reads existing query atoms, witness-view records and ordinary
Cell input/effect layouts. For each possible actual witness it compiles the
existing owner projection. Only the first authoritative origin of an input can
reuse that consumer slot. A later witness can have an Eq-equivalent but distinct
stable identity: its field is copied to the consumer's unused tail instead of
being silently replaced. Overwritten input slots are also not reused. Plans
that exceed the physical row width remain unsupported.

At admission, only accepted new Cells retain three integers per atom: plan,
source row and source generation. One additional target generation is stored
per logical row. No second binding array, historical fact graph, reverse
subscriber list or new marker relation is retained. Duplicates do not overwrite
the accepted instance's evidence. These fields stay with the instance across
waiting ticks and run continuations.

At a completed Run boundary, all query/effect/coverage/union checks already
required by the schedule must pass. The prototype additionally waits until no
frozen reader is present. It then uses the shared transfer routine, checking
source and target generations, current physical epochs, actual values, visibility,
settlement, destination space and coverage of **all** aliases of the old owner.
Only after those checks can it move fields, remap projections, increment the
freed physical generation and release a row. Logical keys, tokens, sources and
query routes remain live. Moving an address is not a semantic change and cannot
extend a saturation loop by itself.

The plan is an optional one-shot compression attempt. A failed attempt keeps
the semantic state and clears the hint at a quiescent boundary. A blocked reader
retains the hint for a later boundary. Failures do not authorize retiring facts,
skipping effects or ignoring a query. Transfer success is not activation-owner
retirement; the two concepts remain distinct.

## Evidence

The compiled Metal test starts with four logical slots and only three physical
payload rows. F and G match to a new Cell, whose RHS performs a union and creates
H. After completion the runtime automatically relocates F and G into this Cell's
storage, releases two physical rows, and proceeds through the original schedule.
The next ruleset matches H and admits its Cell using reclaimed storage. No
manual call to transfer is made by the test's scheduled flow.

Two new logical Cells are admitted; final physical occupancy is two rows for four
logical Cells. Successful Run stages are [0,0,1]. Valid slots/roots, stable keys,
generations, lifecycle/effect state, floating tokens and Run change logs agree
with the dense storage reference. This is a closed-family prototype with explicit
coverage premises and seeded numeric weights, not full Eggcc correctness or
learned-completion accuracy. It does not establish a native Run-graph contract.

Additional tests preserve both exact input values 99 and 100 despite their Eq
relationship, postpone hints across missing boundaries and frozen readers,
reject stale source/target generations, and preserve hints on duplicate matches.

## Costs and remaining work

Evidence storage is 12*N*A + 4*N bytes for N logical rows and A maximum query
atoms. Static transfer plans and their record-index tables add storage too;
neither is credited as free. The current fixed-shape sweep attempts up to N*A
locations per boundary, selecting a plan with an exact bounded index. Each
attempt still scans alias projections and uses functional array updates. It
adds no data-dependent GPU control flow but is not a throughput implementation
or a speedup claim. Counters report attempted, released, blocked and copied
fields; released rows are reusable arena capacity, not reduced process RSS.

Admission still requires free storage before takeover, and logical rows/keys
are not reclaimed. A completely full arena cannot bootstrap a new target from
this mechanism alone. Composition that changes required layout width, general
mutable effects, source retirement and exact coverage of later matches remain
separate work. Real full-workload audits, predictor integration and costs are
still outstanding.

The tracked Bake branch now reaches `ee5e75f0`. It removes exhausted suffixes only
when an existing prefix preserves addresses and all reachable later appends;
it also reports expensive component scans. This GPU implementation follows the
settled-boundary and actual-source evidence requirements but does **not** claim
that preserving physical fields proves suffix retirement safe. It keeps those
logical routes intact. A future efficient sweep should use compacted admitted
instances and existing lifecycle events, without rebuilding subscriber lists.

Run test_device_matched_takeover plus the existing admission, ownership, Eq,
query and schedule suites: 159 related tests pass. This change does not modify
the native Cell CPU path.
