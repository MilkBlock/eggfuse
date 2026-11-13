# Component-level boundary routing is not a large state takeover

This audit reuses the four saved `source-cell-memory.json` states. It does not
run workloads or measure speed. The active runtime is unchanged. The candidate
representation would replace a root's individual symbolic routes with component
IDs, then recover relevant symbols through shared static operator wiring.

The analyzer reconstructs the runtime's native-port exemption from the encoded
source/slot address and existing shape port map. Its external-route count must
match `ownership_query_work.boundary_live` exactly. For every saved external
root/component pair and every operator in that concrete component, it checks
that static candidate enumeration followed by root and native-port tests returns
exactly the original symbolic routes. Missing origin storage is not confused
with missing composition wiring. Five tests cover native exclusion, an absent
native origin, unbound symbols, inconsistent counters and duplicate sources.

| case | external signal records | root/component records | static symbol checks | returned routes | raw payload difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 1,282 | 1,164 | 11,271 | 1,701 | 15,856 B |
| loopfact | 1,231 | 1,119 | 10,278 | 1,610 | 15,220 B |
| sum-bits | 4,699 | 3,965 | 50,560 | 6,350 | 59,324 B |
| dot-product | 4,032 | 3,508 | 50,988 | 5,440 | 50,480 B |

Raw payload compares the current 16-byte Signal with a hypothetical 4-byte
component ID. It excludes root bucket/tree allocation, spare capacity, static
plan storage, and maintenance. It is neither a heap saving nor an upper bound on
every possible implementation. The proposed registry still has 84.4% of the
sum-bits record count. The entire existing 215,144-byte boundary allocation must
not be credited as removed.

Candidate checks are exhaustive per saved root/component/operator combination,
not weighted by actual query frequency. For sum-bits, 6,051 of 11,627 operator
cases return nothing. Static wiring alone still leaves substantial root filtering.
The check totals cannot establish a runtime slowdown, but they prevent treating
this change as free direct addressing. Concrete static plans require `(shape,
frame_codes)`, since port shape alone forgets operator identity; the sum-bits
snapshot has 314 such plans and 3,602 table/symbol positions.

This is a proof of final-state membership equivalence for this projection only.
It does not establish source ordering, query-class closure under new suffixes,
concurrent snapshot lifetime, or union dispatch correctness. In particular, after
updating union-find, a scan by the new root cannot distinguish old-from membership
from pre-existing old-to membership. A runtime implementation needs old-root
routing or a proven safe superset, and must charge that extra completion work.

## Decision

Do not implement a generic component scan as the main compression mechanism.
It mostly changes the representation of still-required external relations.
A useful cross-stage takeover must remove repeated source/fact state and its
routing together under a compiled completion contract. Merely dropping the
symbol from each boundary record does not achieve that contract. Unknown external
relations remain explicit; actual root equality alone does not prove two future
continuations interchangeable. These results do not meet the 30%-of-original
Graph objective or prove additional RHS skips.

Reproduce through the shared compute queue:

```sh
python3 -m unittest discover -s benchmarks/cell-bake-owner-merge -p test_boundary_regions.py
python3 benchmarks/cell-bake-owner-merge/boundary_regions.py out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/boundary-regions.json
```

The JSON records hashes of the exact saved inputs and their Program IDs. No new
native egglog semantic acceptance or performance campaign is claimed.
