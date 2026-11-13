# Evidence-preserving observed continuation collection

Before evaluating changed requests in the latent runtime, this collector attempts
to establish real producer/consumer links from saved execution traces. It does not
reinterpret a pair of static rules as an observed execution chain.

The existing corpus records actual matched inputs and pre/post-Run Eq roots, but
not actual RHS constructor return identities. Consequently this first collector
accepts only producers whose effects are union/copy and whose local closure adds
information. It maps known input symbols through the teacher quotient and native
post-Run roots, rejecting extra native equivalences absent from the local proof.
It never treats `(producer, operation)` as a returned result address.

For a different rule observed in the next nonempty Run, every Eq input must map
into that interface and every constructor premise must be present in the first
local completion. The request must have been locally disabled before the producer
and locally enabled afterward. Its effects must be supported and locally novel.
Actual Run/binding ordinals and ruleset names are retained. Empty intervening Runs
are allowed only when each exists in the step trace with zero executed bindings.
The collector does not skip a nonempty Run or silently assume external facts.

These conditions deliberately define a narrow first evidence tier. They do not
cover general cross-stage Cells with late/external inputs, new constructor return
addresses, mutable context, deletion or ownership transfer. A validated row would
prove the observed match and local derivation, not authorize arbitrary runtime
replacement. Second-completion outputs remain conditional teacher labels, not
recorded native constructor returns.

## Result: no closed continuation under this evidence tier

The first 10 complete workloads with at most 20,000 observed bindings each were
examined, using the recorded manifest order. All other cases have explicit budget
or incomplete-trace exclusions. After bridging 1,407 proven empty Run gaps:

| Diagnostic count | Value |
|---|---:|
| Union/copy producer bindings considered | 2,653 |
| Producer has no local novelty | 1,118 |
| Producer has unsupported/non-constructor premises | 810 |
| Extra native equivalences outside the local proof | 135 |
| Consumer candidate has external Eq inputs | 13,339 |
| Consumer candidate has unsupported Unit scalar | 606 |
| Consumer candidate has non-constructor premises | 47 |
| Consumer candidate uses unsupported subsume | 233 |
| Accepted observed chains | 0 |

Consumer counters are candidate checks per producer, not unique bindings and not
fractions of all runtime errors. Zero accepted chains does not imply that egraphs
lack locality or that no real continuations exist. The evidence contract and
single-query source regions omit the boundary context needed by real consumers.
No changed-request GPU success is claimed from this result.

The current trace hook runs before RHS (`binding_observer`) and exports matched
slots; post-Run auditing only updates those Eq roots. The next data work must
capture actual output witnesses and boundary context, or explicitly model
additional incoming Cell interfaces. Merely extending the candidate dictionary
would not supply this missing runtime evidence.

## Reproduce

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/collect_observed_continuations.py MANIFEST CHAINS.json --max-cases 10 --max-bindings 20000
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_observed_continuations
```

`observed-continuation-results.json` includes every selected workload, fingerprint,
exclusion and diagnostic count. Tests include a positive union-enabled changed
request across an empty Run, rejection of external equivalences, a missing
consumer premise, unproved Run gaps and unaudited traces. These fixtures prove the
collector can accept the stated contract; they are not real-benchmark chain data.
No native engine path was changed. The related 59 tests pass.

## Preserve multi-entry boundary candidates

The optional `--boundary-output PATH.jsonl` streams previously rejected
`external_consumer_input` pairs to disk. Each record retains the actual case,
program fingerprint, split, Run and binding ordinals, rulesets, proved-empty Run
gaps, producer local state and consumer input evidence. Consumer Eq ports are
partitioned into producer-interface symbols and typed external equivalence
classes. Repeated external inputs share a class index. Consumer post-Run roots
are not used for that classification.

These are **observed shared-interface candidates**, not causal links or
completion training targets. Both `causal_link_proven` and
`takeover_authorized` are false. A consumer's successful match supplies its
observed input evidence; it does not prove that this particular producer
caused it, that the external premises are available earlier, or that a GPU
may omit their computation. Future consumer inputs must not leak into the
producer's prediction features. Roots are program/Run-scoped audit identities,
not numeric model features. Unsupported teacher operations are still rejected.

Reproduction (ROOT is the external corpus directory):

```sh
python3 benchmarks/eggcc-gpu-supervision/collect_observed_continuations.py \
  "$ROOT/manifest.json" "$ROOT/observed-boundary-report.json" \
  --boundary-output "$ROOT/observed-boundary-candidates.jsonl"
```

With the unchanged first-ten-case / 20,000-binding limits, the saved report
`observed-continuation-boundary-results.json` records 13,339 candidate pairs, 238 unique
producer applications and 2,885 unique consumer matches. Candidate counts are
not unique mutation counts. External-class counts range from one to six:
279 / 4,437 / 5,777 / 1,798 / 911 / 137 pairs respectively. There are no
cross-ruleset pairs in this sample; all observed candidates cross Runs within
the same ruleset. Closed local proof count remains zero. Train/validation/test
candidate counts are 11,338 / 11 / 1,990, preserving the workload split.

Raw evidence is on the external drive and its SHA-256 is in the report.
This is offline analysis of real CPU traces, not a GPU execution benchmark or
native semantic acceptance. No executor behavior changed. The related Python
suite passed 61 tests, including external-alias typing and preventing a
boundary candidate from becoming a proven chain. Next capture work must supply
actual RHS returned witnesses and boundary premise validity; a shared port
alone cannot authorize token ownership transfer.
