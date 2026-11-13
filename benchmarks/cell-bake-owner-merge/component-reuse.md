# Reuse retired component storage across settled stages

The current catalog's saved execution created 1,601 logical components and
retired 237, but the slot directory retained all 1,601 positions. Old source IDs
and FactRefs must remain stable; internal component positions need not remain
reserved after all their routes and facts retire.

Retirement now appends the empty component position to a quarantine. Only a
settled ownership boundary promotes quarantined positions to reusable positions:
no pending unions, dirty work, active RHS, ownership dispatch, active Entry or
frozen component readers may remain. A subsequent birth reuses a promoted
position, with zero live facts and a fresh source identity. Cached witness
selection is cleared on reuse. Source IDs themselves are never reused.

The worklist is one vector with a ready prefix and quarantined suffix. New
retirements cannot be consumed before the next safe boundary. Both whole
component retirement and the discarded side of a checked multi-source join
enter this path. Surviving source addresses, symbol layouts, slots and fact
arrays are not rewritten by the allocator. Shared read snapshots keep their
old contents until readers finish, as before.
The prefix-retirement queue already stores stable source IDs: a stale event
resolves through the source directory, so it cannot target a new occupant just
because an internal component position was reused.

Component and lifetime directories also use bounded growth (up to 128 spare
positions) instead of doubling indefinitely. This is charged as a memory/work
tradeoff: lifetime-directory growth events increase from 10 to 18. Component
index order changes, so existing source-based validity checks remain essential.

## Actual runtime result

The same 108-extension Program, storage flags and source workload are used.
These are standalone Cell runtime requested-heap measurements, not timing,
RSS or upstream egglog measurements.

| Quantity | Before | After |
| --- | ---: | ---: |
| Graph bytes | 1,297,491 | 1,256,075 |
| Component positions | 1,601 | 1,364 |
| Reused positions | 0 | 237 |
| Component directory and signal storage bytes | 264,064 | 228,224 |
| Lifetime directory bytes | 16,384 | 11,264 |
| Quarantine/reuse vector bytes | 0 | 128 |
| Execution/takeover process heap peak | 113,470,380 | 113,429,158 |
| Resident Program bytes | 107,599,014 | 107,599,014 |

Cells increase by 376 bytes and boundary storage falls by 960 bytes; both are
included in the net **41,416-byte** Graph reduction. Dispatch comparisons rise
from 3,525 to 3,542. No speedup is inferred from the smaller directory. Maximum
extra takeover allocation remains 19,568 bytes.

After aligning by stable source IDs, the logical components (including shapes,
ports, roots, native codes and live facts) and source lifecycles are identical.
The final exported graph and full Run sequence are identical. This reclaims
historical component positions; it does not remove live facts or prove that
RHS effects can be skipped. Graph memory is still 62,264 bytes above the
historical 30% threshold, whose denominator is a working-tree observation.

The library test exercises retirement while a read snapshot exists, verifies
that the snapshot sees the old component, and prevents reuse before both thaw
and a settled boundary. A stable-port regression reuses the same internal
position for a new source and checks that old source ports remain expired.
The integration fixture repeatedly creates and deletes constructor facts across
source Runs and requires actual slot reuse. Complete statuses and artifact
hashes are recorded in `component-reuse.json`.

Job 377 passes all 217 runtime library and 69 ownership tests. Job 380 passes
all 882 Run graphs and ordered audits against the saved control checks, all
reviewed native final-state comparisons, and the no-default-features check.
With parallel publication, Cell absorption and view ports enabled, all 69
ownership, 19 compiler and 13 witness-source tests also pass.

Reproduction uses the same storage commands as `source-routing.md`, under the
shared compute queue. Frozen artifacts are in `out/cell-component-reuse`.

Further learning must follow the actual selected storage/completion mode. The
existing generic catalog observer does not enable completed-owner takeover or
prefix retirement, so its equivalent final graph alone does not establish that
it saw the same intermediate Cell layouts. A future observer update must keep
that distinction explicit when selecting cross-stage closures.
