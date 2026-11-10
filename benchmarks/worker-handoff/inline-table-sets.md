# Inline short prediction sets

The executed hybrid-set plan from `784ff89d` retains 771 unique sets. Of these,
155 have one item, 266 have two, 141 have three, and one is empty. The preceding
compression saved bytes but split every nonempty set into an Rc object and a
separate boxed payload. The next opportunity is those 562 short payloads.

Replace Data's common length plus representation enum with an enum containing
Empty, One, Two, Three, Sparse and Dense variants. The dense variant stores its
length beside its word slice; sparse length comes from the slice. Up to three
native-word IDs fit in the same 32-byte Data size on this target. The Rc header
remains 16 bytes and the owner handle 8 bytes. No packed/unsafe memory access,
new allocation pool or extra runtime index is introduced. Short values iterate
by borrowing their inline storage, preserving source order and duplicates.

This compresses existing shared query/RHS/repair obligations. It does not infer
new permissions at source Run boundaries. Mandatory snapshot reads, ordered
mutable effects, union closure, opaque fallbacks, binding visibility and all
remaining repair obligations are unchanged. Long sets retain the existing
sparse/bitmap choice; exact compiler interning still preserves RHS group reuse.

| Retained component | Before bytes | After bytes |
| --- | ---: | ---: |
| Shared objects, ownership headers and external payloads | 54,936 | 46,128 |
| Owner handles | 17,672 | 17,672 |
| Total | 72,608 | 63,800 |

The measured retained scope saves **8,808 bytes (12.1%)**. All 771 shared owners
still cost 48 bytes each, so this is a net saving after descriptors. The optional
plan ledger subtotal falls from 105,848 to 97,040 bytes. The ordinary catalog's
selected subtotal remains 19,592 bytes; these are not complete RSS figures.

Source-layout accounting reduces retained allocation blocks from 1,541 to 979:
771 Rc objects plus only 208 long boxed payloads. This removes 562 of the 770
extra retained blocks introduced by hybrid-v1. It remains 208 blocks above the
original 771-block Rc-slice layout. Counts exclude temporary compiler/interner
allocations and allocator rounding; they are not observed allocation events.
No latency improvement is claimed and no timing campaign ran.

Validation: 50 compiler integration tests (merge_completion, scoped_completion,
staged_completion, completion_batches, port_completion) and three TableSet
unit tests pass. The new test verifies Data does not grow, short sequences have
no external payload, source order/repeats/usize::MAX survive, iterator clones
continue at the same position, and long sparse data retains its external store.
Expanded Plan, closure and singleton scope signature are exact. Scoped runtime
(--local-congruence --port-scopes) retains all normalized work counters, 1,428
ordered Run signatures and final state hash. Reviewed native semantic
acceptance passes. This measures standalone Cell CPU optional prediction data,
not the native egglog runtime.

Reproduce both inspectors using inspect_completion_storage with features
iterative-bake,sparse-cells,view-ports on the frozen sum-bits program. Run release
kernels with the scoped flags above and the reviewed choice_diagnosis.py gate,
then compare saved outputs:

```sh
python3 benchmarks/worker-handoff/check_table_lists.py --mode inline \
  --before BEFORE.json --after AFTER.json --root OUTPUT_ROOT \
  --program PROGRAM.json --baseline BASELINE_BINARY --candidate CANDIDATE_BINARY \
  --output CHECK.json
```

inline-table-sets-check.json records hashes, measured bytes and the allocation
model. prediction_storage_ledger.py now also reconstructs inline-v2 payloads;
inline-prediction-ledger.json records the nonoverlapping storage subtotals.
