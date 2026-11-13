# Skip settled owner admission before building candidate groups

Completed sources have no ordinary Cell record; restoration recreates one. A
component with no ordinary source therefore cannot contribute a new transfer or
suffix at the current idle Run boundary. The previous implementation nevertheless
built its candidate Vec, collected completed-frame addresses, and only then
noticed that every candidate was already transferred.

Admission now checks for an ordinary source before allocating that Vec. It uses
the existing arena directory, adds no per-component pending flag or reverse
index, and automatically reopens after a new source or scalar restoration.
Incomplete or otherwise ineligible ordinary sources still take the full existing
checks. This moves an existing no-work decision earlier; it does not discharge
any new equality, visibility, retirement or query obligation.

Two counters distinguish cost and result: `shared_owner_admission_source_probes`
counts the new short-circuit source probes, and
`shared_owner_settled_components_skipped` counts components excluded before
candidate collection. The latter is not a saved-fact or skipped-RHS count. Active
components pay the extra preflight; no latency benefit is asserted without a
matched measurement.

All 55 ownership integration tests pass. The existing three-Run extension test
still absorbs 2/1/1 sources (serial and two-worker paths), then checks that an idle
admission examines its four source identities, skips one component and changes
no retained storage. Existing scalar-retirement and later-reading tests remain
part of the same suite. No new performance campaign was run for this local
maintenance deletion; no additional retained-memory reduction is claimed.
