# Template-derived values versus stable fact records

This batch analysis uses the saved `candidate-static-types-heap.json` executions.
It introduces no runtime storage or performance campaign. Its output is an
opportunity census, not a compression result.

| case | exact first-origin bindings | owned facts | facts with no scalar fields | stable field store bytes |
|---|---:|---:|---:|---:|
| fact | 803 | 948 | 653 | 107526 |
| loopfact | 753 | 892 | 633 | 56438 |
| sum-bits | 2850 | 2895 | 1825 | 224118 |
| dot-product | 2714 | 2825 | 2023 | 217702 |

The first count compares the **stored binding**, not its current union-find root,
with the unique native slot of the symbol's first introduction. A receiver added
in a later stage cannot establish that earlier origin. An earlier exploratory
count allowed any matching native slot and was slightly larger; it is not the
criterion used here. Unbound slots still require activation state, and foreign or
reused constructor results require their actual values.

The raw u64 values in the sum-bits exact-origin group total only 22,800 bytes.
This excludes Option tags, capacity, flags and replacement lookup costs; it is not
a net saving estimate. Do not introduce a rank/select or sparse exception scheme
just to eliminate this small payload while complicating union and field reads.

## The larger replacement boundary

`stable_ports::Stored` currently holds a table and a `Fields` record containing
component, source ordinal, operation and scalar array. A map keyed by FactRef owns
one such record for each stable fact. For the scalar-free group:

* FactRef already identifies source Cell and operation.
* Composition identifies the component and ordinal.
* Typed code determines the table; shared port wiring determines all fields.
* Component bindings supply Eq values; union-find supplies their current equality.

Thus those facts require no additional dynamic **field payload**. They still
require authoritative live/hidden/epoch state. The current node map also serves
as a live directory; deleting its record without replacing that responsibility
would make a stale template position appear to be a live fact.

The implementation target is one authoritative lifetime record plus template
projection, instead of separate fact lifecycle and stable-node metadata. Store
only actual scalar residuals for the other facts. Preserve original FactRef
identity and small source-frame recovery boundaries. Neither an all-saturated bit
nor equal current roots licenses inventing or resurrecting a fact.

## Worker constraint, checked in current code

`port_guard::Snapshot` freezes the stable-node map and component bindings using
read_epoch. It deliberately does not borrow Cells: ordinary Cell values/recipe
caches contain Rc-backed state. Coordinator retirement is represented by overlays.
Consequently, simply changing `stable_node` to read `Cells.fact_state` is not a
complete replacement. A successful unified representation must expose a plain
immutable lifecycle view to workers while keeping retirement/visibility overlays
authoritative. Copying all Cells for every worker wave, or adding a second full
membership set, would reintroduce the storage/maintenance being removed.

This is the next structural task. Acceptance should account for removed stable
node records, residual scalar storage, snapshot/overlay traffic, and peak handoff
storage together. The census does not prove the whole stable store is removable:
its byte total includes scalar payloads and other stable-port runtime state.

Validation: six offline tests cover first-origin selection, foreign binding,
hidden facts, missing bindings, duplicate/missing projections and later native
aliases. All four snapshots project every owned fact exactly once and agree with
the actual stable-node count. No runtime behavior was changed by this analysis.

```
python3 benchmarks/cell-batched-learning/template_payload.py out/cell-batched-learning benchmarks/cell-batched-learning/template-payload-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p test_template_payload.py
```
