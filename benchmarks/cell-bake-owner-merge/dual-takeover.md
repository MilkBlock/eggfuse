# Matched dual-source takeover with inherited suffixes

This opt-in experiment runs the standalone Cell CPU executor, not native egglog.
The saved four-workload catalog supplies actual immutable-constructor Entry
receipts. Typed query slots prove which symbols may alias; trace counts only
select candidates (at least two observations), never establish equalities.

## Replaced storage and live obligations

A successful matched Entry replaces two component signal arrays with one shared
layout, retires the right component, and removes/reinstalls exact boundary routes.
Public source/fact identities remain stable. Only right-hand source positions and
cached field locations move; left positions, scalar arrays and fact records stay
in place. No child component tree, duplicated binding graph or forwarding table
is retained. The source directory and completed source records still exist.

Admission checks complete concrete frame codes, live visible anchors, completed
sources and bound alias roots. Pending unions/repair/completion and active frozen
read epochs defer takeover. Residual query atoms and source Run/effect ordering
remain authoritative. Union repair still restores individual source facts; a
merged region is not an instruction to materialize every enclosed source.

The first trial lost the old components' baked suffix transitions. That made
later births independent and sometimes increased final binding counts despite
successful local takeovers. The compiler now inherits the full bounded closure
of both source suffixes (32 frames, 128 closure states per candidate). If the
closure is incomplete, the entire candidate is rejected. It never installs a
partial takeover that silently loses a known suffix. Query-class closure includes
new symbol aliases and RHS-result Entry edges. Marker certificates are checked
after installation. Existing plans without dual-source artifacts remain valid.

Candidates are indexed by two actual Entry addresses, rather than scanning every
compiled pattern. Production Graphs and frozen readers share the immutable Shape
directory with the Program. Exploratory training uses copy-on-write only when it
adds a Shape. This removes a duplicate directory rather than moving a second copy
into the Program's accounting.

## Accounting

Charge route probes, candidate attempts, symbol checks, source/field relocations,
pending skips and existing boundary/root operations. Temporary allocation bytes
are reported separately. Admissions and retired bindings describe coverage, not
additional savings credit. Source records, all fact records, indices, retained
Program heap and execution peak remain visible in the memory audit.

Initial and inherited-directory trials are retained in dual-takeover-initial.json
and dual-takeover-inherited.json. The latter reduced live components by 21–99 and
bindings by 21–86, but grew Graph heap by 0.33–2.05% because each Graph copied the
expanded Shape directory. Neither trial establishes large egraph compression.

## Reproduction

Use the shared compute queue for builds and executions. Build examples
batch_cell_learning and runtime_storage_peak with
iterative-bake,sparse-cells,storage-metrics, then freeze the two binaries together.
Reuse the saved batch inputs under out/cell-bake-owner-merge/batch:

```sh
batch_cell_learning apply-dual ROOT multi-source-observation dual-source-inherited
batch_cell_learning check-passive ROOT dual-source-inherited
# For each of fact, loopfact, sum-bits, dot-product in both prefix-all and
# dual-source-inherited, using the same frozen executable:
runtime_storage_peak ROOT/VARIANT/CASE/candidate.json ROOT/VARIANT/CASE/dual-shared-memory.json inherited-owners --port-domains-only
python3 benchmarks/cell-bake-owner-merge/dual_takeover_results.py ROOT OUTPUT.json dual-source-inherited dual-shared-memory.json
```

The analyzer checks source identities, all saved Run checks, Run counts and final
state hashes against each measured execution. Graph and retained Program are
separate teardown categories; their sum matters for total retained runtime heap.
This is not a timing campaign or a new native semantic acceptance claim.

## Final same-binary measurement

| case | Graph bytes control → candidate | reduction | live components | live bindings |
|---|---:|---:|---:|---:|
| fact | 638,751 → 633,087 | 0.887% | 492 → 456 | 1963 → 1927 |
| loopfact | 565,101 → 565,053 | 0.008% | 464 → 443 | 1868 → 1847 |
| sum-bits | 1,695,443 → 1,690,723 | 0.278% | 1344 → 1245 | 6761 → 6675 |
| dot-product | 1,641,667 → 1,635,971 | 0.347% | 1308 → 1225 | 6254 → 6178 |

All source-frame counts and fact live bytes remain unchanged. Retained Program
heap grows by 3,879,552 / 2,129,691 / 22,385,996 / 14,865,729 bytes respectively.
Thus total retained runtime heap and process peak regress despite the small Graph
savings. The experiment stays opt-in; it is not a successful large compression
strategy. Shared directories remove real duplication in both control and candidate,
but cannot pay for the expanded compiled closure. Merely increasing this catalog
is not justified: most joins remove only one binding. Further work must use
completion coverage to retire whole repeated state/maintenance or skip already
established effects, with source visibility and mutable dependencies still proved.

Right-only relocation reduces source moves from 154/101/465/421 to 69/33/186/152,
and cached field moves from 239/156/707/671 to 79/40/213/183. This is removed
maintenance, not evidence of measured speedup. The final summary is
`dual-takeover-shared.json`; earlier trial summaries remain for comparison.

Validation: 128 integration tests (47 execution, 63 ownership, 2 publication,
2 read guards, 14 stable ports), 210 runtime unit tests and 5 work-credit tests
pass. Runtime no-default-features check passes. The integration configuration
includes view-ports, cell-absorption and parallel-publication; without view-ports,
two pre-existing fixed 160-byte Instance assertions fail because Instance is
144 bytes. No production layout was padded to satisfy those assertions.
The saved batch passes all 2,652 Run snapshot/ordered-write checks and four final
checks. A fixture exercises inherited suffixes, projected fields, scoped workers,
stable handles, deletion and later union. These tests do not establish native
sum-bits choice acceptance or a publication speedup.
