# Enumerating structural interfaces instead of sampling them

`enumerate_cell_interactions.py RECIPE OUTPUT --rules 0,1,2 --max-classes 10`
uses rule definitions only. For each ordered producer/consumer pair it enumerates
every mapping of consumer query atoms to same-table producer facts or explicit
external boundary facts, with at least one producer connection. Producer facts
include inherited matched inputs and completed constructor effects. Copy aliases
and completed unions constrain ports before enumeration. No sampled history or
labels select the mappings.

For each mapping, restricted-growth strings enumerate all typed equivalence
partitions of the remaining port classes, including i64 equality classes.
Different literal values cannot merge. Constructor congruence closes the resulting
facts. Snapshots are deduplicated within a wiring; different derivations remain
separate records. Eq identity renaming uses deterministic first occurrence, not
a complete arbitrary-graph isomorphism algorithm. Scalar representatives preserve
equality and declared literals, not arithmetic or ordering behavior.

The three real Eggcc context rules produce 48 wirings, 1,480 typed partition
combinations and 792 per-wiring representatives. No wiring exceeds the selected
bound of 10 classes. A trial bound of 7 excluded four wirings; that report was
explicitly incomplete. See `enumerated-two-cell-results.json` for the successful
run, per-pair counts and artifact hashes. Three tests check Bell-number partition
counts, exhaustive single-atom wiring, constructor closure, literal contradictions
and visible budget exclusions.

These are completed-producer boundary inputs, **not pre-RHS producer states**.
They deliberately include external facts required by the consumer. The tool
has not proved source-program reachability, schedule legality, higher-arity
producer combinations, iterative interaction closure or ownership retirement.
`within_bound_complete` means no *two-Cell wiring* was skipped by the class cap;
it does not claim the whole Cell family is closed. This round generated inputs,
not saturated labels or a trained model. Native Eggfuse execution/label capture
must follow, preserving the provenance of each representative. No speed claim.
