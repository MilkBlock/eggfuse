# Independent training/prediction audit

Read-only review of train.py, predict.py and the current corpus. No direct label
leakage was found in the implemented feature pipeline: graph encoders and field
moments use only entry DAGs, normalization statistics and kernel centers use
training rows, the completion catalog uses training labels, and kind/regularizer
selection uses validation scores. Precomputing deterministic entry features for
all rows is not label leakage. The known-class benchmark deliberately excludes
classes absent in any split; this defines a conditional known-template task and
must not be presented as novel-template generalization.

The inspected corpus has 469 rows: 272 training, 95 validation and 102 test.
Its 172 skeleton groups have zero cross-split overlap. Masked scalar variants
stay grouped globally, including across completion labels. The explicit native
constructor embedding check now independently reconstructs each source port in
the native final DAG and compares it with actual runtime forwarding. This
addresses the prior missing-native-anchor concern within the narrow constructor
DAG contract.

The frozen result files give:

- Single encoder: 88/102 = 86.27% top-1, macro 86.52%, top-3 97/102;
  eight wrong candidates still pass input containment.
- Two encoders: 89/102 = 87.25% top-1, macro 86.15%, top-3 95/102;
  five wrong candidates still pass input containment.

Two encoders slightly improve micro top-1 but not macro accuracy or top-3.
Neither reaches 90%. No wrong candidate had numeric port-map equality in these
saved results, but comparing port indices across different completion classes
is not independently meaningful: equality of maps must be coupled with equality
of the completion identity/structure.

## What the model computes

The output is a predicted ID in a training-derived finite completion catalog.
Port maps are then computed by the exact symbolic `extension` lookup. Neither
this lookup nor learned catalog recognition executes rule effects, union,
visibility updates or repair. `predict.py` correctly marks every candidate
`authorized_for_execution=False` and calls containment necessary only. Keep
these boundaries prominent in reports and downstream APIs.

The dense orthogonal target-code construction does not by itself create a new
continuous completion machine: with an orthogonal square code matrix, least-
squares/ridge fitting to rotated class codes followed by inverse rotation is
mathematically equivalent (up to numeric rounding) to multiclass ridge on
one-hot labels. The input random nonlinear graph encoders do perform real-valued
computation; the target rotation is a representational choice, not proof of
compression or neural-style completion reuse. Do not conflate this experiment
with the previous autonomous latent-state recurrence experiments.

All correct predicted template maps matching actual maps is useful evidence,
but the explicit five/eight false candidates passing containment demonstrate
that this condition cannot authorize execution. The negative extra-Input
superset example correctly enforces this distinction.

## Limits and remaining disclosure

- If encoder seeds/features were chosen after comparing test outcomes, disclose
  that test reuse as exploratory research. Per-run validation selection does
  not make the overall cross-run test selection untouched.
- `exact_entry_lookup_hits=0` is currently hard-coded; it follows from the
  advertised corpus construction, but should be computed/asserted from actual
  train/test entry-key intersection if retained as a reported metric.
- The saved model and separately provided catalog are not cryptographically
  bound in predict.py. For reproducible deployment, bind the canonical catalog
  digest/schema and reject mismatches rather than trusting an arbitrary file.
  This is not leakage in the inspected paired experiment.
- The CPU timings correctly exclude parsing/proof checks/publication and are
  not GPU throughput or runtime speedup. The generated corpus validates only
  its finite ruleset and constructor contract.

## Follow-up fixes

The final code computes and asserts exact-entry lookup misses, binds model and catalog with a canonical digest, and rejects mismatches. The final dataset also reconstructs the native constructor embedding and compares it with actual runtime forwarding. These fixes were checked before commit.
