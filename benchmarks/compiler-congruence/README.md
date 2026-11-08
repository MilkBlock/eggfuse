# Compiler proofs and the first cross-stage continuation

This follow-up to `2cc8a172` targets the existing compiler and feedback-driven
Bake pipeline. It uses the **standalone Cell CPU runtime**, including the
ordinary repair engine for the complete applications. It does not enable the
restricted `--congruence-cells` executor on those applications.

## Additional proof and execution capability

`eggfuse-result-switch/v2` is an opt-in proof policy. Loading reconstructs the
switch from typed recipes and rejects altered proofs. Existing v1 artifacts
retain their previous derivation and serialized plan.

The compiler now closes known constructor facts under congruence after the
complete LHS and after a source Run's queued unions become available. For
example, a producer may have witnessed `F(a)`, `F(b)` and `G(F(a))`, then queued
`a = b`. After that boundary, a consumer of `F(b)` can use the earlier `G` receipt.
The compiler previously propagated the explicit equality without revisiting
the earlier constructor facts. Deleted tables are removed from the donor facts;
runtime receipt checks still require a live, visible row with the complete key.

A complete RHS may now include explicit unions. Preflight first checks every
required receipt and operand. On success it reserves the original logical Cell
ID, enqueues the unions in source order, and publishes through the existing Run
barrier. Failure leaves the ordinary RHS available once. This does not authorize
using a queued union to satisfy an earlier instruction in the same RHS.

The runtime also initializes the completion state of a root producer when its
rule has one admitted leaf and a compiled continuation demands its receipts.
Previously the first producer did not enter the result switch or remember these
receipts; the first consumer started from a leaf reset. During training, unique
root leaves are also recorded before a continuation demands receipts, so the
first useful edge can become a candidate. `root_completion_seeds` counts these
initializations, not completed RHSs or committed mutations. Ambiguous leaf
entries retain their previous path.

## Tests and actual opportunity

164 all-feature workspace tests pass, with four existing tests ignored. Two
focused compiler tests also pass with the non-sparse runtime and iterative Bake:

- A warm and a cold producer both supply two constructor results after
  congruence; the consumer completes without a frame and preserves its explicit
  union. The cold producer's first useful edge can also be learned from an empty
  continuation catalog.
- Moving the union into the consumer leaves its dependent constructor request
  necessary until the barrier. The test checks the new row is really created.

The existing deleted-sibling regression also checks v2's successful completion
and atomic fallback. Native egglog executes the focused fixtures' source checks.
Relabeling the stronger certificate as v1 fails reconstruction.

The complete sum-bits and Raytrace programs each have 582 rules, but the frozen
catalog has only 32 leaf entries and 32 composed units. On that fixed catalog,
v2 has exactly the same successful work as v1: 165 / 17,152 complete RHSs and
272 / 30,896 substituted constructor reads. No demanded cold root is seeded.
The saved parent executable, the new v1 path and the new v2 path preserve the
final graph and every semantic schedule entry on 1,428 / 16,883 Runs.

We then reseeded from the 32 leaves and allowed six learning rounds, depth 8,
16 primitive nodes, 128 total units, 16 admissions per round, 2,048 candidate
counters and support 2. Every round checks the final graph, semantic schedule
and ordered RHS-input digest against its first round. Both old and new policies
stop after two admission rounds, well below the larger budget.

| Case / policy | Final units | Reused constructor reads | Reused sets | Complete RHSs |
|---|---:|---:|---:|---:|
| sum-bits / v1 | 37 | 272 | 165 | 165 |
| sum-bits / v2 with root training | 37 | 272 | 165 | 165 |
| Raytrace / v1 | 39 | 30,900 | 17,346 | 17,152 |
| Raytrace / v2 with root training | 45 | 30,901 | 17,346 | 17,152 |

The proof-only v2 experiment before root training selected the same 37 / 39
units as v1. Root training exposes additional candidates on Raytrace, but their
realized value is only **one additional constructor read**. More admitted cells
do not establish a throughput improvement. The learned Raytrace v2 artifact
initializes 914 demanded root states, so the extra storage work must also be
charged against that one additional read. These are work counts and correctness
executions; no controlled latency gain is claimed for this iteration.

[results.json](results.json) keeps both experiment stages, all learning rounds,
binary hashes, fixed-catalog controls and separate execution checks of learned
artifacts. Compiler-round digests and standalone-runtime file digests are kept
in their own comparison domains. This is bounded replay-and-recompile learning,
not in-process hot replacement. Constructor repair and RHS publication remain
runtime obligations.

The next coverage constraint is the fixed leaf set: raising the continuation
budget cannot propose paths through rules outside those 32 entries. Broader
leaf admission must still be based on actual executions and typed coverage,
and its value must be measured through successful reuse rather than proposal
counts.

## Reproduce

Start with a compiled program containing validated Spine blocks, such as the
frozen programs described in the repository README. Use fresh output paths.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --example complete_blocks
target/release/examples/complete_blocks SEED_PROGRAM out/v2.json --congruence-completion
cargo cell-iterate --program SEED_PROGRAM --output out/learn-v2 --objective rhs-congruence --rounds 6 --max-depth 8 --max-nodes 16 --max-units 128 --new-per-round 16 --candidate-slots 2048
cargo cell-iterate --program SEED_PROGRAM --output out/learn-v1 --objective rhs-lookups --rounds 6 --max-depth 8 --max-nodes 16 --max-units 128 --new-per-round 16 --candidate-slots 2048
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test compiler compiler_
```

`complete_blocks --congruence-completion` changes the proof policy without
changing the existing unit selection. The new `rhs-congruence` objective uses
the stronger policy during candidate scoring and subsequent executions.
