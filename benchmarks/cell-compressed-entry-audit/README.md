# Structural compression as the completion model's input interface

Read-only inspection of `/private/tmp/eggfuse-cell-structural-compression`, whose
work was uncommitted over f20c0fce. No files there were modified or merged. This
audit reuses saved real-runtime artifacts; it does not run a benchmark or train
a model on final-state information.

## The representation change that matters

`stable_ports.rs::Fields` stores component identity, shared `PortProgram`, a
shared port map, operation position and dynamic scalar values. Equality field
locations are reconstructed from existing shared wiring instead of repeated
`PortRef` values. `take_over_instance_slots` deletes owned Eq slots only after
checking their values equal the existing component signals. `slot_fields` reads
delegated slots through that owner. Before owner retirement, surviving source
frames regain their delegated values. Actual constructor results that cannot
be reconstructed remain explicit.

This is a better input contract than rebuilding an adjacency graph for every
instance. A model can compile the static template/shape contribution once and
read only the required instance fields and boundary evidence. Where a feature
is affine in static and dynamic inputs, its static contribution can be folded
into a template-specific bias; a fixed quadratic cross-term can likewise be
folded into dynamic coefficients. Arbitrary data-dependent relations cannot be
declared static. Live Eq relationships, aliases to external results, visibility
and retirement still need authoritative evidence.

The dense live-frame directory reduces holes without changing logical IDs; it
is not an instruction to turn those IDs into real-valued model features.
Similarly, a delegated slot is not zero or an absent fact: `values` alone no
longer describes the instance's complete inputs.

## Saved evidence and its version boundary

The saved trace matches the original baseline's graph and ordered-audit digests
at all 1,428 Run boundaries. The snapshot contains:

- 2,385 retained instances, 194 template IDs and 123 used shared port programs;
- 1,863 delegated frames, 10,742 remaining explicit slots;
- 7,336 Eq values, 3,358 integers and 48 text values;
- 363 compiled port programs, 256 selected fragment recipes, 259 checked
  transitions, and 646 observed profile candidates.

A hypothetical repeat-per-instance scan of the static field descriptions visits
18,734 positions; scanning each used shared program once visits 1,239. This is
an opportunity accounting proxy, NOT measured saved operations or speedup.
The current runtime already shares those descriptions; the learner must not
reintroduce their repeated reconstruction.

The fixed original Graph-exclusive heap was 3,979,373 bytes. The saved optimized
Graph uses 3,015,293 bytes and adds 237,912 shared-layout bytes, leaving 81.75%
after that additional storage is charged. This does not meet the 30% target.
The final trace's own uncompressed lane is not the immutable original baseline.
Within-Run peaks and complete Program/Executor storage are outside this measure.

The latest inspected source instead reuses the existing PortProgram and reports
zero additional field-layout bytes. **The saved measurements do not establish
that newer version's result.** Binding takeover is also invoked by the
`storage-metrics` idle-boundary compaction diagnostic, not yet a default online
completion policy. Memory reduction is not a measured inference speedup.

## How to use this bench next

1. Use its exact typed wiring and existing slot reader as the reference for a
   compiled feature projection. Do not create a parallel fact graph or alias
   registry. Track static encoding once per shape separately from dynamic reads.
2. Before collecting training labels, export a time-aligned view of the existing
   frame/component mapping, bound signals and required boundary conditions at
   actual completion entry. The current final snapshot and aggregate profile
   do not provide these inputs or prove common saturated targets.
3. Keep existing checked composition dispatch as the baseline. If the template
   and current state already determine the transition, compile it directly;
   do not replace that exact lookup with ridge.
4. Evaluate learned proposals only where they can eliminate additional query,
   handoff or maintenance work, with compiler derivation evidence for takeover.
   Matching a larger structure or restoring its ports is not such a proof.
5. Charge field gathering, any Eq checks, batching, numerical inference, result
   validation, ownership restoration and publication. For a GPU test, count
   transfers and synchronization too. Preserve the existing Run/lifecycle checks.

This is a strong real-workload bench for representation cost, retention and
correct resumption. It is not yet a ready-made held-entry learning corpus. It
should complement the 5-rule native-checked multi-entry fixture, not be relabeled
as another successful model evaluation.

## Reproduce the saved-artifact audit

```sh
python3 benchmarks/cell-compressed-entry-audit/analyze.py \
  --baseline /private/tmp/structural-baseline.json \
  --trace /private/tmp/structural-final.json \
  --program /private/tmp/eggfuse-structural-baked/program.json \
  --profile /private/tmp/eggfuse-structural-profile/profile.json \
  --output out/compressed-entry-audit.json
```

Input hashes are retained in `results.json`. Source identity and plan dimensions
are checked, but the old trace does not record the optimized Program hash, so
exact optimized-artifact provenance is not independently established. No claim
about the changing worktree is derived from these frozen artifact numbers.
