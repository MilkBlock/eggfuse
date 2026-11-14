# Interaction coverage boundary

The current generator covers one completed producer and one consumer from a
selected recipe. It does not cover all Eggcc Cells, multiple producer ownership
states, stage reachability, or an iterative closure of generated interfaces.
`within_bound_complete` refers only to the generator's wiring/partition domain.

`--include-missing` enumerates three input-source choices: a producer export,
explicit boundary support (-1), or omitted boundary support (-2). At least one
producer connection is required. Typed partitions and constructor congruence are
still enumerated. Replay reconstructs the support choices before closing facts.
Omitted support never asserts absence: another producer fact, an alias, or later
completion may satisfy the query. Execute the case to determine readiness; do
not train a negative label from -2 alone.

This adds partial-boundary inputs, not ownership retirement or arbitrary negative
guards. Existing invocations retain their original supported-boundary domain.
Five enumeration tests pass with the NumPy-enabled experiment Python, including
support omission/replay and support recovered from a producer fact. This is
experiment data generation, not a change to the native executor.

## Multiple logical producers

`--producers N` chooses N producer rule instances and one consumer. Repeated
rule types are allowed, but instances receive distinct slot namespaces before
wiring and typed partition enumeration. Every producer must supply at least one
consumer query atom. `producer` remains an integer for legacy single-producer
cases and is an ordered rule-index list for multi-producer cases. Export indices
refer to the concatenated producer exports, so replay preserves input origins.
A producer can export either its matched inputs or its completed operations.
This is logical derivation provenance, NOT evidence of physical result ownership.

All type-compatible producer/consumer assignments, export choices and allowed
Eq/i64 partitions are visited within the requested class budget. Producer order
is retained; permutation-equivalent routes may yield the same snapshot. The
consumer must still be a positive query supported by the chosen facts, except
where boundary support is explicitly omitted. Unused producers are rejected,
rather than becoming arbitrary unrelated context.

The native collector can validate and group these snapshots using the existing
schema. However, graph import currently materializes constructor facts; it does
not restore producer ownership frames from this provenance. Physical aliasing,
retirement, generation, visibility and stage schedule variants still need their
own execution-state generation. Multiple producers here expands structural
training inputs; it does not complete ownership-state coverage or interaction
closure. The six enumeration tests include two same-rule producer instances,
source-preserving replay, unused-source rejection and explicit budget exclusions.

For the existing three-rule context family, two producers require at most 11
pre-partition typed classes. Budget 10 excluded 8 of 120 wirings; budget 11
excludes none. The complete bounded run visits 106,576 partitions and emits
25,670 provenance-bearing cases, with 10,096 distinct snapshot hashes. Of these,
9,974 hashes do not occur in the earlier single-producer set. These hashes use
the existing normalization, not a proof of arbitrary graph-isomorphism novelty.

Reproduce with the earlier enumeration manifest as recipe input:

```
python enumerate_cell_interactions.py RECIPE_MANIFEST OUTPUT \
  --producers 2 --max-classes 11 --include-missing
```

`multi-producer-enumeration-results.json` records recipe, case and archive hashes.
The source archive is one gzip file on the external SSD to avoid per-file block
allocation overhead. No native-label or training campaign has yet been run for
these 10,096 snapshots; the report must not be read as a prediction result.
