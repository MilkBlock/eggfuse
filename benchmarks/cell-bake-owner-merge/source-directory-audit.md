# Source records are not yet replaced by logical composition

The 108-extension candidate passed all 882 Run checks and native final-state
acceptance in job 360. Its Graph uses 1,386,283 requested bytes, still 192,472
above the historical 30% threshold. The following audit joins its saved source,
fact lifecycle, physical owner and logical component inventories. It performs no
new workload execution and adds no runtime index.

All **2,177** completed source records have corresponding ownership routing
records. The source records occupy 104,496 bytes of live record payload
(110,592 bytes including spare capacity). The separate ownership directory
occupies 163,584 allocated bytes, including its index and spare arena capacity.
These amounts must **not** be summed and called removable duplication:

- A completed source record stores physical owner/slice positions, a storage
  layout, creation epoch and recipe depth.
- An ownership frame stores the logical component, ordinal and native-port
  code. Together with the component it resolves old source-based Eq addresses.
- Logical source IDs are represented in both directories, but most record
  fields currently serve different obligations. Deleting a source record
  without moving its responsibilities loses fact and slot addressing.

The snapshot exposes why naive region replacement would be wrong:

| Constraint | Observed components |
| --- | ---: |
| Spans multiple physical owners | 529 |
| Shares a physical owner with outside sources | 1,320 |
| Contains sources from multiple creation epochs | 531 |
| Contains multiple recipe depths | 79 |
| Retains a routing-only source whose ordinary/completed record is gone | 10 |

Among fully present components there are 304 distinct `(shape, native codes)`
groups but 372 observed source-storage layout combinations. Fifty-one groups,
covering 420 components, have multiple layouts. Thus shape and native code alone
do not determine the physical layout. Differences in actual constructor reuse,
stored slots and retained fact operations must remain represented; these
observations do not establish which cause applies to each variant.

This refines the next structural target: unify source lifecycle and routing
addressing under the composed Cell, then remove the old source record. A
takeover needs a checked storage-layout specialization, old FactRef/source-ID
projection, per-source epoch/depth where they differ, and views of existing
physical segments. Requiring exclusive physical owners would exclude 1,320 of
1,364 components; flattening their arrays would copy shared prefixes and create
the materialization cost already rejected by earlier experiments. Routing-only
sources need an explicit native-address fallback until their Eq obligations
are discharged.

No such takeover is claimed by this audit. It rules out treating 2,177 as the
number of immediately deletable records, and rules out inferring a unique
storage layout or creation epoch from a structural Cell shape. The next runtime
change must remove an old addressing/maintenance path, not add another region
directory beside both existing directories.

```sh
python3 benchmarks/cell-bake-owner-merge/source_directory_audit.py \
  out/cell-direct-prefix-growth/budget128/memory.json \
  benchmarks/cell-bake-owner-merge/source-directory-audit.json
```

The script checks cross-directory source identity, template agreement and
physical owner membership before reporting. The report includes the input hash
and catalog digest; observations are explicitly separate from compiler proofs.
