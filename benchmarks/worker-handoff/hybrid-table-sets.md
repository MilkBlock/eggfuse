# Directly iterable hybrid completion sets

The prior ledger identified 94 dense obligation sets dominating ID payload.
This change replaces Rc<[usize]> obligations with shared TableSet objects in
completion reads, rule query/RHS/access demand, scheduled query demand and
scope tables. A sorted unique sequence uses a bitmap only when its bounded
word payload is smaller than the usize sequence. Small sets stay sparse;
unsorted or repeated external scope sequences stay sparse and preserve order.
Bitmap length follows the largest ID, not the full table universe.

Forecast selection, conflict reporting, readiness, matched RHS demand and
compiler dependency derivation consume values directly through a cloneable
iterator. Dense iteration skips empty words and extracts set bits in ascending
order. No conversion cache or per-query decompressed array is introduced.
Existing mutable Influence.reads and eager-scope work buffers still materialize
because they are extended; these allocations have not been claimed as removed.
Exact interning remains compile-local and pointer identity still skips repeated
RHS demand groups. Source snapshot reads, ordered effects, conservative union
influence, late matches and source Run barriers remain authoritative. No new
prediction fact, dependency subscription or cross-stage takeover is introduced.

Against `9cc5437f`, the same executed sum-bits plan retains 2,209 owners and 771
unique sets, with identical expanded membership and exact closure signature:

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| Unique payload plus object/ownership headers | 120,792 | 54,936 |
| All owner handles | 35,344 | 17,672 |
| Counted total | 156,136 | 72,608 |

This saves **83,528 bytes (53.5%)**. The actual encoded payload is 17,928 bytes;
each unique object's remaining 48 bytes includes Data/enum/length and a two-word
Rc header. This deliberately charges the larger per-set descriptor instead of
reporting the 90 KB payload estimate as the final saving. The optional prediction
ledger subtotal falls from 189,376 to 105,848 bytes; the separately counted
ordinary Cell catalog is unchanged at 19,592. Neither subtotal is complete RSS.

There is a cost: source-layout accounting has 771 retained Rc allocation blocks
before and 1,541 retained blocks after (Rc object plus each nonempty boxed
payload). Interning can also allocate temporary encoded candidates before
finding a shared owner. These are not measured allocator event counts. Runtime
bit extraction replaces indexed integer loads; existing logical counters do
not count those machine instructions. No speed benefit or allocation-count
improvement is claimed. Excludes allocator rounding and unrelated metadata.

Validation: 50 compiler integration tests across merge_completion,
scoped_completion, staged_completion, completion_batches and port_completion,
plus the ordered-reader forecast regression and two TableSet tests covering sparse/dense membership, word boundaries,
empty words, iterator cloning, usize::MAX, exact wire representation, shared
lifetime and unsorted/duplicate preservation. Updated sharing tests retain the
same owner-identity obligation. Expanded Plan, every affects pair and singleton
scope signature agree. Scoped executions (--local-congruence --port-scopes)
agree on all normalized work counters, 1,428 ordered Run signatures and exact
state SHA. Native reviewed semantic acceptance passes. No timing campaign ran.

Reproduce the before/after inspections with inspect_completion_storage and
features iterative-bake,sparse-cells,view-ports on the frozen program
out/cell-slot-inheritance/compact-final/program.json. Run release kernels with
the flags above and the documented choice_diagnosis.py gate, then:

```sh
python3 benchmarks/worker-handoff/check_table_lists.py --mode hybrid \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

The check JSON records hashes, actual storage and additional allocation model.
The updated prediction_storage_ledger.py supports both historical usize lists
and hybrid sets, reconstructs encoded payload from exported membership, and
reconciles shared owner headers. hybrid-prediction-ledger.json records the new
nonoverlapping subtotals. This is standalone Cell CPU optional plan storage,
not a change measured inside native egglog or ordinary runs without that plan.
