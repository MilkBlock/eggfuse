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
