# Completion targets carry source control

A local completion target depends on the remaining source execution contract.
The fitter now resolves each capture's explicit source control and rejects mixed
contracts before fitting. New head reports carry `completion_control`. GPU head
admission checks that contract for default as well as explicitly supplied schedules.

Legacy artifacts established only saturation of a single source ruleset. They
resolve to that explicit contract; absent metadata never establishes multistage
coverage. Unknown stage names and a mismatch between head and requested order
are rejected. Structural schedule equality is deliberately conservative: this is
not a solver for equivalence of arbitrary schedules. Bake may eventually prove
contracts interchangeable, but sample-level equality is not such a proof.

No new per-instance facts, binding copies or reverse lists are added. This is a
correctness boundary, not removal of runtime work or evidence of acceleration.
The representation still lacks general conditioning on remaining execution
history; separate contracts prevent silently contradictory supervision meanwhile.

## Actual order contrast

The same generated context/canon input was executed in both orders on the GPU.
Both pass all per-Run/final graph, complete matching and lowering audits. Forward
order has nine Cell samples (four generated-source); reverse order has eight
(three generated-source). Each independently generated label archive records its
actual order rather than saturating all rules together.

The two final graphs are equal for this particular sample: 15 facts, 16 mapped
classes under stable seed anchors. Thus this experiment does **not** demonstrate
different final labels for a common binding. It demonstrates different execution
and sampling paths to the same completed structure. The independent F→G→H test
also covers a case where reversing stages really does omit a final fact.

The 25-context synthetic-only training regression produces bit-identical head
arrays to the existing result-ownership model; the new report explicitly names
`saturate(context)`. No new accuracy claim or model promotion is made. Seventeen
control, scheduler and classifier tests pass.

## Current iterative Bake findings

Inspected aedc2707 (`retain uncompiled cross-stage execution lineage`). Its
empty-catalog discovery path now retains actual selected and completed Entry
lineage, including worker-owned answers. The report counts 2,062 additional
completed parent links, 835 crossing rulesets. It explicitly does not turn these
observations into compiled hits or create a second binding graph.

The typed compiler's post-Run analysis identifies 47 distinct saturated candidates;
much observed support needs three- or four-stage suffixes. This is useful guidance
for synthetic **structural** family selection, not permission to train on observed
program bindings. GPU input generation should compose typed suffixes and preserve
actual owner/lifetime requirements across those boundaries. Current two-stage
support is not completion of that work. No adjacent CPU code was merged here.

Full original Eggcc execution, general learned Cell matching/completion, efficient
GPU representation and applied CPU repair remain outstanding.
