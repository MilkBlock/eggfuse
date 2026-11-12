# Real multi-entry Cell completion recognition

This replaces the fixed-six-port teacher with **actual Cell execution and an
independent native egglog reference**. The learned component recognizes a known
completed template from a new entrance structure. It does not execute the
completion, authorize effects, or demonstrate a GPU speedup.

## Data and completion proof

An audit of saved production histories found no usable non-isomorphic entrance
groups sharing a completed structure. Duplicate class IDs were pivot aliases,
repeated paths or self-repetition. We therefore do not randomly split those
events and call the result multi-entry generalization. Audit scripts and their
negative findings are retained in this directory.

`source-rules.json` preserves five unmodified rules from the actual eggcc recipe:
Concat reassociation (133), SubTuple length-one rewriting (137), SubTuple
decomposition (138), Get-to-Single/SubTuple union (143), and adjacent SubTuple
concatenation (144), with original recipe/program hashes. `Input` is a fixture
boundary constructor, not a new production rewrite. The sources use the real
integer primitives and constructor/union effects.

`generate.py` constructs different entry forests: SubTuple alone, Single/Get
forms, differently associated Concats, multiple roots, shared bases and distinct
bases. These are **generated local fixtures using real rules**, not production
traffic or the complete eggcc ruleset. They vary their node sets and sharing;
all constructors are not preallocated in a fixed universe.

The Rust example compiles each source and executes the actual Cell runtime. Two
additional explicit Runs must report no change and preserve all exported rows
and anchors. Native egglog executes the same source independently. For all
**551 cases**, exact canonical constructor DAGs agree between Cell and native.
No rows, visibility flags, tables or equalities are excluded to obtain a pass.
This is a separately defined restricted constructor contract, not the sum-bits
`choice_diagnosis.py` contract and not full-program saturation.

Canonicalization preserves table names, ordered arguments, scalar literals,
sorts, sharing and e-class alternatives; it rejects cycles, hidden rows or
unsupported tables. IDs never define graph equality. Actual initial-to-final
port forwarding is exported, and independently reconstructed through functional
constructor lookup in the native final graph. Input fact preservation is checked.
An independent audit renames IDs and shuffles rows in all 1,653 initial/final/
native graphs and obtains identical canonical graphs.

## Different entrances, shared completions

- 551 cases reduce to 544 distinct initial graphs and 33 exact completion graphs.
- A global, isomorphism-invariant skeleton grouping erases Get/SubTuple scalar
  values while retaining operators, positions, sharing and Input boundary
  identities. Parameter substitutions of the same skeleton cannot cross splits.
- The skeleton hash is only a conservative split mechanism, never a proof of
  completion equality. Collisions keep more examples together.
- Keep known completion classes that have train, validation and test entrances:
  **24 completions, 469 entries, 172 skeleton groups**.
- Split counts: **272 train / 95 validation / 102 test**, with no shared skeleton.
- Retained entries contain 2–12 e-classes, completions 6–15. Node creation and
  actual union forwarding are represented, unlike the preceding fixed graph.

`examples.json` shows three exact completion graphs, each with different train,
validation and test entrances and actual port maps. Root terms define the input
forest; the prediction target is the whole observable constructor graph, not a
distinguished extracted root value.

## What is learned

The encoder reads only the initial DAG. Fixed random real-valued operator,
argument-position and numeric-literal projections are combined bottom-up with
tanh, then pooled. There is no rule application or saturation inside encoding.
Two views produce 210 real features. Training statistics and the 272 nonlinear
projection centers come only from training entries. Ridge fits the final dense
weights; no backpropagation is used.

The output selects one of the 24 known completed templates. Orthogonal dense
target codes followed by a categorical readout are mathematically a rotated
multiclass ridge representation, **not a new continuous completion executor**.
The predicted template stores the completed DAG. An exact constructor lookup
then attempts to embed the entry into that template and returns port mappings.
Unseen completion classes and arbitrary open-boundary graphs are not covered.

