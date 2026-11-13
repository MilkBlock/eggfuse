# Actual RHS output to later Cell input evidence

`link_rhs_results.py` connects captured constructor return values to successful
matches in the next nonempty observed Run. It uses typed post-Run Eq roots and
consumer pre-Run roots. Raw identity equality is reported separately from
membership in the same equivalence class. This distinction does not assert
which union caused equality. Copies do not become extra producers; scalar
numerical equality and mutable reads/sets do not establish links.

A group stores all possible producer application / operation / result-slot
references for one typed root. Consumers refer to these shared groups, retaining
their unmatched external Eq classes and observed input values. There is no
Cartesian expansion into separately stored pairwise bindings. Multiple
constructor calls can reuse one existing result, so the group deliberately
does not nominate a unique owner. This is offline evidence organization, not a
second runtime fact graph or a GPU dispatch mechanism.

Missing, incomplete or unavailable constructor results cannot provide inputs.
Intervening Runs must have both zero executed bindings and `changed == false`;
missing metadata and changed empty Runs prevent linking. Every trace must have
passed the actual RHS capture's per-Run and final reference graph audits.

Reproduction:

```sh
python3 benchmarks/eggcc-gpu-supervision/link_rhs_results.py \
  "$ROOT/rhs-dot-product.json" "$ROOT/rhs-dot-product-links.json" \
  --manifest "$ROOT/manifest.json" \
  --summary benchmarks/eggcc-gpu-supervision/rhs-dot-product-links-results.json
```

The manifest check binds this new trace to the original corpus recipe and
partition. Dot-product is **test**, so these records must not be added to ridge
fitting data. No model was fitted or selected in this experiment. Source data
and full link records are on the external drive; committed text results contain
the trace, manifest and link-artifact hashes.

## Observed dot-product result

Across 413 eligible adjacent-Run windows, 207 have linked consumers:

- 7,579 constructor outputs requested from eligible producer windows, all
  available. This is narrower than all 47,173 slot reads in the capture report;
  the latter includes the 2,663 unavailable non-constructor-result reads.
- 5,675 of 25,852 examined consumer Eq slots connect: 5,540 have a provider with
  the identical captured identity, and 135 only have equal typed roots.
- 2,901 of 5,934 examined consumer applications have at least one connected
  input. Of these, 2,391 still need external Eq inputs; 496 cross rulesets.
- 1,066 applications need multiple observed provider applications to account
  for their connected groups: no one provider appears in every group. This
  does not prove that these providers caused the match.
- 510 have no external Eq classes relative to these groups. Scalar inputs,
  query predicates, visibility and lifetime obligations remain; this is **not**
  a claim of 510 fully closed or executable completions.
- The artifact stores 2,459 shared provider groups and 3,962 provider references.

Counts describe observed inputs and candidate providers, not committed new
mutations or correctly generated GPU tokens. This advances beyond the earlier
union-only closed-fragment collector: real RHS identities expose cross-ruleset
and multi-provider input structure without restricting everything to one
producer. A future Bake layout can preserve these shared result interfaces,
but must still establish the complete consumer conditions and output lifetime.

Six linking tests cover multiple possible providers, multi-provider inputs,
external classes, typed identity, missing/incomplete outputs, copy exclusion,
equivalent identities, changed/missing gap metadata and audit/order rejection.
The related Python suite passes 69 tests. This is CPU-trace analysis, with no
new GPU benchmark or native egglog semantic acceptance claim.
