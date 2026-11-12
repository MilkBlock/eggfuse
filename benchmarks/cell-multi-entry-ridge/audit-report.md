# Read-only audit: real multiple-entry completion evidence

The historical sum-bits `cell-history.json` exists at the supplied 7c16 worktree
path. Its program/recipe checksums bind a bounded retained history, not a complete
run log. Inventory: 2,048 retained events, 380 dropped events, 134 direct truncated
parents, 723 retained parent links; 121 implementations in 119 completion classes,
23 implementations with canonical port maps, 9 exact prefix extensions and
77 catalog transitions. The 39 sampled applications are latest retained examples,
not 39 exhaustive rule applications or committed graph mutations.

There are only two classes with more than one implementation:

- Class 25: rule 103 pivot 0 alone, versus rule 103 pivot 0 repeated through
  output 0. Units 25/52 have 47/1 retained events. The longer path carries the
  identity port extension and exact completed inclusion. This is repeated
  self-completion, not two distinct rules discovering a shared completion.
- Class 75: rule 426 pivot 1 versus rule 426 pivot 0, units 76/100 with 10/28
  events. Canonical query/effect port maps coincide. This is a genuine alternate
  query entry for the same rule, but no alternate rule-route discovery.

The newer local `out/cell-trail-review/structures.json` describes 141 paths:
11 flat, 87 staged and 43 opaque. The 98 supported paths have 98 distinct exact
structures. There are **zero** repeated full completion structures. Sharing
302 stage occurrences into eight stage structures in the companion export is
shared stage storage, not evidence that those 98 completed paths are equivalent.

## Contract boundary

`engine/cell-runtime/src/iterative.rs::completion_contracts` groups supported
flat structures by exact structural equality; assumptions remain part of the
key. `cell_completion.rs::extension` verifies an exact prefix port mapping and
inclusion of completed facts, and requires consumer match assumptions to be
established separately. It rejects prefixes containing terminal/constructor
unions. The current staged fallback preserves exact stage/order contracts;
it does not establish that distinct ordered paths reach the same saturated
state. Opaque classes retain source identity and provide no structural proof.

Thus the two small duplicate classes support a smoke test for alternate-entry
projection and self-idempotence. They do not support a credible train/validation/
test split for learned generalization across different completion structures.
Splitting their 86 events randomly would mostly duplicate the same structural
labels across sets. Hold out entire canonical structures or source instances
with complete provenance; report whether unseen entries of a known structure or
unseen structures are the actual task. Neither contract is adequately populated
by this dataset alone.

## Minimum additional offline exports

No new runtime fact graph is needed. Extend the compiler/history diagnostic
export from existing Cell definitions and successful apply evidence with:

1. Exact canonical completion structure, supported effect/Run ordering and a
   stated finite closure rule domain. If saturation is claimed, include a
   checked no-pending-applicable-rule certificate within that domain.
2. Each distinct admissible entry's assumptions and exact mapping into that
   shared completion structure; preserve rule/pivot only as provenance, not as
   the prediction label. Export required extra assumptions explicitly.
3. For each proved extension, source/target structure identities, complete port
   map and precise newly established facts/effects. Keep consumer-match and
   visibility obligations visible instead of treating inclusion as activation.
4. Successful instance bindings in canonical port order, actual returned result
   references, generation/visibility and original Run boundaries. Existing
   history exports have witness identity but not full bindings, so they cannot
   presently label a numeric instantiated-state completion dataset.
5. Complete-lineage or truncation flags, source workload/seed identifiers and
   counts of failed candidates when studying selection. Positive retained apply
   samples alone cannot label impossible completions or quantify false positives.

First collect multiple nontrivial proved entry routes into several shared
completion structures. Then split by complete provenance/structure, retain
exact held labels, and train ridge from those real contracts. Catalog IDs,
common rule suffixes and shared stage nodes must never substitute for the
missing equivalence proof.

`audit.py` reproduces the counts; `audit-results.json` retains both duplicate
classes, their maps, counts and source hashes. No runtime code was changed.

## Completed-only isomorphism follow-up

Class counts alone are insufficient: the current class key includes assumptions,
whereas distinct assumptions may reach the same completed graph. Therefore
`audit_isomorphism.py` separately canonicalizes completed facts, ignoring
assumptions when forming that key, and retains each entry's assumption graph and
its exact mapping into the completion coordinates. It exhaustively enumerates
color-preserving vertex permutations, preserving sort/literal colors, relation
tables and ordered hyperedge ports. These flat examples need at most 36 candidate
permutations each. Assumption graphs are independently canonicalized over their
used vertices, so unused completed outputs do not create false entry differences.

The combined 23 historical flat implementations and 11 current flat paths yield
34 records, 21 completed shapes and 10 duplicate groups. Most duplicates are the
same path in both exports; the remaining cases are the rule-103 self-repeat and
rule-426 pivot aliases. Every duplicate completion group has exactly one
isomorphism type of entry assumptions. **No two non-isomorphic entry structures
sharing a completed flat shape were found.** This conclusion now follows from
completed-only exact isomorphism, not merely from catalog/class IDs. Staged or
union-bearing shapes were not flattened or merged. Full mappings are in
`audit-isomorphism-results.json`.
