# EggFuse preprint

Title: **EggFuse: Exploiting Locality in E-Graphs**.

This revision imports the manuscript sources from `929aa61c`
(`codex/eggfuse-inference-paper`) and expands the architectural account beyond
iterative Bake. `architecture.tex` describes Cell templates and instances,
Shared Entry, ordered effects, completion/publication, optional parallel queries
and the offline learning loop. Historical results retain their original revisions
and semantic limitations; they must not be attributed to the current engine.
Historical evidence sources remain on that branch under `paper/evidence/`, and
native replay records at `b89129cc` under `docs/papers/eggcc-cpu-techreport/`.

The current 96 × 3 eggcc replay is documented in
`../benchmarks/eggcc-suite/README.md`; its table retains the old per-pass format.

A separate paired native 2.0/3.0 release comparison is documented in
`../benchmarks/egglog3-suite/README.md`; it uses the same captured inputs and
reruns both native versions. Its table is distinct from the earlier Cell replay.

The new unmodified upstream `.egg` audit is documented in
`../benchmarks/upstream-suite/README.md`. Its results have an explicit final-state
contract; they are not a proof of complete egglog language or proof-mode support.

Build from this directory:

    latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=dist main.tex

The title, byline and submission metadata remain editable in `main.tex`,
`authors.tex` and `submission.txt`. From a repository checkout, build the PDF, package all manuscript sources (including
both `workloads.dat` and `current-workloads.dat`), and verify that the archive
builds independently:

    python3 package.py

Outputs are `dist/eggfuse.pdf` and `dist/eggfuse-arxiv-source.tar.gz`. The archive
includes current benchmark text records and drivers under `anc/`; it excludes
binaries, generated caches and large graph exports. Running those benchmark
drivers requires the repository, whereas building the manuscript requires only
the source archive and a TeX installation. Historical evidence remains at the
pinned locations above. No arXiv upload is performed by this task.
