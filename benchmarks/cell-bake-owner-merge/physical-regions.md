# Physical segments are not completed Cell regions

The previous region census described logical composition and actual fact
membership, but omitted the physical segment holding each completed source.
`completed_regions` now exports that relation after execution: shared source
layouts, source-to-owner addresses, slot/fact offsets, source epochs/depths,
owner extents and actual record sizes. Layout labels are deterministic and omit
instance values. No runtime directory, bindings, history or subscriptions are
added. The export requires `storage-metrics` and is outside inference.

The offline join checks source metadata against the existing lifecycle census,
source identity uniqueness, exact completed-source coverage, owner counts,
non-overlapping bounded ranges, fact membership and each owner's live-fact count.
It preserves dead ranges and missing facts rather than treating allocation as
proof of live membership. A Rust regression checks shared layouts, distinct
source epochs and unchanged sibling offsets after one source restores. Four
Python tests cover mixed logical ownership, holes, retired fact positions,
overlapping ranges and missing/inconsistent source metadata.

## Observed placement

| case | completed sources | physical owners | owners spanning logical Cells | sources in those owners | logical Cells split across owners |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 752 | 292 | 66 | 469 | 126 |
| loopfact | 689 | 246 | 56 | 444 | 106 |
| sum-bits | 2,177 | 907 | 177 | 1,285 | 423 |
| dot-product | 2,122 | 850 | 161 | 1,256 | 328 |

This is expected from bounded singleton pooling and suffix-only extension.
Pooling shares allocation headers across unrelated logical Cells. Later growth
adds a suffix segment rather than moving all earlier sources. Both decisions
saved measured work in earlier experiments; they also mean a physical owner
cannot now be interpreted as one saturated Cell or one source stage.

The actual completed source record is **48 bytes**, and an owner record is
80 bytes on this 64-bit build. These sizes must not be confused with the earlier
result-handoff frame sizes. Sum-bits has 436 slot positions and 238 fact positions
outside all surviving source ranges, plus retired fact positions inside surviving
ranges. These are retained holes, not additional live facts. There are still
37 externally retained completed sources, so dropping their source identity is
not justified by completion or allocation sharing.

## Rejected shared physical-header design

A specific candidate would move each source's layout pointer and two offsets
into a shared physical-region descriptor, add an ordinal to each source, and add
one descriptor pointer to each owner. The model charges three 8-byte descriptor
words per unique source position, an 8-byte ordinal per source, and an 8-byte
handle per owner. It leaves all values, source epochs, depths, identities,
owner addresses and lifecycle storage intact.

| case | distinct physical layouts | source positions in those layouts | modeled net payload saved |
| --- | ---: | ---: | ---: |
| fact | 126 | 539 | -3,240 B |
| loopfact | 136 | 552 | -4,192 B |
| sum-bits | 318 | 1,452 | -7,272 B |
| dot-product | 246 | 1,321 | -4,552 B |

Negative savings mean **additional** bytes, even before charging the new registry,
allocation headers, padding and spare capacity. This rejects this particular
factorization of existing physical groups. It is not a lower bound on all Cell
representations and does not reject logical template regions. Implementing the
candidate would add complexity without removing enough state.

A further structural takeover must select its logical template region and
source-stage mapping before choosing storage ownership, preserve actual foreign
results, and specify source-sized restoration. It cannot infer those properties
from today's pooled owner or equate a missing source range with a dead symbolic
origin. No new source retirement, rule skip or state-switch RHS is implemented
by this audit.

## Execution scope and reproduction

Compute job 221 runs the Rust regression and builds the snapshot executable with
`iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit`.
Job 222 runs the four offline tests and one sequential four-case snapshot batch,
using unchanged `prefix-all` artifacts and `inherited-owners --port-domains-only
--cell-fields`. Each snapshot's Program ID, Run count and terminal state hash
matches its saved source-field control. This is final-state differential evidence,
not a fresh per-Run/native semantic proof or a timing campaign.

Full Graph-owned teardown bytes remain exactly 535,367 / 512,765 / 1,486,983 /
1,434,643. The diagnostic did not compress the Graph. The large-compression goal
remains open.

Freeze the newly built `runtime_storage_peak` binary, then for each of fact,
loopfact, sum-bits and dot-product, run under the shared compute lease:

```sh
runtime_storage_peak out/cell-bake-owner-merge/batch/prefix-all/CASE/candidate.json out/cell-physical-regions/CASE.json inherited-owners --port-domains-only --cell-fields
python3 -m unittest discover -s benchmarks/cell-bake-owner-merge -p test_physical_regions.py
python3 benchmarks/cell-bake-owner-merge/physical_regions.py out/cell-physical-regions benchmarks/cell-bake-owner-merge/physical-regions.json
```

The compact JSON records exact input snapshot hashes. Raw snapshots, the frozen
binary and `provenance.json` remain under the ignored experiment directory.

## Retired source values no longer wait for unrelated siblings

The physical-range audit led to an actual lifetime fix. `retire_completed` removed
the source address, but kept that source's values inside a shared owner whenever
another source remained alive. Consequently Text/Set/Key payloads could remain
strongly referenced even after the source was unreachable. Dropping the last
owner eventually released them; this was unnecessary lifetime retention, not a
permanent allocation leak.

Retirement now clears only the removed source's slot range. The last-owner path
still drops the entire allocation directly. Source restoration already moves
values into the restored Cell before retirement, so clearing its old range does
not destroy the restored values. Graph retirement still requires zero facts and
zero external parent references. No sibling offsets, values or backing addresses
change; no enclosing Cell is materialized. Array holes remain allocated, and
shared values with other legitimate owners naturally remain alive.

The regression first failed on the old runtime: an Arc weak reference could still
upgrade after one of two pooled sources retired. It now proves that the source's
heap object is released while the sibling's address/value and shared array size
are unchanged. Four completed-storage and ten fact-lifecycle tests pass. The
`retired_slot_clears` census counter charges every slot cleared, including slots
already moved during restoration; it is work, not saved bytes. No new workload
memory percentage, speedup or large-compression claim is made for this fix.
