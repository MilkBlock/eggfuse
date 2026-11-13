# Reject constant-only completion as the main compression path

This is an offline reclassification of the exact four audited constructor reuse
archives from `template-transitions.json`. No workloads were rerun and no timing
result is added. Each consumer operation is checked against its artifact's typed
source table. Constructor expression identity uses table names, typed literals
and earlier fixed results, not source IDs or slot numbers. Mutable reads, missing
inputs, unknown primitives and other effects stop this conservative prefix proof.

| case | observed visible cross-Run reuse | input-independent prefix | outside that proof |
| --- | ---: | ---: | ---: |
| fact | 714 | 71 | 643 |
| loopfact | 508 | 87 | 421 |
| sum-bits | 3,622 | 373 | 3,249 |
| dot-product | 2,652 | 359 | 2,293 |

Every case has three constant expression groups: NoTerm, TCPair(NoTerm,10^16),
and TNil. Sum-bits contributes 186,186,1 uses respectively. This is not a claim
that every other expression fundamentally depends on inputs: unsupported effects
and proof boundaries are deliberately not guessed. Nor is it a memory-saving
estimate; repeated reads may already target one stored constructor.

## Rejected runtime trial

A trial compiled a validated constructor prefix followed by a single write into
the existing `apply_write` entry. The focused integration test failed its required
path-coverage assertion, while semantic snapshots still agreed: the rule retained
a live stage cursor and a three-slot actual-result buffer. Discarding those
receipts to force admission would lose the existing completion contract.

There is also a typed blocker for the actual hotspot. ExtractedExpr's source
merge is `(Smaller old new)`, a table-call merge. `row_kernel::writes` admits only
null/simple supported merges; `physical_plan::scalar_merge` does not lower this
merge. It must remain an ordered effect, potentially with its own work. The trial
was removed in full. There is no new runtime fast path, changed compiler plan,
additional maintained cache or runtime performance claim in this result.

## Priority changed by the evidence

Input-independent prefixes account for only 10.3% of the observed visible
cross-Run constructor reuse in sum-bits. Implementing a separate persistent
constant cache would address this small subset and leave the dominant closure
problem intact. Even that subset needs the existing result ownership and merge
publication semantics; a successful snapshot constructor read is not permission
to erase a stage's receipts or later effects.

The next takeover should use parameterized Cell state and its actual result
slots, together with the existing completion/publication interface. Its admission
must discharge the covered prefix and preserve the remaining merge and its
ordered result. The necessary evidence is removed repeated matching/publication
and retired storage, charged against new state/dispatch costs. Broadening the
single-write eligibility check or adding a memo before the old path is not that
takeover. Current production runtime remains the prior accepted implementation.

## Reproduction

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/constant_prefixes.py benchmarks/cell-bake-owner-merge/template-transitions.json out/cell-bake-owner-merge/batch/prefix-all benchmarks/cell-bake-owner-merge/constant-prefixes.json
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/test_constant_prefixes.py
```

Three tests pass for slot renaming, input/mutable-read exclusion, effect boundaries
and typed literal distinction. This source classification is not an executable
closure proof or a new native semantic acceptance result.
