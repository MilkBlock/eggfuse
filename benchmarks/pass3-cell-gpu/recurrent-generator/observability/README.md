# Pre-decision evidence on the pending-parent GPU archive

Run audit.py EXPERIMENT_ROOT OUTPUT_DIRECTORY with the external workspace Python.
decisions.jsonl references original captured tensors by workload, Run and digest.
At root decision r, its input is the current candidate tensor and the preceding
self-generated children (zero at entry). The evidence delta contains publications
and winning commits from the previous Run. wins_later_this_run is an offline
target and must never enter the input. Candidate observations are reconstructed
from the separate, previously replay-checked reference capture for seed 1703.

The narrow matching key is the same leaf, physical anchor and publication
ticket, bounded by republication. It does not prove the same bindings remain
eligible after a union, watermark advance or hidden-row change. A historical
win is an occurrence, not a permanent closure of all later obligations. The
whole-bank check includes the ruleset and ordered candidate addresses.
Distinct input hashes establish neither causal distinguishability nor a
learnable rule. These observational comparisons do not intervene on the graph.

Set compound['audit_claim_time'] to True for new GPU captures to record the Run
of failed resume checks (ticket invalidation or duplicate); at a subsequent
root decision the audit exposes only already-observed events. The extra file
is optional. Historical failures with unknown timing remain unlabeled.
