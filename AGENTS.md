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

## Recursive neural Cell generation and verification

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

Prioritize two outcomes on equivalent source executions. Measure time from
inference entry to a common, independently calibrated process RSS threshold,
and measure **FEPT**, final-visible new constructor origins per externally issued token.
For generative actions, separately charge feedback, failed model/prototype choices
and verifier expansion, so transport FEPT cannot be mistaken for neural work efficiency. Record
entry RSS, absolute and incremental crossings (including already reached and
unreached thresholds), peak RSS, and how many speculative members were later
redeemed or retired. Keep full inference latency as a secondary metric.

Report both first constructor publications and the subset whose original source
identity remains visible at final export. Count unique original fact references,
excluding the input graph, duplicate constructor requests and function writes.
Charge rejected root packets and separately issued child packets in the external
denominator. Report committed-root yield separately. Cross-Run attribution to
an ancestor is useful lineage evidence. Credit a composed token with eliminating
external packets only when the executor really suppresses them while the
verifier preserves the original release and visibility semantics.

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
