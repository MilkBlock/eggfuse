# Allocate new GPU Cells from released physical owners

This extends sealed owner takeover into the existing admission path. It is a
bounded device mechanism, not complete Eggcc runtime execution or performance
evidence. No new model, backpropagation or accuracy claim is involved.

## Atomic capacity and allocation

Logical identity capacity and physical payload capacity are distinct. Admission
first performs its existing exact key dedup, query witness/lifetime validation
and winner order. It additionally checks physical owners and limits acceptance
to both available logical rows and unreferenced free physical rows. A physical
row with an exhausted generation is unavailable rather than wrapping.

Accepted proposals get a physical row in deterministic prefix order. The same
admission writes their exact slots, roots, validity and scalar columns directly
into the owner bank, installs a projection/owner generation, and writes the
logical key and floating token. It does not rebuild a parallel dense logical-slot
array. Missing payload columns or incompatible layouts fail explicitly.

Both single-source Entry projection and multi-source constructor joins read
owner-backed fields and scalar columns. Source owner generations are checked
again at commit. Logical key retention and generation semantics are unchanged;
repeated matches do not consume another owner row. `owner_capacity` distinguishes
physical exhaustion and participates in the existing attention/closure boundary.
Allocation does not prove effect completion: a consumer with pending union stays
unsettled at effect_pc zero.

## Compiled GPU integration evidence

A single Metal function performs sealed transfer, actual multi-source matching,
live feature encoding, ridge arithmetic, and admission. Two physical rows hold
three logical Cells: source row 0 moves to owner 1, then the new matched Cell gets
released owner 0 with a new physical generation. The original source still reads
owner 1 correctly. A second matching round admits no duplicate. This uses seeded
model coefficients to test execution plumbing, not trained semantic accuracy.

The identical state without transfer has a free logical row but no free physical
owner. It admits nothing and marks physical capacity, leaving payloads unchanged.
Other tests cover stale owners, exhausted generation, single-source scalar column
preservation, and retaining unfinished RHS obligations. Six new tests and 145
related tests pass. There is no intermediate GPU state readback in the compiled
integration test.

## Costs and outstanding work

Fixed arena allocation does not shrink allocated memory. Free-owner discovery
currently compares logical owner references with physical rows; placement uses
dense candidate/row masks and functional array updates. These are extra costs,
not a speed improvement. The prior directory and template costs still apply.
Constructor/copy operations and token refresh now support new pending instances
(DEVICE_OWNER_EFFECTS.md); general RHS operations remain incomplete.
Owner Eq refresh and stage-loop wiring are now locally tested (DEVICE_OWNER_UNION.md).
Automatic takeover scheduling, lifecycle-aware reclamation and whole-workload
audits remain required before native semantic acceptance.

The Bake reference advanced to 6dcbd782. It measured only 135 admitted joins out
of a much larger proposed catalog, with 1947 guard exits associated with queued
unions; larger catalogs worsened total memory. This change does not infer safety
from candidate counts, clear a pending union, or relax a repair/frozen-read guard.
Physical capacity reuse is verified separately from effect completion and union
compatibility. Those remaining obligations must be proven at actual Run boundaries.
