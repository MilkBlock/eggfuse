# Reuse the current constructor comparison at immediate admission

A multi-target compiled route already reads candidate fields and compares each
input against the current RHS arguments. Previously, when static wiring could
not prove the key, the route returned an unproved address. `construct_inner`
then built the same key and repeated its equality check in the prepared-witness
lookup. This duplicated work even after a successful current-value comparison.

The route now distinguishes unchecked, compiler-proved, and immediately compared
key evidence. Both checked cases enter the existing result-admission helper.
Successful admission returns the actual stored result without rebuilding the key
or issuing the prepared-key comparison. Unchecked routes and failed admission
retain the same full current-key lookup. No witness history, result copy or
binding registry is added.

The compared evidence is ephemeral: there is no mutation, suspension or worker
handoff between route comparison and the following admission. It must never be
retained for a later stage. The shared helper still rejects dirty constructor
tables, receipt forwarding, dead/non-owned/hidden facts and wrong table identity.
Compiler proofs retain their own distinct counter; runtime comparisons do not
masquerade as static proofs.

`constructor_cell_route_compared_admissions` counts successful immediate reuse;
`constructor_cell_route_recheck_fields_avoided` counts only its skipped second
field comparison. Existing alternative-check counters still charge the first
comparison and unsuccessful candidates. These counts do not establish net speedup
or expanded Bake coverage, and this change claims no egraph memory reduction.

All 56 ownership integration tests pass. The new scalar fixture copies an input
between different constructor fields, so shared Eq wiring alone cannot prove
that scalar relationship. A wrong same-operator route is tried before the correct
one. Final states, source snapshots and binding audits match the control; the
compared path admits a result and performs fewer prepared-key field comparisons
than the single-target control. That comparison concerns the prepared phase,
not the total work of candidate selection. Existing tests retain hide/delete,
union, invalid-code and actual-result checks. The default runtime also compiles.

This local deletion follows the user's preference for a small check before the
next optimization. No new workload timing campaign or native semantic claim is
made. The original witness coverage remains small; this is not evidence of the
requested large compression or a complete saturated-cell RHS takeover.
