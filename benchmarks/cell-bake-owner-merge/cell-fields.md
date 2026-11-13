# Stable facts read their owning Cell slots

This is an opt-in representation replacement in the actual standalone Cell CPU
runtime, not native egglog. It uses the existing Cell template operations and
actual source instance. No new marker, fact graph, scalar binding map or per-source
consumer list is added. It follows the state-frontier audit: aliasing a few bound
roots cannot remove the larger duplicated field/index representation.

## Ownership and removed maintenance

`Graph::use_cell_stable_fields` extends scalar-free template projection to every
covered stable fact. Equality fields still read the existing symbolic ports.
Scalar literals come from the original operation; scalar slot operands read the
source Cell's slots, including completed-owner storage. Publication captures an
actual scalar only when that source slot is not already present. Multiple facts
using one slot share its authoritative value. Returned foreign constructors retain
their actual source identity and template; a logical producer is not substituted.

The old per-fact `Stored` hash entry and scalar array are absent. The new path
bypasses their lookup and retirement removal rather than performing a speculative
projection followed by the old index lookup. Moving a source within a composed
Cell therefore requires no cached field-coordinate rewrite. Original source/fact
IDs, type codes, visibility, field wiring and lifecycle records remain live.

Completed sources previously delegated scalar slots to stable facts. That reverse
path is disabled in this mode, as is scalar-provider restoration when a fact is
retired. Otherwise source slots and projected fields would read each other in a
cycle. Enabling after completed scalar delegation/storage is rejected; configure
at a settled boundary before execution. Parent completion, Eq delegation, unrelated
source retirement and source-sized lifecycle restoration remain authoritative.

Borrowed readers use the same source slots. An overlapping worker snapshot captures
only selected candidate rows and their scalar values, then reads its frozen records
by reference. It must not consult mutable live source storage after the coordinator
advances. Snapshot scalar copies, array bytes and source scalar reads are charged.
The common frozen record is larger than the previous scalar-free record; this cost
is reported rather than hidden behind removal of the persistent node index.

## Same-binary memory results

The control already uses scalar-free template projection and completed-owner
storage. The candidate enables Cell scalar ownership on the same program/catalog.
No dual-source catalog expansion is included. Both lanes use a single frozen
`runtime_storage_peak` binary. Results are requested heap bytes, not RSS.

| case | Graph control | Graph candidate | reduction | remaining materialized stable records |
|---|---:|---:|---:|---:|
| fact | 563,487 | 535,367 | 4.99% | 295 → 0 |
| loopfact | 540,013 | 512,765 | 5.05% | 259 → 0 |
| sum-bits | 1,595,091 | 1,486,983 | 6.78% | 1070 → 0 |
| dot-product | 1,491,139 | 1,434,643 | 3.79% | 802 → 0 |

Only the `cells` and `stable_ports` Graph teardown fields change. In sum-bits,
stable field storage drops by 123,766 bytes, while Cell storage grows by 15,658
bytes; net Graph saving is 108,108 bytes. Explicit scalar/other source slots rise
from 3,085 to 3,953. This trade replaces a whole field directory and its arrays,
not just reserved capacity. Fact counts, fact live bytes and completed source-frame
counts remain unchanged. Retained Program heap is exactly equal between lanes,
unlike the prior expanded dual-source catalog.

Process execution peaks also fall, but by less than 0.1% because retained Program
heap dominates these processes. Sum-bits' maximum takeover extra allocation grows
from 11,888 to 15,908 bytes; retain that limitation. Graph savings are 3.79–6.78%,
not the requested reduction to 30% of original runtime egraph size. No speedup,
new skipped RHS application or new saturated-state transition is claimed.

The final memory lanes record node-retirement index probes falling from
67/47/844/336 to zero. New source scalar reads are 3,844/3,457/25,236/15,947 and
missing-slot captures are 61/40/185/134. Overlap validation captures
33/15/386/94 scalar values across the whole execution; combined projection-buffer
peak capacities are 1,920/768/12,384/6,144 bytes. These are snapshot buffers, not
whole-runtime peaks. Bake charges source reads/captures and snapshot copies;
missing counters in an enabled mode fail work-credit parsing.

## Validation and reproduction

All four source programs pass their 2,652 saved Run graph and ordered-effect checks
in serial mode and again in overlapping completion mode, plus terminal checks.
The field-ownership implementation was validated before the subsequent removal of
empty-index probes; that no-op removal was then checked by the focused source and
relocation fixtures. Final memory executions use the updated kernel and match
those verified program IDs, Run counts and final exports. No native-choice proof
scope is broadened and no timing campaign is included.

127 integration tests (47 execution, 64 ownership, 2 borrowed readers, 14 stable
ports), 210 runtime unit tests and six work-credit tests pass. The new fixture
covers scalar literals, copied query inputs, scalar-bearing constructors, completed
storage, union, deletion, subsequent stages and workers. The existing dual-source
fixture now also moves scalar-bearing sources in Cell-field mode, retains the
old suffix transitions, and verifies zero field relocations with exact states.
Runtime no-default-features compilation passes. The mode stays opt-in.

Under the shared compute queue, build `batch_cell_learning` and
`runtime_storage_peak` with `iterative-bake,sparse-cells,storage-metrics`. Freeze
binaries before measurement. With ROOT=`out/cell-bake-owner-merge/batch`:

```sh
batch_cell_learning check-passive ROOT prefix-all cell-fields
batch_cell_learning check-passive ROOT prefix-all cell-overlap
# For each case, both commands use the same frozen executable:
runtime_storage_peak ROOT/prefix-all/CASE/candidate.json ROOT/prefix-all/CASE/source-template-memory.json inherited-owners --port-domains-only --template-fields
runtime_storage_peak ROOT/prefix-all/CASE/candidate.json ROOT/prefix-all/CASE/source-cell-memory.json inherited-owners --port-domains-only --cell-fields
python3 benchmarks/cell-bake-owner-merge/cell_field_results.py ROOT OUTPUT.json
```

Check reports use separate `cell-fields-checked.json` and
`cell-overlap-checked.json` filenames. The analyzer rejects mismatched program,
Run, final-state or fact-storage identities and nonzero persistent stable records.
It preserves complete Graph and Program accounting and overlap costs.

## Ordinary sparse build coverage

A subsequent feature-matrix check found that the new source reader referred to
completed-owner methods even without `storage-metrics`, where those methods do
not exist. The ordinary sparse build now reads its regular source slots without
referencing the optional completed store. The transferred-source admission guard
is likewise conditional; the scalar-delegation guard remains active in both modes.
`cargo check -p eggfuse-cell-runtime --features sparse-cells` and the actual
`cell_field_reads_and_snapshot_values_are_charged` execution test with compiler
features `iterative-bake,sparse-cells` pass through the shared compute queue.
This repairs availability of the representation outside measurement builds;
it introduces no additional memory-saving claim or new timing campaign.
