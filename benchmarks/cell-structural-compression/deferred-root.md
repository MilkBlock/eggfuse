# Delay query-only root history until publication wins

Bake already identifies the root's demanded captures. When exactly one query
witness is needed for one retained stage, keep its actual reference and source
Run inline in the existing pending Root variant. Construct the Cursor/history
owner only when an Entry selects that publication. Losing publications need no
history allocation or root owner. The new fields fit inside the existing Cursor
variant; a size regression test guards this. No reverse index or new fact map is
introduced. Training retains its original eager ancestry recording.

The root is still captured after successful RHS execution. At promotion its
original Run is restored and ordinary receipt forwarding/lifetime checks run.
Multiple publications promote the same completion only once. Other capture
shapes keep their ordinary path. The dispatch obtains the root plan once; it
does not add a failed generic probe in front of the old root lookup.

Actual standalone runtime, same full-history-admission artifact:

- 146 deferred query captures, 65 winning promotions, 81 discarded captures.
- History allocations: 452 -> 371; capture reads and result-slot writes:
  216 -> 135 each. The 146 new pending capture writes and probes are reported
  separately, rather than hidden in a saved-work total.
- All 1,428 saved Run graphs and ordered RHS/write/resume hashes match.
- Saved-export semantic acceptance: pass.
- 144 runtime tests and 20 ripsat tests pass, including competing root
  publications and a pending-state size guard.

This removes unnecessary history owners, not egraph facts. Final retained
history storage is unchanged. No time, peak-memory or whole-egraph compression
claim is made. The candidate artifact remains experimental; the change does not
make the previously reported full batch profitable by itself.

Results are in deferred-root-results.json. Three introduced counters have an
explicit zero baseline because the previous runtime did not implement this
path; all other work counters are compared exactly. The audited execution used
the same deferred mechanism before the helper was refactored to avoid a second
root-plan lookup; the final helper is covered by the full test suites. No timing
comparison is inferred from that refactor.
