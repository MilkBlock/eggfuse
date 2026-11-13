# Stable input keys with current Eq comparison

This is a bounded GPU prototype, not full Eggcc runtime acceptance. Stored Cell
keys retain original input identities. Admission creates a transient typed
comparison view from the current Eq registry: Eq inputs compare current roots,
scalar inputs compare exact caller-owned keys. Keys and input slots are not
rewritten after union. Same-round and resident-key dedup use the same view.

Bake compiles key types from original query inputs, independently of effect slot
overwrites. Nested and flat stage prototypes pass the live registry when present.
An unsettled registry, invalid typed identity, or invalid present resident key
blocks admission and marks attention; none is treated as evidence of saturation.
Without a registry, legacy callers retain exact raw-key comparison.

98 mechanism tests pass, including compiled Metal alias dedup without key
rewrites and nested multi-source query/effect execution. This does not prove
complete query coverage, ownership release, deletion handling, or saturation for
an actual Eggcc workload. Pairwise comparison and registry access remain costs.

Bake reference d911ff49 removes marker materializations but measures increased
resident Program memory. Accordingly these static type tables and transient
comparison arrays are additional storage, not a claimed speed or memory gain.