Four fixed feature comparisons were explored adaptively. Within each comparison,
validation macro accuracy, then micro accuracy, chooses the nonlinear feature
family and regularization. Across the comparisons, the same validation criterion
selects two structural views. Test results from earlier experiments were seen;
this is exploratory research, not an untouched external benchmark.

| Features | Held entrance top-1 | Macro accuracy | Top-3 |
|---|---:|---:|---:|
| One structural view | 88/102 (86.27%) | 86.52% | 97/102 |
| Two structural views (selected) | **89/102 (87.25%)** | 86.15% | 95/102 |
| Structural view + field moments | 84/102 | 81.99% | 98/102 |
| Cheap typed-field moments only | 32/102 | 45.00% | 58/102 |

All correct selected-template predictions also have the exact actual port map.
The majority-completion baseline gets 3/102. Exact initial-graph lookup hits
0/102, measured and asserted. These results establish nontrivial held-entrance
recognition within this restricted real-rule corpus, **not 90% generalization**.
Two views improve one test answer but slightly worsen macro and top-3 metrics.

## Why it cannot yet skip execution

Five wrong top-1 candidates still contain every initial fact. Containment and
valid port mappings are necessary, not sufficient: a larger graph can contain
unjustified facts. A negative control adds an unsupported Input to a correct
completion; containment passes while exact completion equality fails.

`predict.py` therefore returns `authorized_for_execution: false`. The model is
a candidate recognizer for a shared completion catalog. It does not publish
results, commit union, allocate actual output IDs, or prove that a new entry can
reach the selected dominator. A production takeover needs a compiler-certified
entry-to-completion derivation plus original visibility/lifetime obligations.

## Encoding cost is currently a problem

The two-view run's cold Python structural encoding is roughly twice the
one-view run, for one additional correct test prediction. Cached batched numeric
inference is much cheaper than cold graph encoding. Exact timings for all arms
are recorded separately in `results.json`; they exclude canonicalization, graph
gathering, transfer, routing, proof checks and publication. They are CPU
diagnostics, not an end-to-end or GPU speed comparison.

This encoder scans the entry DAG. It is not yet derived from existing matched
Cell slots or compiled once into an Entry projection. That is the integration
gap: avoid reconstructing an already-known template, expose only dynamic fields,
then compare the complete cost against the work a certified completion removes.
Cheap field summaries alone performed poorly, so discarding structure wholesale
is not supported either.

## Reproduce

Use NumPy from `../cell-real-state/requirements.txt`. Source rules are committed,
so no external worktree is needed. Use fresh output paths. All raw exports and
binary model arrays stay under ignored `out/`.

```sh
cargo build --locked -p eggfuse-cell-compiler --example real_completion_dataset
python3 benchmarks/cell-multi-entry-ridge/generate.py --output out/multi-entry/inputs.json
python3 benchmarks/cell-multi-entry-ridge/collect.py \
  --inputs out/multi-entry/inputs.json --runner target/debug/examples/real_completion_dataset \
  --output out/multi-entry/runtime.json
python3 benchmarks/cell-multi-entry-ridge/dataset.py \
  --runtime out/multi-entry/runtime.json --output out/multi-entry/corpus.json
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-multi-entry-ridge/train.py \
  --corpus out/multi-entry/corpus.json --output out/multi-entry/model \
  --encoder-seeds 20261115,20261116
```

Collection enforces a one-second timeout per fixture and fails on any error;
this limit is not a performance claim. The original collection used a shared
worktree with concurrent runtime changes, so it is not a pinned speed baseline.
Native comparison verifies the resulting graph data independently.

To inspect a new entry export (`{"rows":...,"anchors":...}`):

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-multi-entry-ridge/predict.py \
  --model out/multi-entry/model/model.npz --catalog out/multi-entry/model/catalog.json \
  --graph ENTRY.json --output out/multi-entry/prediction.json
```

Model and catalog are bound by a digest; a mismatched catalog is rejected.
Scores are regression scores, not calibrated probabilities. No runtime source
was changed by this experiment; the Rust exporter is a separate example.
