# Historical entry coverage and synthetic-only training policy

**Policy update:** future model fitting uses only randomly generated legal local
Cell inputs. Real Eggcc Runs are evaluation/audit data, not training data. The
real-program fits below were completed before this decision and are historical
controls, not the prescribed training pipeline. The second-entry captures were
not fitted. GCD and LCM are development evaluations, not untouched test sets.
Reserve new real programs for final evaluation.


This experiment is a standalone, three-rule GPU Cell-family prototype. It does
not implement the entire Eggcc stage schedule or authorize learned unions.
The intended runtime still generates Cell tokens until the current Run reaches
its fixed point, then advances through the original stages. CPU reference labels
are offline supervision, not future GPU inputs. No backpropagation is used.

## Collection

`select_completion_training.py CORPUS EXCLUDE OUTPUT` selects unseen original
training programs using audited application coverage of rules 283 and 293,
ordered by observed binding count. Saved CPU reference execution must be at most
one second. It checks trace/program hashes and reference/control-flow audits.
Neither validation labels nor validation scores select programs.

`collect_boundary_training.py TRAINING CORPUS BINARY MODEL ARTIFACTS OUTPUT
--cases 013-factors,041-leibniz --boundary-rule 293` captures before the first
Single continuation. Repeat in a separate artifact directory with
`--boundary-rule 290` for the next Get entry. Collection records actual current
boundary features, ownership witnesses and independently checked final labels.
Existing graph, Run and query checks remain authoritative.

Both first entries produced only eight samples (six generated-source) each,
with zero dynamic Eq positives. Training increased from 129 to 145 observations
but the existing exact-source validation predictions did not change. Increasing
program count is not sufficient evidence of useful context coverage.

The trainer now allows distinct snapshots of one training program while rejecting
cross-split program reuse, repeated entries and repeated validation programs.
Identical feature/target rows within a program are counted once. Identical inputs
with conflicting targets are retained and reported, rather than silently relabeled.
Different programs remain independent evidence. Deduplication alone reduced the
original training population from 129 to 125 and left validation choices unchanged.
Counts are representation-level exact duplicates; they do not claim semantic
canonicalization or independence of overlapping contexts.

## Active construction next

Construct legal bounded local inputs from the existing Cell/rule definitions,
not random floating token vectors. Vary typed port aliasing, initial Eq partitions,
scalar values near guard boundaries, and shared neighboring Cells. Materialize
through the ordinary constructor semantics, then use the original exact rules to
obtain completion labels. All features must come from the pre-completion input.

Prioritize paired cases with the same selected source Cells but one changed
external relationship. Balance positive/negative completion outcomes. Rank a
training-only candidate pool by ridge score margin, disagreement and novel
canonical input structure. Keep a uniform component so uncertainty is not the
only source of data. Existing direct-source failures motivate the generator;
held-out program values and labels must not be copied into synthetic training.

Canonicalize local structure to avoid counting renamed IDs as new examples.
Split by generating seed/structural family before fitting. Record whether each
case is merely rule-valid or has a trace establishing Eggcc reachability.
Bounded templates do not imply finite unbounded scalar/instance combinations.
Synthetic gains must be tested on unchanged real-program captures, followed by
actual predicted-token feedback. An offline exact-source improvement alone is
not a closed-loop result.

## Bake relationship

Inspected adjacent Bake revision b066509b: terminal constructor writes can reuse
an actual matched witness only with ownership, visibility, forwarding and dirty
repair checks at the original effect boundary. Nontrivial unions remain live.
That CPU takeover has not been ported by this collection change. GPU feature
construction must preserve these same distinctions rather than equating a
producer/op address with the actual returned result owner.

The second-entry collection passed for both programs: 013-factors 17 samples (7 generated-source), 041-leibniz 16 samples (6 generated-source). These archives remain outside future training.
