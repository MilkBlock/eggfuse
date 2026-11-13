# Bounded multi-source constructor matching

`device_query_join` removes the single-source restriction for supported immutable
constructor queries. It projects ephemeral facts from current Cell slots, joins
atoms by current Eq roots (and exact non-Eq field keys), checks repeated variables
inside each atom, and returns actual slot identities separately from roots.
The successful binding retains each atom's source row, static occurrence index
and source generation, even when that atom introduces no new variable. Bound
fields retain their own source row/slot addresses for direct scalar projection.
No persistent fact graph or per-producer consumer list is introduced.

`match_inputs` feeds these device-produced bindings directly into existing seed
and neighborhood encoding. Dynamic scalar feature columns use the same source
addresses as exact values. No CPU successful-binding list or intermediate host
feature encoding is required in the integrated GPU test. This is not yet wired
into general ridge proposal admission or complete Run coverage.

This is an exact bounded fallback, not neural-throughput matching. Each atom
forms a dense prefix-binding by witness candidate mask, then sorts indices for
deterministic compaction. Candidate lanes are charged explicitly. Capacity loss
at any prefix keeps an overflow obligation even if later filtering would shrink
the result; final deduplication cannot undo that information loss. Repeated
physical witnesses can therefore cause conservative overflow. Missing witness
coverage or unsettled Eq also prevents complete enumeration. Partial candidates
may be returned but do not authorize a negative query answer or stage closure.

Only slot-argument immutable constructor atoms are supported. Unsupported guards,
literals and mutable reads are recorded by compilation and cannot be silently
omitted at runtime. Query-only Cell facts use the existing visibility/retirement
contract of witness projection. Inputs must belong to one fixed matching
snapshot with valid template/type and exact scalar-key metadata; later use must
revalidate the retained witnesses and generations under the runtime lifecycle.
These results do not by themselves establish delta ownership or native encounter
order. Initial graph import and complete external boundary coverage remain live.

## Evidence

90 mechanism tests pass. The GPU fixture joins F(x,y) from one Cell with G(y,z)
from another, using equal roots but distinct actual y identities. The resulting
actual fields, roots and both source generations are checked. Other cases test
mismatch, hidden facts, missing external coverage, repeated variables, overflow,
unsupported guards and direct GPU input-feature encoding.

Static dot-product compilation supports 382 of 548 rule query shapes; 314 of
these have multiple atoms, with at most 10 atoms. Reasons on unsupported rules
are 139 non-constructor atoms, 111 unbound query-slot cases and 52 literal-atom
cases; reasons overlap. Shared static witness layouts occupy 82,792 bytes across
170 table/arity layouts. These are compiler counts, not actual match coverage or
speed. `complete_ruleset_authorized` and ownership-transfer authorization remain
false in `query-join-coverage.json`.

Reproduce static coverage with `device_query_join.py TRACE OUTPUT`. A shared
compile-time view cache avoids retaining a duplicate layout for each query.
The new optional field projection on `device_witness_views.project` is used only
by this matcher; existing constructor/Eq consumers keep their original interface.

Reference Bake tip `20c85cfa` preserves static wiring and source-sized lifecycle
slices while pooling short compositions. Its negligible second-round saving
shows why physical batching alone is not a full takeover. Here, returning
multi-source matches is likewise not ownership transfer: retaining and removing
source responsibilities under a proved composed Cell remains unfinished.
No native runtime, prediction-accuracy or whole-workload speed claim is made.

## Joint matches through ridge and admission

`device_join_transition` now compiles source/consumer role coefficient banks for
query input ports, selects them from matched witness occurrences, pools current
source tokens and invokes the existing ridge feature map. Projected scalar
features and exact values share the same field provenance. The resulting slots,
roots and token go directly into the common admission path. Query overflow and
incomplete views stay visible even when some proven partial matches are admitted.

Joint proposals retain all atom witnesses and their generations. Admission
checks every witness's presence, visibility, settlement and token freshness;
it does not require a shared reader to own activation. A placeholder source of
-1 explicitly avoids inventing one primary owner. Multi-source proposals never
transfer activation, even if a caller incorrectly sets the old transfer flag.
They also skip the old single-primary competition scan. Actual ownership
transfer still requires a separate composed-Cell proof and lifecycle takeover.

`run_round` jointly admits multiple such query blocks with padded witness masks.
The nested scheduled runtime accepts this query kernel while preserving its
one-query-snapshot-per-Run protocol and current external/Eq coverage gates.
Unknown coverage defaults to false. Unsupported queries are not silently
installed, and this does not establish complete residual enumeration or delta
ownership for a real ruleset.

94 mechanism tests pass. GPU tests cover multi-source matching, encoding, ridge
and admission in one call; actual IDs/roots remain distinct. Changing a secondary
witness's generation, visibility, freshness or settlement blocks admission. A
nested local runtime fixture executes a constructor from the joined match and
reports completed-Run changes [true, false]. Shared input sources remain live;
no transfer is credited. Test weights are synthetic, not a new prediction-rate
result. The static role scheme chooses the first binding witness per port; its
provider distribution still needs evaluation against the frozen trained model.

Remaining limits include dense join/compaction work, coefficient-bank residency,
full constructor-view coverage, witness retirement after admission, exact
original encounter/delta semantics and semantic key deduplication when different
actual identities share one Eq class across Runs. Existing exact integer-key
admission is not a proof that all such aliases are globally deduplicated. The
integrated fixture has sufficient capacity and explicitly complete local query
coverage; it is not full Eggcc acceptance or a performance result.

Reference Bake tip remains `20c85cfa`. The change reuses existing slots and
admission rather than introducing another runtime fact graph, but it still
retains source responsibilities and does not claim full ownership completion.
