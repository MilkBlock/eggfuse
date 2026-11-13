# Batched learning over four frozen pass3 inputs

The batch contains `fact`, `loopfact`, `sum-bits`, and `dot-product` from the
checksummed pass3 suite. Each input executes separately. Their traces are pooled
before selecting **one shared catalog**, rather than baking four independent
catalogs or merging their runtime egraphs.

This experiment uses direct typed source compilation without input-specific
marker catalogs. Its per-input unbaked controls therefore differ from the earlier
marked sum-bits configuration. No old memory denominator is silently replaced.

## Identity, selection and proof

The compiler exports existing rule definitions, shared port-program definitions,
and query Entry atom indices. Pooling checks the table contracts and each trace's
source digest. It identifies a rule/port program by its full static definition,
not by its local array index, runtime Cell ID, or eclass representative. Entries
are translated through query atom indices. The input-specific initialization
rules remain distinct.

There are 2,797 different candidate paths, 334 observed on multiple inputs and 99
observed on all four. Each target can map 2,710 candidate paths. The global
selection contains 533 paths, of which 272 were observed on multiple inputs.
All four targets can load that same selection, with remapped local coordinates.
Foreign observations can therefore propose a path the target's training run did
not encounter. Normal typed substitution checks must still prove every hop when
compiling the target; ordinary execution remains available at uncovered edges.

This identity is conservative, exact structural matching. It does not equate
arbitrary alpha-renamed rules or prove that different histories have reached the
same saturated state. Recorded local projections and longer paths overlap;
their credits are not additive savings. All four inputs contribute training, so
this is not a held-out generalization result.

## Remove a duplicate runtime directory

The first batch helped the larger inputs but regressed fact and loopfact. Each
Graph copied the entire compiled transition directory into a HashMap, including
paths never activated on that input. The compiled directory was already sorted
by transition key.

Production now binary-searches that existing immutable directory. Only newly
learned transitions use the runtime overlay. Catalog-first training selection,
shape IDs, actual instance binding, source effects and Run boundaries are
preserved. This deletes 50,184 requested allocation bytes from each candidate
Graph. Retained Program bytes and all other Graph field charges are unchanged;
this is not moving the charge to Program. Lookup speed has not been measured.

| Input | Unbaked Graph bytes | Pooled, copied directory | Pooled, shared directory | Reduction vs unbaked |
|---|---:|---:|---:|---:|
| fact | 803,567 | 828,503 | 778,319 | 3.14% |
| loopfact | 726,057 | 732,449 | 682,265 | 6.03% |
| sum-bits | 2,257,323 | 2,123,571 | 2,073,387 | 8.15% |
| dot-product | 2,199,779 | 2,097,387 | 2,047,203 | 6.94% |

The sum of four separate final Graph heaps falls from 5,986,726 to 5,581,174
bytes (6.77%). This is not a simultaneous combined-graph measurement or a peak.
Program costs are reported separately. Live source-frame counts remain unchanged;
this has not yet implemented replacement of all dominated source instances.

## Validation scope

Forty-two ownership tests and eight Unit specialization tests pass. Five pooling
tests cover reordered program/rule IDs, Entry atom remapping, unseen-path transfer,
incompatible contracts, inconsistent costs and duplicate samples. Runtime checks
compare graph exports, ordered RHS and physical writes at every source Run against
each input's own unbaked control: 418 + 398 + 882 + 954 = 2,652 Runs. The shared
catalog is checked before and after removing the runtime directory copy.

These are standalone Cell runtime regression checks. They do not extend the
reviewed native sum-bits semantic contract to the other workloads, nor establish
native egglog equivalence for this direct-source batch. No timing result or
universal default admission is claimed. The broader egraph compression and
stage-driven RHS objective remains open.

## Reproduction

Use the repository's local Cargo toolchain and target directory:

```
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo build \
  -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics \
  --example batch_cell_learning --example runtime_storage_peak

target/debug/examples/batch_cell_learning prepare workloads/pass3/suite.json \
  out/cell-batched-learning fact loopfact sum-bits dot-product
python3 benchmarks/cell-batched-learning/pool.py out/cell-batched-learning
target/debug/examples/batch_cell_learning apply out/cell-batched-learning
target/debug/examples/batch_cell_learning verify out/cell-batched-learning
python3 -m unittest discover -s benchmarks/cell-batched-learning -p test_pool.py
```

Run `runtime_storage_peak` on each input's `baseline.json` and `candidate.json`,
using `inherited-owners --port-domains-only`, to reproduce the current heap
columns. The copied-directory column requires the pre-change runtime; its saved
reports are preserved as `candidate-copied-directory-heap.json`. Generate the
tracked small report with `summarize.py ARTIFACT_ROOT OUTPUT.json`. Generated
programs, full traces, binaries and Python caches are not tracked.

## Completed scalar bindings (follow-up)

The frozen shared catalog exposes duplicate retained state: Eq slots already
read composed symbols, but scalar operands were still held both in source slots
and stable constructor fields. Completion now derives `(slot, operation, column)`
projections from the original typed constructor instructions and Copy aliases.
Only immutable primitive scalars are admitted; container values and mutable
function reads are not recomputed. The existing execution plan holds this static
layout, without changing port-program identity or keeping another binding map.

