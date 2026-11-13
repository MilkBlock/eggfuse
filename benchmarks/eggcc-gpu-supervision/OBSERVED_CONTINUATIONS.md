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
