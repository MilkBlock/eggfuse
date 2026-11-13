# Runtime closure storage obligations

Source: four saved actual standalone Cell executions at atomic constructor
completion (`f5e675fa`). This analysis runs no workloads or timing campaign.
The saturation observations use the same source/catalog but are not individually
joined to final surviving instances. They cannot establish removable live facts.

| case | Graph bytes | Cell storage | component/directory/boundary/stable storage | missing source instances still positioned | static sites without a live owned fact |
|---|---:|---:|---:|---:|---:|
| fact | 705175 | 181432 | 292510 | 26 | 532 / 2909 |
| loopfact | 616289 | 155736 | 235422 | 18 | 465 / 2716 |
| sum-bits | 1830387 | 506952 | 883038 | 194 | 2808 / 10519 |
| dot-product | 1798019 | 502568 | 846518 | 146 | 2069 / 9600 |

Even the impossible removal of **all** Cell storage leaves 72–75% of the current
Graph. This is a bound relative to the current snapshot, not the original baseline
or a prediction of attainable savings. Cell record compression alone cannot reach
30% of this snapshot. The four maintenance fields must also be addressed.

## Why an absent source still has a position

`Graph::retire_empty` releases an empty, unreferenced source instance. The enclosing
composition remains alive while another fact survives. Its frame list and directory
remain available. `composition::Runtime::signal` resolves a symbol's static origin
through `components -> frames -> directory.code -> query class`; removal of that
directory entry would therefore break a valid future lookup, even though the
source instance no longer exists. This is concrete lifetime coupling to static
type information, not a requirement to retain the original source values.

Other consumers use code/ordinal for witness routes, candidate dispatch and future
composition. A correct replacement must compile typed origins and code-specific
operations into shared template information and preserve the logical positions
needed by surviving facts and Entries. Do not simply erase directory entries.

## Implications for cross-stage completion

1. Distinguish typed template positions from live instance storage. A typed
   closed layout should resolve operator/query-class information without keeping
   a dead source directory record. Preserve original IDs for still-visible facts.
2. Compile which local fact sites a stage needs. On a proved stage transition,
   replace obsolete local dispatch with the remaining static slice. A previously
   absent site may represent constructor reuse rather than deletion; importing a
   replacement receipt and its lifetime obligations still requires proof.
3. Keep exported slot/Entry obligations separate from local fact activity. In
   sum-bits, 711 bound symbols have no live owned local site, but that does not
   prove that all external readers or native address interpretations are gone.
   Hidden facts also remain congruence obligations (141 symbols have only hidden
   owned sites). Neither category is safely removable by this census.
4. Keep source-sized restoration boundaries. A typed template replacement must
   not turn one invalidated scalar provider into expansion of all ancestor frames.
   Reuse existing lifecycle state; do not add a second runtime reverse-use graph.

The current observer reports only 401 / 6532 fully covered applies in sum-bits
and 259 / 5935 in dot-product. Coverage can remove redundant execution, but those
observations do not prove that the applications own redundant final facts. Do not
convert these counts into an egraph memory-saving claim.

Next implementation admission requires a typed layout that removes an existing
directory/dispatch dependency, with union, deletion, external Entry and Run-boundary
tests. The new census is not itself a completed takeover or speedup.

Reproduce:

```
python3 benchmarks/cell-batched-learning/closure_storage.py out/cell-batched-learning benchmarks/cell-batched-learning/closure-storage-results.json
python3 -m unittest discover -s benchmarks/cell-batched-learning -p test_closure_storage.py
```

Five tests distinguish hidden owned facts, missing source instances, unbound
symbols, exported symbols without local sites and duplicate instance positions.
