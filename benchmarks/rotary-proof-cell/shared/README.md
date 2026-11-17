# Structure preservation and shared relation/pointer heads

This standalone GPU prototype replaces the flat 128-float recurrent MLP with a
279-float structured state. All old observations and source requests are copied
inside GPU-generated tokens. A shared relation MLP, a shared pointer MLP and a
shared activation MLP produce dynamic state. There is no CPU reconstruction or
inference fallback. The source egglog runtime is unchanged.

The exact ABI is in `abi.py`: 64 relation probabilities, 72 pointer probabilities,
139 protected source-input floats, three phase flags and one activation score.
Cell rotation acts on the first 64 lanes; port rotation is in transient reference
keys. Each transition takes the previous generated token plus schedule/address
metadata. Static input retention is a fixed copy operation, not a learned success.
The state is 1,116 bytes, versus 512 previously; no compression claim is made.

`PROTOCOL.md` records the first frozen experiment, including 16 fresh structures.
All three end-to-end-only runs are retained under `results/end-to-end`. Seed 1721
passes every original and fresh panel; 1703 fails to fit the pointer composition
even on training replay, and 1709 also fails to fit union. These failures are not
reclassified as correct. The result demonstrates representational capacity but
unstable fitting, rather than robust acceptance across initializations.

Six unit/contract tests pass. The model has no separate learned classifier per
endpoint pair. Ordinary GPU matrix features, state copies, source scheduling and
proof-template instantiation remain outside the learned heads. CPU verification
decodes actual saved token bytes and uses the existing independent source checker.
