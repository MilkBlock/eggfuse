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

The full selected-family runner has not yet switched to this importer. Before
collecting its training data, source accounting must distinguish seeded completed
producer frames from tokens newly generated during the GPU run. Rule identity
alone is insufficient for that distinction. Likewise, no full multi-stage or
whole-Eggcc coverage is claimed.

Reproduce the fact audit with:

```
python materialize_enumerated_cells.py ENUMERATION_DIRECTORY OUTPUT.json
```
