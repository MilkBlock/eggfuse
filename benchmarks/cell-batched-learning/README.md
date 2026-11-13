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
