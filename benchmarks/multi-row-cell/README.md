# Two-dimensional Cell references and shared template views

This is a **deterministic GPU address/view substrate**, not the multi-row neural
network, an eggcc backend, a union engine or a compression result. The current
user goal prioritizes fast complementary neural token generation. This code is
retained to read and audit such future proposals; no further compression work is
required before testing the network.

A graph has multiple rows and multiple instance positions in each row. A reference
is `(row, position, template_port, generation)`. Instance records point to a shared
constructor program and a boundary-reference payload. They do not carry copies of
all member instructions or an instance-private equality matrix.

The offline compiler composes two programs using declared producer/consumer wires.
It emits one target template, boundary-source projections, and shared old-port
maps. Multiple instances reuse those programs and maps. Programs are pure finite
constructor DAGs, with a source visibility Run per operation; the current bitset
limit is 32 ports. This is not a general compiler for eggcc rules or automatic
iterative Bake selection.

## What executes

- `catalog.py`: validates constructor arity, topological order and stage order;
  composes programs without copying an observed endpoint graph.
- `device.py`: resolves references, reads virtual constructor views, publishes a
  bounded frontier, validates supplied compositions and transitions ownership.
- `rotary.py`: separates row, within-row position and port rotations. Its keys
  currently encode addresses only; no learned reference-key generator exists.
- `reference.py`: expands the ORIGINAL source instances after GPU execution. It
  does not use the new composition target to construct expected results.

In `read_encoded`, rotary retrieval must agree with the declared exact pointer.
An inconsistent key/pointer is rejected, never silently replaced by the declared
pointer. This tests an address contract; it does not establish that a network
learns those addresses. Joint all-candidate scoring is temporary and may be costly.
Generation and visibility are exact checks outside the rotary score.

The compiled test path performs Run 1 -> ownership transition -> Run 2 -> reads
without intermediate CPU state readback. A nested test performs another
composition and Run 3. Parents are replaced by forwarding headers referencing
shared projections. The target reuses source arena capacity even when the arena
was initially full. Old parameter payloads are cleared; poisoning freed payloads
does not change reads. Source aliases remain represented by lightweight metadata.

Transfers execute in source effect order inside one compiled graph. A second
claim on an already retired source rejects. This is NOT a concurrent lock-free
or multi-stream commit protocol. Source versions, destination versions, wiring,
bounds and arena ownership are checked before any transition is accepted.

A Run with unfinished source operations cannot advance; budget exhaustion remains
pending. The test supports only the fixed pure-constructor source contract, not
arbitrary saturation, mutable effects or complete source-rule coverage.

## Evidence

12 tests pass. They cover cross-row reading, nonuniform port projections, staged
visibility, stale generations, invalid descriptor bounds, wrong wiring, overlapping
retirement, alias-cycle budgets, nested composition, poisoned retired payloads and
an initially full arena. Compiler tests reject stage inversions and exercise a
third compiled component. Encoded reads actually pass through rotary retrieval
before reading the shared view.

The layout sweep has six graphs (three shapes of the row arena, two seeds). Each
graph contains multiple coupled producer/consumer pairs: a consumer also references
the NEXT pair's producer, including across rows. These are not independent samples
pretending to be one graph. Expected terms come from the source interpreter only
after the device has finished. All 480 original-port observations across the two
Runs agree.

| Rows x positions | Source instances | Active payload slots after | Forwarding records | State tensor bytes before / after |
| --- | ---: | ---: | ---: | ---: |
| 2 x 8 | 8 | 4 | 8 | 900 / 900 |
| 4 x 8 | 16 | 8 | 16 | 1796 / 1796 |
| 4 x 16 | 24 | 12 | 24 | 3268 / 3268 |

Each size uses the same 340-byte GPU template/projection catalog. Active payload
SLOTS halve; useful boundary REFERENCES decrease from three per pair to two.
Those are different counters. Fixed-capacity tensor storage does not shrink.
These byte counts are array element footprints, not measured GPU allocator peaks
or RSS, and omit transient queries, compilation caches and audit packets.

See `results.json` for all counts and source hashes; binary audit checkpoints
remain under `/Volumes/EggFuseWorkspace/experiments/multi-row-cell-foundation-20261118-checked`.

## Structural argument and limits

Composition preserves each original port by induction over the declared DAG:
left ports retain their operations; a wired right parameter projects to its
proved left port; an unwired parameter becomes a target boundary binding; each
right constructor applies the same opcode to recursively projected arguments.
The compiler retains stage metadata, while the device projects only actually
completed operation flags. Thus a transfer does not authorize early publication.
The GPU tests check this against a separately expanded source graph.

This argument covers pure constructor terms only. It does not establish a
canonical returned FactRef under global hashcons collisions, arbitrary union,
negative queries, scalar mutations, true parallel ownership commits or neural
completeness. There are no learned weights and `model_executed` is false.
`union_executed` is also false. Neither this result nor correct rotary lookup
proves the active architecture goal complete.

## Reproduce on the external workspace

```sh
~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python benchmarks/multi-row-cell/test_device.py

~/.local/bin/eggfuse-job submit --kind compute -- \
  /Volumes/EggFuseWorkspace/bin/run-eggfuse python benchmarks/multi-row-cell/run.py \
  /Volumes/EggFuseWorkspace/experiments/FRESH-DIRECTORY
```

Requires the existing MLX/NumPy environment and Metal; missing Metal is an error.
The next priority is the actual complementary multi-row neural generator and its
joint correctness/latency baselines, not further arena compression.
