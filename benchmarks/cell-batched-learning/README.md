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
