# Union and materialization cost audit

Scope: current standalone Cell runtime, saved four-case residual-parent executions.
Typed nested child views are offline candidates, not an executed runtime hierarchy.
The measurements below therefore cannot establish the cost of an arbitrary future
nested implementation. Counts are work counts, not timings or allocated bytes.

## Actual paths

1. `Graph::union` in `graph.rs` links Parents and calls `propagate_owned_union`.
   `cell_ownership.rs` moves boundary routing and traverses the shared signal
   slices, coalescing affected fact columns through a heap. Stable signal bindings
   and the shared shape do not change. Work scales with activated slices and their
   static uses (including retired sites skipped during traversal), not automatically
   with the whole containing Cell. This is dispatch/completion work, not stored-field
   materialization.
2. `propagate_cell_fields` in `stable_ports.rs` publishes a proved result-only
   change or enqueues key completion. `complete_port_key` in `port_keys.rs` checks
   compiled local conditions, then the complete port-key candidate domain where
   needed. `complete_cell_collision` enqueues equality of outputs and retires a
   duplicate. The stable path passes `hash: None`: it does not rewrite canonical
   key hashes or stable Eq fields. Temporary row reads still allocate/read values.
3. `Graph::retire` calls `preserve_completed_scalars` before removing the fact.
   If the retiring fact is the last readable provider of a delegated scalar slot,
   the code restores that scalar. If its source frame is in completed storage,
   `unseal_completed` first rebuilds the **whole source frame's** remaining slot
   and fact containers. It does not unseal all siblings in the composed owner.
   This is a concrete amplification: losing one provider can cost all stored
   fields/facts in that source frame. Scalar-plan scanning and alternative-provider
   checks happen before that fallback.
4. `composition_retire_fact` in `ownership_composition.rs` tears down a component
   when its last owned fact disappears. It scans all component signals to remove
   boundary registrations, then all source frames. Compressed symbolic frames
   with surviving parent users are restored; ordinary symbolic frames enumerate
   their template slots and restore missing bound Eq values. The cost can cover
   the entire component at retirement, even though only residual external readers
   require bindings. This is lifetime coupling, not a necessity of union-find.
5. Independently, `extend_completed` flattens old completed owners plus the new
   suffix at a settled Run boundary. It moves old slots and facts and allocates
   the replacement arrays. Repeated extension can sum to quadratic prefix work.
   This is growth/compaction cost, not direct union materialization. The optional
   segmented experiment removes these moves but retains more headers and dead
   entries; it is not the default and did not reduce final memory.
6. A representation-changing `FactWrite` also unseals its source frame if it no
   longer satisfies the owned-fact contract. The saved runs report zero such
   `representation_fallbacks`. Ordinary epoch/hidden/hash changes do not take
   this path, including the new stage-inherited lifecycle representation.

## Saved evidence

| case | nontrivial unions | repair collisions | port completions | restored scalar slots | restored compressed frames | old slots moved by extension | old facts moved by extension |
|---|---:|---:|---:|---:|---:|---:|---:|
| fact | 143 | 67 | 76 | 8 | 2 | 337 | 339 |
| loopfact | 126 | 47 | 57 | 3 | 0 | 253 | 280 |
| sum-bits | 1039 | 844 | 1046 | 47 | 13 | 1094 | 1256 |
| dot-product | 607 | 336 | 427 | 25 | 10 | 2671 | 1835 |

Source: each `candidate-residual-parent-heap.json` under
`out/cell-batched-learning`, fields `completion_work`, `stable_fields.stats`, and
`source_storage.completed_owners`. Restore counters combine scalar-provider loss
and component-lifetime fallback. They do not identify the triggering union or
count expanded bytes. Do not divide restored frames by unions and call it a
probability, or infer worst-case amplification from these totals.

## Consequences for child reuse

Template reuse need not imply a recursively owned/materialized instance tree.
A child's existing fact identity and stable ports can remain valid after new Eq
relations; a different representative alone does not require re-extracting the
child or its parent. Constructor collisions, deletions and mutable reads still
need real checks. Saturation is relative to admitted boundary conditions and
source stages; an unconditional persistent saturated bit is not sufficient.

Do not admit an optimization that couples a child's deoptimization to recursively
expanding all ancestors. Keep selective projection, storage lifetime and template
composition separate. In particular, the current scalar-last-provider fallback
must be addressed before merging many source frames into one indivisible child
storage unit. Compile the residual required interface and bound the fallback to
it; account for any forwarding/lifetime machinery needed to keep it valid.

The next missing measurements are cause-tagged restored slots/facts/bytes,
maximum restoration per triggering event, component teardown scan work, and
subsequent re-compaction of the same frame. Existing counts establish where
amplification can occur, not that catastrophic expansion has already occurred.

## Cause-tagged restoration measurements

The follow-up runtime observation distinguishes scalar-provider loss, component
retirement, and representation fallback at the actual `unseal_completed` entry.
Counters record remaining slot/fact counts and the newly restored containers'
capacity, plus the maximum event and its source template. They are fixed per-Graph
counters, not per-fact history or another runtime index. The caller's subsequent
insertion of lost scalar bindings and ordinary source arena growth are excluded;
these figures are not total allocation traffic, net heap increase or peak memory.

| case | scalar-driven unseals | requested scalar slots | existing slots restored | remaining facts restored | summed array capacity | maximum one event |
|---|---:|---:|---:|---:|---:|---:|
| fact | 2 | 2 | 4 | 2 | 672 | 336 |
| loopfact | 0 | 0 | 0 | 0 | 0 | 0 |
| sum-bits | 13 | 13 | 24 | 16 | 4,320 | 360 |
| dot-product | 10 | 10 | 20 | 10 | 3,360 | 336 |

Component-retirement and representation-driven unseals are zero in all four
executions. This does not imply component teardown scans are absent: only the
compressed-frame restoration branch was counted here. Nor are these counts proof
that a future indivisible nested Cell has bounded materialization cost.

The measurements do **not** justify prioritizing a residual-storage mechanism
for the current small source frames. They do justify retaining those small
restoration boundaries when composing templates: do not fuse their lifetime or
fall back to expanding an entire ancestor solely to recover one field. Current
prefix-copy costs remain separately charged to owner extension. Before changing
storage granularity, bound the largest possible affected storage region using the
compiled layout, and measure actual fallback amplification after that change.

Validation: seven fact-state tests pass, including cause attribution, deleted facts,
missing owners and restored capacity. All four final-state hashes and exact
lifecycle snapshots equal the preceding stage-inherited executions. This is an
observation-only change; the preceding storage implementation has the separate
2,652-Run acceptance evidence. No performance campaign was run.

Reproduce by building the existing `runtime_storage_peak` example, recording each
unchanged seed into `candidate-restoration-audit-heap.json` with `inherited-owners
--port-domains-only`, then:

```
python3 benchmarks/cell-batched-learning/restoration_cost_results.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/restoration-cost-results.json
```
