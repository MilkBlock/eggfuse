# Producer-local prefixes for residual register queries

This experiment concerns the standalone Cell CPU, not the native egglog runtime.
Its baseline is `762beb0f`. No speedup is asserted before frozen-binary
measurements and the ordered execution audit.

## Opportunity

The current catalog learns witnessed full matching entries. An entry requiring
an index expansion is not a complete Spine block: `stage_spine::order` rejects
it, and `result_handoff` only derives query receipts for complete stage entries.
The register matcher supports one residual expansion, but its early branch
also bypasses the generic matcher's existing `continue_local` projections.
Consequently a known producer effect is looked up again in a constructor index.

For example, a producer creates `A(x) -> a` and publishes `B(x) -> b`. A consumer
starts with `B(x)`, reads `A(x) -> a`, and then expands `E(a, y) -> z`. The first
read can use the producer's existing effect witness while the last atom must
still enumerate every matching row. One known `E` witness could not certify
that expansion's complete domain.

The smallest extension derives a shared prefix from the already validated
`multi_stage.routes` and the existing register program. It uses only contiguous
complete-key effects before the first unresolved key or expansion. Primitive
steps within this prefix execute normally. No observations authorize a rule
that the typed route cannot prove, and no new consumer subscription is stored.
The source-derived routes provide that wiring; the current iterative catalog
cannot yet learn these partial kernel entries from its executions. This change
does not claim to close that learning gap. Extending catalog history to partial
matching leaves and scoring these new counters during replay are separate later
changes; the immediate experiment tests whether the checked wiring saves work.

## Representation and execution

Each eligible kernel holds immutable plans indexed by the producer template
and publication operation. A plan maps its leading key steps to existing
producer effect operations; the register program retains all argument,
assignment, guard and ownership checks. Kernels without such plans do not read
producer context. Eligible seeds obtain their current origin/forwarded context
once, select a plan, and read its facts directly.

Successful reads fill the same register fields and query witness positions as
the old matcher. The original register loop resumes at the first unfinished
instruction. Missing, hidden, mismatched or unavailable donors resume that
instruction's original lookup; they are never negative match proofs. No
intermediate full-width `QueryEnv`, per-instance prefix buffer, or retained
producer reference is introduced.

## Live obligations

- Only a complete functional key can bypass lookup. The residual expansion and
  its candidate order are unchanged.
- Every donor must currently exist, be visible, have the expected operator and
  arity, and agree with every current canonical input. Mutable outputs are read
  now; historical result values are not equality proofs.
- The exact original seminaive owner test remains: a donor's `(epoch, witness)`
  may not exceed the seed's owner, and an equal stamp cannot belong to an atom
  preceding the pivot. Repeated variables and output constraints remain checked.
- Primitive guards execute in the original kernel order. A failed guard still
  rejects the candidate. No full-LHS future equality justifies an earlier read.
- Context comes from the current committed witness, including existing Entry
  forwarding and last-writer handling. Deletion/recreation cannot revive a dead
  effect. All matching is within the existing immutable source Run snapshot.
- Final bindings still use the existing deduplication and publication path;
  partial matching is never reported as complete Spine coverage.

## Cost and acceptance

`register_prefix` records eligible seeds, context and plan work, donor reads,
exact-key hits, stale/key fallbacks, field checks/writes, guards, owner/result
rejections, resumed instructions and actual avoided point-read invocations.
Avoided point reads are not automatically avoided hash lookups: the existing
`PointPorts` cache already serves some reads. Its requests/hits, actual key
lookup counters, allocation and complete process/inference time must be read
together. The static plans add setup work and retained metadata; runtime donor
decoding may allocate in the non-sparse backend.

Regression acceptance includes multiple residual results, stale and recreated
donors, mutable results, union changes, current publication origin, equal/newer
owner stamps, failed guards, repeated variables, and mixed legacy/shared Entry
execution. Compare complete ordered state, RHS, writes, resumes and schedule
where available. The implementation is accepted as a performance improvement
only after the normal single-thread sum-bits and Raytrace comparisons; counters
alone do not establish a gain.

## Bake ledger

The ledger charges prefix context probes, actual binary-search comparisons,
donor accesses and full-key field comparisons. Prefix `field_writes`, result
checks and primitive evaluations also remain visible in the report, but are
not charged as additional work: they execute the same instructions as the
ordinary kernel. A switch into the prefix must not invent a cost for work that
both sides already perform. `eligible_seeds`, hits, rejections, resumes and
`key_reads_avoided` describe outcomes; they never directly add positive credit.
Actual lookup savings already reduce `key_lookup_calls`, and cold decoding
remains charged through the existing fact decode counters.

Spine's separate local-witness path charges context/route probes, scanned route
steps and checked key fields. Its donor accesses already increment
`stats.decoded_rows`; charging `local_witness_reads` again would duplicate that
work. A failed donor still pays for its attempted access and checks.

For fragment publication, the old and new paths both report their actual
shared Entry slot probes. The old direct-publication hash operations have an
explicit counter, including misses, forwarding and replacement. New packet
appends, receipt writes/spills, delivery checks and temporary Pending slot
reads/writes are charged. Final publication writes remain in the existing
counter. Fragment deliveries, replacements, avoided insertions and successful
notification reuse are outcomes, not additional operations or free credit.

Repeated publication of a packetless Entry now enqueues a notification only
when that Entry first obtains a publication slot. Before refresh, the first
notification is still pending; refresh either installs the packet or removes
the Entry. Ordinary graph Wake notifications remain active for later changes.
Actual enqueues and suppressed duplicates are reported separately; only actual
enqueues enter the ledger.

These are equal-weight operation counts, not a calibrated time model. They do
not include compiler/setup cost or establish speedup. The ledger unit test
starts with a real report, checks that each new work counter changes the score,
and verifies that outcome counters and the Spine decode subset do not charge
the same operation twice.
