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

## Native execution and final boundary labels

`collect_enumerated_native.py ENUMERATION OUTPUT COMPILER OBSERVER` replays each
representative's wiring and restricted-growth partitions before emitting source.
`synthetic_cell_inputs.validate` now accepts this explicit enumeration provenance
alongside the existing random generator. Edited snapshots, invalid indices,
partitions or all-external wiring are rejected. Distinct routes with identical
boundary snapshots are archived together and executed once.

The 507 distinct snapshots were all attempted: 487 passed native graph, ordered
binding and control audits; 20 exceeded the two-second compiler limit. Observer
execution was limited to one second per case. These timeouts are **unresolved**,
not proofs of divergence or saturation. Some compile traces keep producing new
facts, so a finite interface catalog alone does not prove finite unrestricted
completion. No training or inference accuracy claim is made.

`enumerated_boundary_labels.py CAPTURE_DIRECTORY OUTPUT.jsonl` checks archive,
trace and input identities and obtains program-final Eq partitions from the
private seed anchors. It labels the initial boundary ports, including equality
acquired in later Runs, without treating immediate post-Run targets as final.
All 487 successful cases were labeled; their summed input-class reductions are
366 (not a count of runtime union operations). New constructor graphs and ordinary
per-Run examples remain in the archived native trace. This is not yet a complete
compressed-token target or ownership-retirement proof. See
`enumerated-native-results.json` for unresolved indices and hashes.

During the first attempt the external disk filled because small native artifacts
occupied large filesystem allocation units. All 71 existing case directories
were archived and byte-hash verified before removal; the three resulting disk
failures later passed on retry. The collector now runs each case in a temporary
local directory and retains one verified compressed archive. Resume checks all
existing archive hashes and provenance; retries preserve the previous archive
and record. Compiler timeouts kill the complete child process group before
archiving. An earlier archive altered by a lingering compiler child was rejected
and preserved as unverified, then re-executed. No unrelated data was deleted.

Validation: four enumeration/replay tests, three source-emitter tests, two archive/
timeout tests and one final-anchor-label test passed. These checks supplement
rather than replace the 487 native execution audits.
