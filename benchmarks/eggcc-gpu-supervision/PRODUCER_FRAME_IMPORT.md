# Preserve enumerated producer instances at initialization

`materialize_enumerated_cells.prepare(document, spare)` replays and validates an
enumerated interface, then constructs the completed producer frames themselves.
It restores slot bindings from the typed partition, preserves logical producer
origins, fills the existing semantic token/scalar layouts, and marks only the
specified completed effects as complete. Lowered constructor-set temporaries
alias their proven semantic result slots; they do not add duplicate token input.
Unsupported producer query-literal layouts or missing slots are rejected.

Facts represented by these frames no longer retain separate visible seed rows.
Uncovered boundary rows remain. Equal producer keys/payloads share one logical
frame; inconsistent same-key payloads are rejected. This avoids inventing two
independent logical executions for an identical completed instance. Physical
payloads are initially independent and use ordinary `device_slot_owners.pack`.
No new reverse-dependency lists or runtime fact graph are maintained.

Every import projects ordinary constructor views through the packed owner
layout and compares the complete visible fact set with the validated snapshot.
All 25,670 two-producer routes passed this audit: 51,340 logical producer
occurrences became 51,204 distinct frames across cases. These selected consumer
queries have both atoms supplied by producers, so no boundary seed rows remain.
The audit concerns exact facts, not prediction accuracy or transfer savings.

A GPU test enumerates small F/G interfaces, confirms consumer matches retain both
producer witnesses, compares with the old fact import, and checks that retiring a
physical payload makes query enumeration incomplete. Constructor-set/token
behavior is still subject to further rollout validation. The exhaustive fact
projection audit was run before a token-only change excluding compiler temporary
aliases; graph projection is unaffected by that change.

This is checked synthetic initialization. The completed facts support the frame
contents, but do not prove source-program reachability, an actual apply history,
or a particular physical creator of a reused result. Runtime ownership transfer
must still follow the existing catalog and lifetime checks.

The selected-family runner supports opt-in `--synthetic-input --producer-frames`
for the full enumerated family. Capture metadata records the initial logical row
and generation identities; CPU auditing reconstructs and verifies that map.
Source accounting compares both row and generation, so a reused row is a new
instance, while an initialized original-rule frame is not a generated token.
No per-step GPU provenance registry is introduced. Historical captures without
this metadata retain their legacy seed-rule interpretation.

Two actual GPU rollouts with the shared-context head and exact effect authority
were tested. The first is already complete (zero generated Cells, one Run). The
second generates seven Cells over four Runs; six consume generated sources.
The old rule-ID heuristic would report seven, demonstrating the corrected bias.
CPU graph checks, feature reconstruction and final labels pass. Both runs report
zero owner releases: this validates instance-preserving execution and accounting,
NOT successful ownership transfer in this new input mode. Takeover eligibility
for these compound initial frames remains to be investigated. No accuracy or
speedup claim follows from these two examples.

Reproduction uses `audit_construct_union_family.py` with rules 0,1,2, snapshot 0,
capacity 32, ticks 20, flush-every 1, order-queries, boundary-context, experimental
boundary-model, predicted-source-feedback and the enumerated shared-classifier
weights/report, plus the two flags above. Then run `label_composed_witnesses.py`
with synthetic-input and the same head. Input documents and verified captures,
execution reports and labels are in the archive identified by
`producer-frame-rollout-results.json`. No whole-Eggcc coverage is claimed.

Reproduce the fact audit with:

```
python materialize_enumerated_cells.py ENUMERATION_DIRECTORY OUTPUT.json
```
