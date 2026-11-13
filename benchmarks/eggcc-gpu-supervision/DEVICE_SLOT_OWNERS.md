# Physical slot ownership separate from logical Cell identity

This opt-in GPU mechanism transfers **sealed payload storage**, not logical
activation or proof responsibilities. It is integrated with constructor witness
projection, multi-source query matching and input encoding. New instance admission now reuses the owner arena (see DEVICE_OWNER_ADMISSION.md).
Constructor/copy writers and token refresh now support it (DEVICE_OWNER_EFFECTS.md).
Eq completion and the full stage loop are not yet lowered to it. It is not a complete autonomous Eggcc runtime.

## Representation and actual removed storage obligation

Logical Cells retain keys, generations, visibility, completion and their own
floating tokens. Their slots are read via owner ID, expected owner generation,
and a logical-slot projection. The packed state has no parallel dense `slots`,
`slot_roots`, `slot_valid` or scalar arrays: authoritative payload columns are in
the physical owner bank. Logical tokens stay separate because different template
roles can encode the same physical values differently.

Bake derives which source fields are already inherited by receiver inputs.
Receiver effects that overwrite an input prevent that reuse. Remaining source
fields are assigned unused tail positions beyond the receiver template's slots.
The plan is rejected if the combined payload exceeds the arena row width.
This is a storage layout, not proof that the consumer query/effects happened.
Actual settled instances and value checks are required before applying it.

At a quiescent boundary, the device validates logical and physical generations,
visibility, settlement, exact shared values and all scalar metadata. It checks
that copied destinations are unoccupied and every live alias of the source owner
can be remapped. It then copies only the unshared logical fields into receiver
storage, rewires aliases directly to that owner, and marks the source physical
row free with an incremented generation. There are no parent-owner chains or
per-producer consumer lists. Repeated transfers compose the direct projections.

The source's logical query facts remain available through the receiver's storage.
Receiver logical retirement does not automatically retire the independent physical
owner. This preserves shared readers instead of treating an active-bit change as
permission to discard their facts. Existing effect/visibility/lifecycle decisions
remain authoritative; no mutable effect is skipped. Allowing completed mutable
rules in the layout catalog is only storage preservation of sealed snapshots,
not a mutable-read validity or retirement certificate.

## Evidence and remaining boundary

Compiled Metal tests release a source row, poison/reactivate that physical row to
simulate reuse, then successfully run the existing multi-source query and live
input encoder without host feature readback. Further tests check nonshared field
and scalar metadata copies, exact constructor-view preservation, chained aliases,
padding, occupied tails, stale generations, value mismatches and quiescence.
139 relevant mechanism tests pass. The original poison test establishes that queries no longer depend on the released
row; DEVICE_OWNER_ADMISSION.md adds actual allocation reuse through query admission.

A direct-inheritance-only draft covered zero of the 157 lowered dot-product
Entries: requiring the receiver to already contain every source field misses
composition. The combined layout fits all 157 at width 396, with 475 statically
shared source fields and 721 moved fields. These are **template counts**, not
157 successful runtime transfers or workload memory savings. Runtime checks may
reject instances. Static source capture and ownership proof coverage are distinct.

## Costs charged explicitly

The current compiled plans occupy 373032 bytes. The prototype directory adds
1592 bytes per logical Cell at width 396, plus five bytes per physical row for
live/generation metadata. Fixed-width projection padding is substantial. Moving
721 template fields is work, not a zero-copy claim. Runtime transfer scans live
aliases and uses masked functional bank updates; these may allocate/copy whole
arrays even when logical moved-field counts are small. No speedup is claimed.

Freeing physical rows releases reusable arena capacity; it does not shrink the
allocated bank or establish lower process memory. Logical keys and floating
source tokens remain retained. New instance allocation now uses released capacity. Writers must still respect
shared owners before this becomes a complete takeover.
The quiescence bit is currently a caller-supplied premise, not a concurrent GPU
reader protocol. Unsynchronized writes are outside the supported contract.

## Reproduction and Bake alignment

Run device_slot_owners.py TRACE OUTPUT for static coverage. The committed report
records the held-out dot-product trace hash. Run test_device_slot_owners together
with the witness, query, completion and schedule tests for mechanism checks.

This follows Bake branch 6be77d9c: actual multi-source matches can establish
composition opportunities even without Cursor ancestry; keeping only logical
component counts hides retained source fields and owner fragmentation. Here shared
fields derive from template projections, missing fields remain stored, and owner
metadata/movement are charged. The next required integration is writable owner
storage at the existing GPU Run boundaries, followed by actual
snapshot audits; no full runtime correctness follows from these local tests.
