# Source marker result handoff

Baseline: `7725da71`. This experiment changes generated `.egg`, then lowers it
through the ordinary typed frontend to the standalone Cell CPU. Native egglog
is a semantic reference, not the runtime whose speed is claimed.

The last sum-bits audit still performed 19,222 key lookups; fixing runtime
receipt addresses did not remove any. Source markers already carry complete
correlated constructor tuples, including constructor outputs. Replacing a LHS
fragment with a marker hides those constructor facts from RHS alias discovery.
Re-emitting `(F a)` on the consumer RHS therefore discards a result already
present in the marker. Producer marker arguments can also reconstruct nested
RHS expressions instead of forwarding their actual returned values.

The source pass will replace proven permanent-constructor expressions with
their bound values and capture needed producer results at their original
evaluation position. It introduces no physical Cell addresses or receipt
history. The marker tuple supplies bindings and constructor results; its table
and consumer rule statically identify the residual continuation. Consumers
keep their original residual LHS and Run membership. No historical application
receipt is interpreted as a permanent completed rule.

Proof obligations: constructor identity and all arguments must agree; only
positive permanent constructor facts qualify. Tables that can be deleted or
subsumed are excluded. Mutable reads and primitive evaluations retain their
position. New bindings must be hygienic, and each capture must dominate its
uses. Eq values remain ordinary egglog values, never physical row addresses.
Unions continue to canonicalize marker tuples. Completion must still discover
initial and newly union-enabled bindings not published by a producer.

Validate the emitted `.egg` with native egglog and compare standalone visible
states and original schedule boundaries. Measure actual lookup, publication,
slot and allocation differences, not the number of syntactic substitutions.
The unchanged frozen catalogs are bound to the old recipe, so new source
artifacts cannot silently inherit them. Keep a selectable legacy emitter for
paired source experiments and reproducibility.
