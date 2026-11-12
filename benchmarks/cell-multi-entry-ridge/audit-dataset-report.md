# Audit of real DAG completion labels and splitting

The reviewed `dataset.py` canonicalizer is appropriate for its explicitly narrow
contract: five supported constructor tables, visible rows, Expr output classes,
and acyclic constructor dependencies. It rejects cycles, missing producers and
unsupported visibility instead of silently dropping them. Processing complete
constructor multisets at each ready dependency layer and sorting them removes
instance identifiers while retaining ordered argument incidence, sorts, literals
and sharing. The duplicate-key assertion assumes repaired constructor identity.

An independent randomized rename/row-order test passed on initial, final and
native_final graphs for all 551 cases: 1,653 canonical invariance checks. This
supports implementation correctness but is not a general graph-isomorphism proof.
The current finite acyclic contract is essential; do not extend it to cyclic
egraphs without another canonicalizer.

`actual_port_map` is more than a class label: it follows each stable source anchor
through actual runtime forwarding and checks that every established source fact
survives at the projected final ports. Its map need not be injective, since union
may merge input ports. Missing anchors and inconsistent source aliases are
rejected. This is valid necessary extension evidence. Sufficient completion
comes separately from actual execution, the bounded ruleset fixed-point checks
and equality with the independent native final graph. It does not follow from
containment alone.

All 551 native final exports currently have empty anchor lists. Consequently the
explicit anchor-forwarding check is runtime-internal, while the native comparison
is whole-graph canonical equality. This is not automatically unsound for the
current repaired constructor DAG: the initial terms can be replayed by exact
constructor lookup into the native final graph, producing unique output classes
and thus an independently derived native port map. Export native source anchors
or check that unique embedding if claiming native validation of each returned
port/root. Merely comparing unannotated final graphs should not be described as
an independently checked native anchor map.

## Split recommendation

Do not retain the earlier per-completion round-robin split of literal-sensitive
entry hashes. For the strict unseen-entry-structure experiment:

1. Build an isomorphism-invariant incidence skeleton of each initial graph.
   Preserve operator/table, argument position, sort, eclass sharing and external
   Input identity. Mask Get/SubTuple scalar values but preserve their argument
   positions and scalar sorts. Include designated roots if root role is part of
   the prediction task.
2. Assign an entire skeleton group globally to one split using a fixed salted
   hash, before any completion-class filtering. A skeleton must never be split
   differently for different target completions. WL refinement is acceptable as
   a conservative grouping key: collisions merge extra shapes into one split;
   they must not be treated as proofs of completion equivalence.
3. Only then retain completion classes with distinct skeleton groups represented
   in all required splits. Report excluded classes/entries and full post-filter
   counts. Keep unseen literal combinations inside the same skeleton split.
4. Describe the task honestly as unseen entry skeletons for known completion
   classes. It is not generalization to unseen completion templates or unseen
   programs. Multiple entries share a common finite rule domain and workload.

Grouping by Input identities still permits renaming-only variants to cross
splits if the data generator treats Input IDs as interchangeable rather than
external semantics. If that becomes a nuisance augmentation, canonically rename
those IDs at split grouping time too; retain actual identities in labels.

## Negative containment test

`audit_dataset.py` adds an unrelated fresh Input constructor to a correct final
graph. All original facts survive, so all input-fact containment checks remain
true, but exact completion equality is false. The executable negative test
passes. Therefore neither a supersets-only metric nor successful port inclusion
is a sufficient prediction acceptance gate. Compare the complete predicted
completion with the independently justified target; reject extra unsupported
facts as well as missing facts. If later allowing deliberately partial
completions, give that a different contract and do not call it complete.

No dataset or runtime source was modified. Results bind the reviewed source and
runtime hashes in `audit-dataset-results.json`.

## Follow-up native port check

`dataset.py` now independently embeds the initial constructor DAG into the native final canonical graph and requires this mapping to equal the actual Cell anchor forwarding. All 551 cases pass; native export anchors themselves remain empty.
