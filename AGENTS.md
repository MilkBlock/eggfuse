# Repository workflow

- Validate the minimal CPU branch using the local Cargo compile, run and bench commands in README.md. The debugger and historical experiments live on the research branch. Published site releases require explicit user instruction.

- Maintain Git history as part of completing implementation work: after a coherent change passes its relevant checks, create a focused Conventional Commit with a scope. Report its short commit ID.
- In every experiment report, include total model parameters, parameters optimized, complete training Cell Token exposures, and measured training wall time. Separate inherited checkpoints from new training, distinguish repeated exposures from unique experience, and mark unavailable historical measurements explicitly. Report zero new training Tokens and zero training time for frozen comparisons.
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

## Recursive neural Cell generation and verification

Declare the research track and execution mode of each experiment.

- **Neural Execution** applies B2. The generator chooses named proofs from typed, seminaive-visible ports. Its verifier may check only the named evidence.
- **Symbolic Execution** permits compiled exact joins. Charge candidate discovery to the symbolic executor, including in hybrid controls where a network ranks those candidates.
- **Neural Compilation** permits exact execution of proposed and Bake-checked structures. Compare selection with equal-budget compiler heuristics and distinguish offline packaging opportunities from executed takeovers.

Report each track separately when running shared workloads.

Use single-threaded CPU policy inference with the authoritative Rust Cell runtime as
the primary baseline for new neural studies. Train in PyTorch offline and export
the checkpoint and static compiler features. The current two-level forest can
run end to end in Rust using `--forest-policy` and `--forest-inputs`.
Compare with the same Rust runtime using ordinary exact search to measure the
net contribution of neural generation. GPU policy + Rust and GPU policy + Metal
remain explicit controls for model size, batch size and device locality.
[Baseline commands and scope](benchmarks/pass3-cell-gpu/native-forest/README.md).

The research goal is to let the network discover and compose useful derivations
on a real Pass 3 graph, then verify them more cheaply than matching them again.
Iterative Bake supplies shared Cell templates, certified internal wiring and
named boundary ports. The network chooses instances, parents and continuations.
An instance can cite another instance's output port as a premise. One composed
certificate can justify several rule applications when the template proves them.

- **Generation.** Each neural forward consumes its own preceding generated tokens and
  latents. Multiple rows can propose complementary instances and address a
  parent by row, position and port. A source Run defines visibility and effect
  order. The generator can take several waves inside that Run and carry private
  continuations across Runs. Row count, candidate window, wave budget and stop
  policy are experimental choices. State them when reporting a coverage ceiling.
- **Verification.** Support both feedback after a wave and generation of a batch
  in which children cite pending parents. For example, a child may cite the
  output of a Pair proposed in the preceding wave. Check its parent first, reuse
  the verified port, and check the child's remaining boundary conditions. If a
  premise fails or a union invalidates an observation, retire the dependent
  proof and its descendants. Preserve independent proposals and any separately
  supported derivations. Retain source identity, generation, epoch and original
  Run visibility for ordered publication.
- **Stopping.** The model may propose stopping. Closing a source obligation
  requires a coverage proof or explicit exact completion. Carry unresolved
  obligations forward to their legal boundary. On the pure GPU path the CPU
  performs offline Bake and independent post-run audit. Charge all device-side
  exact completion to the exact engine.
- **Evidence.** On full Pass 3, attribute distinct committed RHS bindings to
  their producer after deduplication. Report raw proposals, rejects, duplicates,
  neural winners, exact completions and end-to-end time including verification.
  Check ordered RHS inputs, effective writes, Spine continuations and the final
  graph. Report what happens with exact completion disabled. For a feedback vs
  batch comparison, hold the action library and proposal budget fixed.

The coverage target is at least 98% of distinct committed source RHS occurrences
on each full Pass 3 workload. Record model-issued Cell certificates, actual RHS
ordinals won by each, physical Cell allocations during those bindings, and exact
residuals separately. Reject changes in ordered RHS, effective writes, Spine and
final graph. A verified opportunity ceiling, all-candidate diagnostic, or sum
of independent provider runs does not establish combined neural coverage.
[Source denominators and attribution](benchmarks/pass3-cell-gpu/coverage-target/README.md).
Use the [joint CPU witness study](benchmarks/pass3-cell-gpu/joint-witness/README.md)
for the measured high-coverage deployment. The selective policy may use a
small residual; the certified cutoff has a different recall guarantee. For
physical claims, report fresh ids allocated from the actual verified root or
merge-child recipe and compare with withheld or corrupted recipe controls.

Consult the existing evidence before proposing these mechanisms as new:

- [Pair → Chain](benchmarks/multi-row-generation/README.md) generated children
  from generated parents and audited them afterwards.
  [Same-stage multi-wave generation](benchmarks/multi-row-generation/streaming/README.md)
  measured reuse of actual token history and complementary coverage.
- [Figure 17](benchmarks/multi-row-generation/proof_ablation/README.md) checked
  compiler-composed proofs for neural bindings.
  [Figure 18](benchmarks/multi-row-generation/integral_ablation/README.md)
  exercised private parent/child chains and selective retirement after union.
  [Figure 19](benchmarks/multi-row-generation/stopping_ablation/README.md)
  tested learned stopping against exact outstanding obligations.
- [Figure 56](benchmarks/pass3-cell-gpu/recurrent-generator/README.md) ran a
  restricted neural leaf proposer with exact GPU completion on full Pass 3.
  Its 181/7,265 sum-bits ceiling counts reference winners reachable with its
  32 leaves, eight addresses per leaf and two proposals in one wave per Run.
  A composed certificate or a different wave budget needs its own measurement.
  Identify who generated the bindings whenever reusing a Pass 3 result.

## Neural and Bake optimization metrics

**FEPT requires explicit independent parents.** A qualifying token selects a static
Cell template and names each independent external source fact and its version.
Within a composed template, consume the prior instruction's actual returned
reference. Check original visibility, guards, keys and release order. A determined
primitive or scalar projection may be verified; a verifier that discovers an
unnamed independent parent by enumerating a table, class, bucket, span or
candidate bank invalidates the treatment for this metric.

Use distinct new constructor identities visible in the final export as the
numerator. Charge failed external proposals, separately issued children, and
any additional independent choices. For a larger Cell to earn credit, bake its
ordered wiring before the proposed instance executes, and actually eliminate
its internally determined proposals on the normal execution path. Establish
equivalent ordered source execution independently. Report receiver probes,
full inference and sampled time to common process RSS separately. Class and
family descriptor studies retain their transport-yield results in a separate
series. See the [explicit-parent protocol](docs/EXPLICIT_PARENT_FEPT.zh.md).

The Python-package milestone remains parity with the default vanilla EggFuse
CPU runtime. The matched references and metric definitions are in the
[constructor ledger](benchmarks/pass3-cell-gpu/token-constructor-births/README.md)
and [RSS study](benchmarks/pass3-cell-gpu/verified-wave-rss/README.md).

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
