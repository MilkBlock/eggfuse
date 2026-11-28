# Repository workflow

- Validate the minimal CPU branch using the local Cargo compile, run and bench commands in README.md. The debugger and historical experiments live on the research branch. Published site releases require explicit user instruction.

- Maintain Git history as part of completing implementation work: after a coherent change passes its relevant checks, create a focused Conventional Commit with a scope. Report its short commit ID.
- Preserve the immutable `egglog-baseline` tag. Keep local kernel changes, experiment infrastructure, and experiment results distinguishable from the pristine upstream import.
- Inspect the index and working tree before staging. Commit only work belonging to the current task; preserve unrelated changes and do not rewrite existing history without user authorization.
- Do not track build directories, Python caches, generated binary mutation streams, or credentials. Commit the reproducible experiment sources and relevant text results.
- Document whether a result measures a standalone prototype or the actual egglog runtime. Do not describe logical rule matches as committed mutations.

Before optimizing the Cell CPU path, check whether a new iteration can learn from the last catalog's actual executions, which work a scheduled block switch could discharge across Runs, and which typed compiler facts can prove that work redundant. Record the opportunity, the obligations that remain live, and the measured change against the current branch.

## Cell unification direction

- Use Cell templates and their actual instances as the common structural
  representation for query completion, execution and iterative Bake. Shared
  Entry projects the existing instance slots into a consumer's query. Derive
  established facts from the template's matched inputs and completed operations;
  do not introduce a parallel runtime fact graph or a second copy of the bindings.
- An independent source marker relation is optional materialization, not a
  required intermediate representation. Keep `.egg` marker emission available
  where useful for native comparison or measured sharing. Do not require new
  markers merely to expose information already available through a Cell Entry.
- Template assumptions need evidence from a successful match or completed
  operation. Actual returned values may refer to an existing constructor owned
  by another Cell; `(producer Cell, operation)` is not a universal result address.
  Preserve residual enumeration, late-input and union-enabled matches, delta
  ownership, visibility and any necessary retirement/generation checks.
- Keep ordinary query atoms, effect instructions, existing Entry projections
  and source Run boundaries authoritative. Constructor facts, equality tests,
  scalar guards and mutable reads are properties of those operations, not four
  additional maintained representations. Reuse existing lifecycle metadata.
- Bake composition must derive consumer Entries and any materialization
  boundaries from the same Cell definitions. A newly combined Cell must be able
  to replace an intermediate handoff and its maintenance, not only add another
  execution catalog over a fixed marker layout. Preserve original Run/effect
  ordering when crossing stages.
- For each implemented takeover, identify and remove the redundant query,
  binding, history/receipt or publication work within its proven coverage.
  Template-internal connections remain static wiring; do not recreate them as
  per-producer consumer lists. Charge uncovered boundary work and new storage
  or dispatch costs. Count a saved operation only once across marker and Cell
  paths. A specification, shared registry or new counter alone is not a completed
  takeover or evidence of a speedup.

## Semantic acceptance

- Use `python3 benchmarks/marker-handoff/choice_diagnosis.py ARTIFACT_ROOT OUTPUT.json`
  as the semantic acceptance entrypoint for the reviewed sum-bits final-state
  contract. Follow `benchmarks/marker-handoff/choice-diagnosis.md` for inputs and
  proof coverage. Reuse saved exports during development; do not turn this
  check into an unsolicited performance campaign.
- Accept only `status: pass` / exit 0. `difference` / exit 1 fails the stated
  acceptance conditions; `inconclusive` / exit 2 requires investigation or an
  extension of the proof rules. Missing inputs, unsupported source contracts,
  unknown identities and equal cost alone never establish a pass. Do not run
  the validator with Python `-O`.
- Require exact core equality and visibility, legal current minimum-cost
  extraction candidates, supported term equivalence, and legal maximum-size
  hoist choices. Allow the proven Add/Mul-equivalent extraction ties and legal
  hoist tie choices to differ in encounter order.
- Keep strict whole-graph comparison as a separate determinism diagnostic.
  Its failure due solely to validated choices is not a semantic rejection.
  Changes affecting scheduling, deletion or cross-stage visibility still need
  the relevant Run-boundary checks; final-state acceptance does not replace them.
- For other workloads or source changes, first validate and explicitly extend
  the supported contract. Never broaden the table exclusions or equational
  rules merely to make a failing comparison pass.

## Cell Foundation Model experiment tracking and storage

- For architecture or learning-capability comparisons, use at least **500,000 complete Cell Token training exposures per model**. Count full targets actually consumed by that model. Shorter runs are implementation, equivalence, or throughput checks only. Report unique native states, distinct state × complete target pairs, repeated optimizer exposure and actual training time separately.
- Every training entry point, including architecture pilots and resumed jobs, must write a local SwanLab live run with actual cumulative complete Token exposure as the step. Log Train CE, validation CE when evaluated, LR, pre-clip gradient norm, total parameters, observed forward and backward connected parameters, unique training states and targets, optimizer updates, elapsed training seconds, Token/s, and sampled forward, backward and optimizer times. Record the objective separately if it differs from CE. Sample from the CPU side or existing measurements to avoid per-Token logging and device synchronization.
- Record Git revision, data version, model and optimizer configuration, seeds and checkpoint paths. Verify the run in the **served SwanLab API** with a current step and readable metrics. Provide the direct live link. A JSONL file on disk alone does not establish dashboard visibility.
- On every 10K exposure crossing, evaluate the actual post-update weights asynchronously in the native Runtime on loopfact with generation seeds 193 and 307 and a 256-paid-request budget. In the same live run, write Coverage, EPT, EPS, Continuation EPT and actual paid count under the corresponding native_256 prefix. Use actual exposure, including batch overshoot. Preserve failures, shortfalls and undefined continuation metrics. Never interpolate missing checkpoints.
- For milestone comparisons, retain native results by program, generation seed and budget (16, 32, 64, 128, 256 paid requests and full schedule), including actual paid tokens, terminal facts/graph, rejection and duplicate counts, and separate Primitive/Higher outcomes where observed. State the scope of any reduced matrix; distinguish live checks, offline diagnostics and formal native execution. Keep source ledgers and weights authoritative.
- Store **all new experiment data on the mounted external SSD**: training corpora, replay data, temporary native worlds and exports, caches, journals, SwanLab databases and run files, checkpoints, profiles, and raw results. Use `/Volumes/Extreme SSD/eggfuse-experiments` for bulk artifacts. For SQLite and large populations of tiny files prefer the external APFS mount `/Volumes/EggFuseWorkspace` (backed by `/Volumes/Extreme SSD/Development/EggFuseWorkspace.sparsebundle`). Set TMPDIR and tracking paths **before** starting Python, native workers or dashboard processes. Verify the actual mount, resolved paths and available space before launch. If the external volume is absent or lacks space, stop before writing; never fall back to the internal disk or create a directory masquerading as a missing mount. Only reproducible source and compact reviewable text results belong in Git. Preserve existing archives and active training state.
