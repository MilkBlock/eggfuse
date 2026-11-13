# Cross-component provenance is shared, not an ownership tree

This analyzes the four saved `out/cell-physical-regions` final states without
executing another workload. It follows **raw bound native addresses**, verifies
that the producing symbol actually binds that address, and counts receiver
components. Current union roots never establish provenance. Legacy or missing
origins stay unknown. This is not a complete reference graph: queries, indexes,
scalar bindings, external readers and temporary references remain outside it.

| case | components | cross-component bound slots | referenced producers | producers with multiple consumers | exclusive candidates | regions after candidate-only joining |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 492 | 843 | 29 | 18 | 11 | 481 |
| loopfact | 464 | 805 | 35 | 31 | 4 | 460 |
| sum-bits | 1,344 | 3,249 | 160 | 131 | 29 | 1,315 |
| dot-product | 1,308 | 2,977 | 142 | 103 | 39 | 1,269 |

The largest such candidate regions have only 3/2/4/3 components. The highest
fan-outs are 325/271/585/950 receivers from a single-source component. However, a single source can contain many result operations. The largest hub
has 65/47/85/170 referenced native ports, and its most shared single port has
49/54/140/221 receivers. Treating the entire source as one shared value would
therefore overstate a single union's scope. Some ports may also be cheap constants;
fan-out is not proof of expensive work or a worthwhile saturated Cell. Unknown-origin slots number 280/275/545/379. Respectively
14/9/231/103 cross-component raw bindings have changed current roots. Those are
final-state observations, not union event counts or measured repair work.

At port granularity the referenced counts are 119/123/431/446, of which
27/29/152/114 have a single receiver. In sum-bits, 152 single-receiver ports occur
within only 29 exclusively referenced whole components. Thus any more permissive
ownership analysis must work at an operation/port slice, not blindly transfer an
entire producer source. A port is still not a disposable fact: other fields,
indexes, external readers and lifecycle can keep that fact alive.

## Consequence for the next representation

Greedily absorbing uniquely consumed producers cannot be the primary compression
strategy on this frontier. Even the permissive candidate grouping, which ignores
external references and execution ordering, removes only 29 sum-bits component
headers. Copying a shared producer into its receivers would multiply state;
putting all receivers under that producer would create a huge physical restoration
unit. Neither follows from saturated-cell reuse.

The next useful compiler experiment should distinguish **shared boundary inputs**
from **owned completion suffixes**. Shared inputs stay as references to actual
results; the template describes how multiple suffixes consume them. Receiver
operations and slots can only be shared after comparing their actual static
layouts and stage obligations. A large closure should not imply a single physical
owner, and an unexpected union must still restore only affected source state.

This is a selection constraint, not a completed runtime optimization. It does not
prove that any particular region is saturated, can skip RHS publication, or can
retire an old source. Source Run ordering, equality guards, visibility, actual
foreign constructor returns, generations and external readers still require
proof. No runtime bytes or time were saved by this analyzer.

Reproduce:

```sh
python3 benchmarks/cell-bake-owner-merge/closure_frontier.py out/cell-physical-regions benchmarks/cell-bake-owner-merge/closure-frontier.json
python3 -m unittest discover -s benchmarks/cell-bake-owner-merge -p test_closure_frontier.py
```

Six unit tests cover shared fan-out, independently used ports of a shared source,
exclusive chains, cycles, union-root versus
raw-address identity, foreign results and malformed inventories. Input hashes and
Program identities are in the JSON. These are standalone Cell CPU observations,
not native egglog acceptance. The large runtime compression goal remains open.

## Join to actual fact ownership before choosing a takeover

The follow-up joins each single-receiver native port to its existing static
operation incidences and the exported live owned-fact inventory. It never creates
a fact from a template site. Input and result incidences are checked separately;
an operation whose input and output alias still counts as an internal user.

| case | candidate ports | ports with local input uses | ports touching externally retained sources | ports touching lifecycle exceptions | ports without an owned result site | distinct live facts touched |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 27 | 18 | 10 | 8 | 1 | 54 |
| loopfact | 29 | 23 | 6 | 5 | 0 | 60 |
| sum-bits | 152 | 87 | 12 | 64 | 7 | 243 |
| dot-product | 114 | 79 | 27 | 40 | 4 | 279 |

Columns overlap and must not be subtracted independently. An externally retained
source is a conservative obligation, not evidence that every slot is read. The
current snapshot has no hidden facts in these candidate incidences; the analyzer
and tests still account for them. A missing result site can have retired or been
returned from elsewhere; neither case permits fabricating a new local result.
All static sites are checked against the authoritative port fields before joining
facts. There are 21/28/88/58 distinct artifact-local `(shape, port)` plans among
these candidates, but these are not compiled takeover permissions.

Even this entire sum-bits frontier touches only 243 of 2,895 live owned facts.
Removing all of them would be illegal, and cannot serve as the main explanation
for a 70% overall memory reduction. This constrains the previous recommendation:
port-sized proof/restoration is necessary for correctness, but expanding only
single-consumer takeover is too narrow. Large compression must also cover the
shared-producer majority, keeping one authoritative fact identity and projecting
its internal relations from a template rather than copying it into receivers.

The next runtime design must combine static operation coverage with dynamic
membership and lifecycle exceptions. It must keep shared boundary references,
not equate "one receiver" with "one owner", and remove a current storage or index
path within proven coverage. Adding the candidate plan alone would not do that.
Ten analyzer tests now cover these obligations. This remains saved-trace evidence;
there is no new runtime-memory or performance claim.