A completed instance removes an explicit slot only after finding an actual local
stable constructor field with the same value. A reused foreign constructor does
not supply a synthetic local address. Parent handoff can use the same projections.
Before retiring the final provider of a delegated slot, the runtime restores its
value; completed shared storage is unsealed when necessary. Other live providers
avoid that restoration. This uses static template wiring, not consumer lists.

The same four candidate artifacts, without retraining, give:

| Input | Prior Graph bytes | Scalar delegation | Explicit slots before → after |
|---|---:|---:|---:|
| fact | 778,319 | 775,343 | 1,190 → 1,066 |
| loopfact | 682,265 | 679,001 | 1,158 → 1,022 |
| sum-bits | 2,073,387 | 2,057,283 | 3,989 → 3,276 |
| dot-product | 2,047,203 | 2,035,803 | 3,954 → 3,479 |

The final parent-link counts remain 89, 76, 216 and 231: this does **not** retire
the dominated source instances. Sum-bits elides 731 scalar slots over execution
and restores 18 on retirement; the other inputs restore none. The added compiled
layout costs 12,608 retained Program bytes per input, separately from Graph.
Runtime costs include provider lookups, a temporary list at completion, and
restoration/unsealing at retirement. No latency benefit is claimed.

The batched verifier now disables completed-parent takeover on the control lane,
so both sides cannot mask the same delegation error. All 2,652 source Run graph,
ordered-RHS and physical-write comparisons pass. The 44 ownership and 8 Unit tests
include retirement after shared-owner transfer, surviving child reads, worker
execution, and retaining an alternative scalar provider until the last retires.

The previously accepted **marked** sum-bits artifact separately falls from
2,477,174 to 2,460,662 Graph bytes, with the same final-state digest as its reviewed
saved export. The saved-export `choice_diagnosis.py` gate passes. This is a
final-state check, not a new native Run-boundary proof for the unmarked batch.

Reproduce by rebuilding the two examples above, running `verify`, and measuring
the unchanged candidate artifacts with `runtime_storage_peak ... inherited-owners
--port-domains-only`. Results are in `scalar-results.json`; the earlier directory
and batch measurements are intentionally retained as their own controls.

## Physical owner completion across Runs

The previous physical transfer collected only ordinary Cells, requiring two or
more eligible sources. Once two earlier frames had transferred, a single later
stage could not join their backing owner. The composed port shape grew, while
storage completion stopped at the earlier stage.

Transfer now includes the component's existing completed frames. A later Run
can absorb one new frame into the existing owner, preserving each original
logical ID, metadata, scalar binding, and live fact state. The old owner is not
unsealed into ordinary Cells just to assemble the new one. Complete coverage of
all participating owner slices is checked before mutation. Dead fact holes are
omitted when moving the backing arrays; missing facts stay missing. External
readers no longer disqualify an otherwise complete, parent-free source: their
stable logical references already support completed storage and retirement
fallback. Sources that themselves still require a parent remain ineligible.

The new work is charged explicitly: extension events, newly absorbed frames,
referenced frames, merged owners, and old slot/fact entries moved. This is a
storage takeover at a settled source Run boundary, not an earlier publication or
permission to skip a rule. Repeated transfer of an unchanged owner is a no-op.

Testing caught allocation cliffs in **both** completed-frame and owner-header
Vecs. Enlarging the eligible population could double either directory and lose
the memory benefit. Both now grow normally at small sizes and in increments of
128 records thereafter; IDs and record formats are unchanged. Temporary arrays
still exist during extension and are included in the heap high-water sampling.

`owner-takeover-results.json` compares the fixed catalog against scalar delegation
alone, including independent source-record counts, actual Graph bytes, temporary
takeover peaks and work. Program storage is unchanged. The earlier native scope
limitations still apply. All 2,652 source Run graph/RHS/write checks pass for the
new takeover and live-reader eligibility, alongside 46 ownership tests, 8 Unit
tests and the low-level owner-extension lifecycle test. Directory growth is an
allocation-only change; the final measured exports match the saved controls.

Reproduce the report after the saved before/after heap runs:

```
python3 benchmarks/cell-batched-learning/takeover_audit.py \
  out/cell-batched-learning benchmarks/cell-batched-learning/owner-takeover-results.json
```

This still retains logical source metadata and fact records inside the shared
owner. It has not contracted internal parent lifetimes or achieved the 30% runtime
egraph target. The saved final trace now includes parent references, retainer
counts and physical-storage kind. Most remaining parent-free sources are in
single-frame components (195, 186, 589, 669); improving their composition coverage
is a larger opportunity than further header packing. There are also 37, 29, 80,
104 observed within-component cross-stage parent links. Those observations alone
do not prove that the parent states can be retired: typed Entry projections,
actual result ownership, external readers and lifecycle preservation remain live
obligations for a future internal-parent contraction.

Final Graph bytes for the four fixed candidates are respectively 759,727;
674,105; 2,043,955; 2,009,467: 60,176 fewer bytes in the sum of separate final
heaps. Ordinary source records fall 495→461, 469→438, 1,251→1,116 and 1,338→1,211
(327 fewer), while logical source and fact counts remain unchanged. The marked
accepted sum-bits artifact separately falls 2,460,662→2,447,294 bytes and
1,580→1,397 ordinary records. Its final digest still equals the reviewed saved
export, and the saved-export semantic gate passes. These are incremental gains,
not a claim of large egraph compression or faster RHS execution.
