# Repository workflow

- Validate the minimal CPU branch using the local Cargo compile, run and bench commands in README.md. The debugger and historical experiments live on the research branch. Published site releases require explicit user instruction.

- Maintain Git history as part of completing implementation work: after a coherent change passes its relevant checks, create a focused Conventional Commit with a scope. Report its short commit ID.
- Preserve the immutable `egglog-baseline` tag. Keep local kernel changes, experiment infrastructure, and experiment results distinguishable from the pristine upstream import.
- Inspect the index and working tree before staging. Commit only work belonging to the current task; preserve unrelated changes and do not rewrite existing history without user authorization.
- Do not track build directories, Python caches, generated binary mutation streams, or credentials. Commit the reproducible experiment sources and relevant text results.
- Document whether a result measures a standalone prototype or the actual egglog runtime. Do not describe logical rule matches as committed mutations.

Before optimizing the Cell CPU path, check whether a new iteration can learn from the last catalog's actual executions, which work a scheduled block switch could discharge across Runs, and which typed compiler facts can prove that work redundant. Record the opportunity, the obligations that remain live, and the measured change against the current branch.

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
