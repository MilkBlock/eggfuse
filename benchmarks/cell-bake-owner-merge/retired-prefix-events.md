# Trigger prefix retirement from actual source retirement

The preceding prefix experiment removed 129 exhausted suffix frames, but
visited 1,074,658 component slots at Run boundaries. The saved execution proves
that this is disproportionate maintenance for the admitted coverage.

The first explicit prefix compaction performs one bootstrap scan and enables a
coordinator worklist. Subsequently, `retire_empty` records an ID only after a
source record really retires and still has an ownership frame. At the settled
boundary, the existing frame directory resolves these source IDs to their
current components. This matters when a join moves a source after the event.
Duplicate components are processed once. Pending repair, active RHS execution
and frozen readers still prohibit shape changes.

This adds an opt-in temporary vector of retired source IDs, not a consumer list,
binding copy or per-instance dependency index. Candidate checks rejected by the
native-address guard retain a retired source ID for retry: later union can
clear that obligation without a second deletion. Other candidates are consumed.
The temporary vector releases excess storage after each pass; its allocation
is included in the Graph observer under `ownership.retired_prefix_sources`.
Disabled execution does not perform a frame lookup for this mechanism.

On the same selected Program, visits fall from **1,074,658 to 263**: 129 initial
bootstrap slots and 134 actual retirement events. All 129 suffix retirements,
the final ownership inventory, Run sequence and final export are unchanged.
Graph requested heap stays at 1,392,459 bytes; resident Program stays at
107,450,586. Final worklist heap is zero. Maximum extra takeover allocation is
11,376 bytes. This measures work and requested heap in the actual standalone
Cell runtime; it is not a wall-clock speedup measurement or upstream egglog.

The regression fixture now requires real retirement events and verifies that
three idle boundary calls perform no further component scans. Reproduction uses
the same `--retired-prefixes` commands as `retired-prefixes.md`. Frozen artifacts
are under `out/cell-retired-prefix-events`; exact hashes and validation status
are in `retired-prefix-events.json`. The Graph 30% target and saturated RHS
skipping remain unfinished; this removes the scanning overhead of the existing
takeover rather than claiming additional compression.
