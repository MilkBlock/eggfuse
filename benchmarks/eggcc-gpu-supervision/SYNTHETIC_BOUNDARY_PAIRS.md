# Controlled initial Eq pairs

The previous generator reused a random number of same-sort ports. Changing its
reuse probability with the same seed also changes random-number consumption, so
that is not a controlled one-relation experiment. This experiment instead makes
one no-random-sharing base and adds exactly one explicitly recorded, same-sort
initial Eq. Constructor closure can change several rows as a consequence.

`synthetic_boundary_pairs.py synthetic-context-recipe.json ARTIFACTS` produces
four pairs (seeds 20261200–20261203), selected without validation labels or
completion outcomes. Each base contains four rule-query fragments. The paired
side keeps exactly those fragments and scalar values; only the recorded Eq and
mandatory canonical constructor closure differ. The replay validator checks the
base seed and the explicit merge. Unknown IDs, different sorts and self-merges
are rejected. Base and paired sides are both training-only, not independent
holdouts. This generator still does not establish source-program reachability.

All eight inputs pass the actual GPU family runner, complete-match audit and
per-Run/full graph checks. They use the existing Cell token importer, generated
source consumption and physical ownership path. CPU labels are post-execution.
No backpropagation, real Run training, new runtime fact graph or per-producer
consumer list is introduced.

With alpha 10 and the same readout/features, compare the original 11 synthetic
inputs plus four base inputs against those inputs plus the four Eq variants:

| Training | GCD all/direct | LCM all/direct | Expanded false pairs GCD/LCM |
| --- | --- | --- | --- |
| Original 11 | 21/41, 14/26 | 45/99, 35/78 | 98 / 207 |
| Plus base | 20/41, 13/26 | 52/99, 33/78 | 95 / 161 |
| Plus pairs | 22/41, 14/26 | 55/99, 35/78 | 88 / 150 |

These are offline exact-source state predictions, not a predicted-token rollout
or full Eggcc result. The model remains unpromoted. Four added samples sets are
small, and the comparison changes sample count as well as coverage; it does not
prove a general advantage of paired sampling. The useful result is a controlled,
replayable way to vary a boundary condition and produce actual GPU witnesses.
A matching-but-unproductive entry is also different from an absent query match;
this experiment does not yet train a readiness/match head on rejected candidates.

## Current Bake evidence

Inspected `codex/cell-parallel-admission` at ace4f4c4. Composed constructor Set
routes now consume actual result witnesses through the existing key proof or a
full current-key check. Stale evidence falls back; nontrivial unions remain.
Its reuse catalog saves 37 domain queries but adds 373 route probes and 4,968
Program bytes; these counts are not a speedup. No CPU changes were merged here.

For GPU synthesis this identifies an additional needed contrast: a result
already owned by another Cell, versus a result requiring a real merge. An initial
Eq alone is not a substitute for exercising actual returned-result ownership,
visibility and key compatibility across stage boundaries. The current three-rule
single-stage prototype and its runtime guards remain unchanged by this experiment.
