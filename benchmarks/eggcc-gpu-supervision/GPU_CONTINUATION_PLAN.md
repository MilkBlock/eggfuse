# GPU Cell continuation and ownership transfer

## Target and reference

Implement actual GPU-resident Cell continuation matching and ownership transfer,
with evolving dense floating token states, trained by ridge without backpropagation.
CPU supplies initial state and audits/handles explicitly marked uncovered cases;
it must not supply each successful match or an observed future route schedule.
The requested endpoint includes multi-entry, cross-stage/ruleset execution and
improved correctness, not only replaying known routes faster.

Reference branch inspected: `codex/cell-parallel-admission`, tip `56e28b89`.
Track this branch's advancing tip before subsequent architectural changes; this
is a reference pin, not an assertion that its code has been merged.

Relevant source and evidence:

- `shared_owner_transfer.rs`: transfer requires idle RHS, settled ownership,
  no pending unions and no dirty completion. Actual source metadata remains live.
- `cell-fields.md`, `b9fda4c1`, `28735c67`, `004fd672`: scalar operands project
  owning source slots. Remove the reverse scalar-provider path to avoid cycles;
  foreign returned results retain actual source/template identity. Compaction
  must preserve projected scalar operands.
- `template-transitions.md`: observed rule/template reuse is an opportunity,
  not proof of exclusive ownership or permission to skip mutable effects.
- `boundary-regions.md`, `56e28b89`: replacing symbolic routes with component IDs
  still requires substantial filtering. Static wiring is not universal direct
  addressing. New-root equality cannot reconstruct old-root union membership.

## Current gaps

`multi_entry_ridge.py` replays CPU-observed instances and connections; neither
matching nor future token generation is autonomous. `generated_cell_flow.py`
pre-enumerates bounded successors and gives fixed term encodings. Its current
`set/union` handling does not execute their obligations. The untracked
`token_ownership.py` experiment removes duplicate payload columns, but explicitly
has no activation, Run-boundary, retirement or generation ownership contract.
Do not count either as the required complete GPU flow.

## Implementation order and acceptance

1. **One compiled continuation interface.** Extend existing Cell catalog edges,
   rather than introducing a second fact graph. Each interface maps every
   consumer query atom to an established source-template fact and maps consumer
   inputs to authoritative source slots or actual returned witnesses. Retain
   effect-prefix, Run, Eq/scalar and lifecycle obligations. Implemented initial
   schema: `cell-continuation-contract/v1`; it grants no runtime transfer by itself.

2. **Device-side matching and token creation.** Bake static candidate layouts,
   not successful dynamic instances. GPU batches consume current Cell tokens and
   authoritative boundary/slot identity sidecars; compute matching evidence,
   masks and output tokens on device. Ridge predicts dense completion state;
   exact identity, generation and visible-stage checks must not be inferred from
   float similarity. Fixed tensor operations and bounded masks are preferred to
   per-node traversal. Capacity exhaustion produces an explicit local mark.
   Prove new token values/masks depend on previous GPU results, with no CPU
   binding/result injection between rounds. Include multi-source joins, not only
   a single producer whose template happens to cover the complete query.

3. **Transfer authoritative ownership.** A transfer changes both token state and
   responsibility for future continuation/effects. Data columns remain shared;
   preserve logical views and actual witnesses, including foreign constructors.
   Validate the whole transfer before replacing source ownership. Pending union,
   unsettled completion, stale generations, missing visibility or competing
   unproven owners must prevent transfer and yield reason-specific marks.
   Unknown external relations remain boundaries. Eliminate the duplicate source
   continuation state within admitted coverage; do not add a second registry.

4. **Run closure and cross-stage execution.** Separate no new token from proven
   saturation: unresolved marks, pending completion, capacity and uncovered
   candidates prevent certification. Delta/novelty handling must suppress repeated
   derivations without suppressing union-enabled matches. Advance the original
   schedule only when covered work is closed or CPU repair explicitly completes
   it. Ordered mutable effects remain ordered. CPU audits asynchronously, but
   uncertified speculative state cannot be committed as semantic completion.

5. **Real Eggcc validation and fitting.** Use the saved independent workload
   splits and actual program initial states. CPU full Run traces serve as a
   reference only, not runtime routes. Train ridge on multiple entry interfaces,
   completed states and permitted transfers, including changed ownership tokens.
   Select on validation and keep test held out. Retain exact partition, false
   merge, scalar, witness-lifetime, source Run visibility and stop-condition audits.
   Extend source contracts explicitly where the existing sum-bits validator is
   insufficient; unknown proof coverage is inconclusive, not pass.

## Metrics and completion evidence

Report device-produced matches and tokens separately from committed effects.
For each input/run: covered and uncovered candidate counts, failed obligations by
reason, false positives/negatives found by CPU, transfer proposals/acceptances,
source states actually removed, retained shared readers, copied payload bytes,
static wiring and dynamic metadata bytes. Charge compilation/preparation, upload,
GPU matching/completion, CPU audit and correction, synchronization, and output
transfer separately and end to end. Numeric CPU comparisons are not native
semantics or throughput baselines.

Completion requires GPU-generated multi-entry matching and token continuation
across actual source Runs, admitted ownership replacing old responsibility,
correctly handled conflicts and retirement, final and Run-boundary semantic
acceptance, and measured correctness against the frozen current model. A schema,
mask kernel, bounded example or speedup on CPU-observed replay cannot alone meet
this target. No completion claim is made in this document.

## Initial interface check

On the saved dot-product recipe (trace SHA256
`9cec5d6f16fc24db9863f84e704af0888ef2afc17aae041a2c00f57a20ba9b38`), catalog
compilation uses only `recipe`: 548 rules, 397 supported completed templates,
930 validated continuation contracts, 767 crossing rulesets. No bindings,
post-state labels or runtime transfers are used or claimed. Nine tests passed
across `test_continuation_contract` and `test_cell_token_successors`; malformed
witness coverage, duplicate witnesses and inconsistent bindings are rejected.

## Reference update: 794a2afd

The tracked branch advanced to `794a2afd` after the initial pin. Its checked Entry
address reuse retains `(FactRef, component ID)` in existing selection scratch;
reuse still checks the anchor, current shape and source at the saved ordinal.
Relocation, suffix change or retirement falls back to resolution. This is not a
cached value or permission to cross mutations. GPU continuation must retain the
same distinction between stable semantic token identity and a currently valid
storage address. Recycling introduces an additional generation check. No native
code was merged in this update.

The runtime target remains repeated GPU token production to a verified fixed
point, followed by the next original stage/ruleset, rather than host enumeration
of a predetermined successful path. New local-feature experiments are supporting
model work, not evidence that device matching or ownership transfer is complete.
