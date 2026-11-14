# Actual feedback errors and a synthetic two-producer probe

The existing merged classifier was diagnosed on actual GCD/LCM predicted-source
captures, not teacher-forced inputs. All 140 reconstructed selections agree with
the recorded GPU choices. Complete-state correctness by local rule is 20/22,
69/98 and 1/20. Every validation target state occurs in synthetic training; none
of these validation feature vectors exactly matches a training input. No exact
training feature-plus-required-Eq label collisions were found. These observations
do not prove representation sufficiency or complete interaction coverage.

The third local rule is especially poor: 18 targets are state 0 and two are state
7; only one state-0 example is correct. Nearest standardized synthetic features
have the correct target on 13/20 examples, but this is a diagnostic, not a proposed
GPU lookup implementation or proof that ridge should achieve that accuracy.

`select_multi_producer_inputs.py` selects the smallest input hash per ordered
producer pair and consumer, excluding all 641 existing input identities. It reads
no real-program labels or model accuracy. The 18 available interfaces produce 14
distinct snapshots. This is a small deterministic probe, not exhaustive coverage.
The first native attempt accidentally used the old live-trace observer: all 14
failed argument parsing, not semantics. That attempt is archived separately.
With the capture observer, 12 pass and two exceed the one-second Run limit; the
latter remain unresolved and are excluded explicitly. Binary hashes are recorded
in the native manifest; they are not assumed identical to prior collectors.

All 12 terminating inputs pass the selected-family GPU execution and label audits,
producing 99 examples, 23 generated-source consumers and 76 released owner rows.
Those releases do not establish a speedup, and graph correctness remains protected
by exact kernels. The experiment does not enable learned union authority.

Adding all 12 inputs to the original 641, keeping alpha 10, shared context and
fixed joint projection, gives offline GCD 29/41 (previously 26/41) and LCM 40/99
(previously 65/99). The 653-input model is not promoted and no feedback rollout
was run for it. Real programs remain recurring development validation only;
training is synthetic-only, with no backpropagation. This result rejects the
claim that this small multi-producer expansion alone improves general accuracy.

Artifacts: `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/multi-producer-probe-v1.tar.gz`
contains enumeration selection, both native attempts, GPU captures and unpacked
training inputs. `matched-entry-gpu-v1/multi-probe-fit-argv.json` records the exact
fit command; `multi-probe-classifier.json` records the complete result. The feature
audit and its argv are `merged-feature-audit.json` and
`merged-feature-audit-argv.json`. The tracked JSON summarizes counts and hashes.

Tests cover deterministic input identities, exclusion of previous training inputs,
multiple interfaces sharing a snapshot, invalid sample limits, separation of
unseen targets from prediction errors, and exact feature collision diagnostics.
