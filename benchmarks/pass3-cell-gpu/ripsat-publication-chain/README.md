# An opt-in two-step program for a fresh constructor Set publication

This authorizer supplements the frozen Let-only RipSat adapter with one distinct instruction kind. Its evidence is a connected native history and a connected original execution from **the same dot-product producer and middle occurrence**. The original external root of rule 143 supplies its named Get. Rule 143's operation 1 publishes a fresh Single, whose actual physical reference is the sole input to rule 55. Rule 55's Set operation 1 publishes a fresh Get; that returned physical reference supplies the sole input to a later rule 143. The usual Let library still contains only `[[143,1,55]]`. Sending the reverse edge through its ordinary Let proof path still fails.

| Step | Native RipSat records | Exact native write/read token | Original donor serials | Original Runs | Fresh physical fact consumed |
|---|---|---:|---|---|---|
| 143 `let Single` → 55 | 0 → 8 | 6 | 1,737 → 1,822 | 131 → 135 | Cell 893, op 1, version 131 |
| 55 `set Get` → 143 | 8 → 12 | 10 | 1,822 → 2,625 | 135 → 139 | Cell 971, op 1, version 135 |

The local graph and donor use different namespaces. Native Single coordinates are [4, 5], and native Get coordinates are [5, 6, 4]. The middle's output site is `head/0/expr/0`. The terminal's Parent port [0, 4] in its required input addresses the exact Row site and token 10 of the middle native record. The original donor's Get publication has key [Eq 3835405795333, Int 0], result Eq 554050781213 and original FactRef 4170413244417. Independent reference results confirm that the first step was signed and the later terminal was an ordinary, separately issued binding. Jacobi's independently observed signed middle also published a fresh Get, but no later paid 143 consumed that exact version. It supplies no terminal witness for this authorization.

## Source and native proof

- Rehash the original [donor manifest and raw native graphs and history](../ripsat-donor-evidence/README.md). The separate [companion pins](../ripsat-strict-acceptance/companion-pins.json) bind the real three-occurrence source evidence. The companion specifies the exact first origin sample, donor program and recipe, signed first-step physical trail, independent source checks, complete actual named parents and terminal birth. A different observation of the reverse edge cannot stand in for the middle.
- Run the original strict adapter on the first edge. Reconstruct the middle instruction from the source SSA. The preceding `let Single(expr)` resolves to the middle's already named Single row. Require identical table and key, the correct destination sort and the compiler's existing operation-0 alias certificate. The Get Set key and value are functions of that input and literal zero. Its target must be a constructor table with no merge declaration, a real source fact operation, and the terminal must use that table's whole, distinct-slot row as its only independent premise.
- For the second native edge, recompute the complete Get row of the middle from the first returned classes. Check the actual newly produced Row token at the compiled source site and the emitted columns. The terminal must read that same write token at the same typed coordinates, and its parent-port index must point to that exact output on the earlier record. Require a real donor first-birth event and a later original named physical parent with identical version and values. Exclude previous or interned results, wrong owner or a descendant from another context.
- Relink only source role fingerprints with unique counterparts in the target. Recheck both operation grammars, target alias metadata, every projected argument sort and all terminal slots. The nested program carries the **target's exact file SHA-256**, the ordered path, the distinct kinds `fresh_constructor_let` and `fresh_constructor_set`, and the target constructor/pivot. The optional native runtime must still use the actual fresh physical publication, revalidate at the original Run, decline ambiguity/version changes, and genuinely suppress the otherwise external terminal before reporting FEPT. This directory establishes authorization; the runtime experiment measures adoption.

No target Run history, output, timing or model score is used for selection. [Dot-product certificate](dot-product.json) · [sum-bits certificate](sum-bits.json) · [3mm certificate](3mm.json) · [Tamper controls](controls.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/ripsat-publication-chain
small="$EXP/compact-holdouts-20261121-v1"
python "$d/authorize.py" \
  --donor "dot-product=$small/dot-product-1703/program.json" \
  --donor "jacobi-1d=$small/jacobi-1d-1703/program.json" \
  --target "$EXP/extra-pass3-transfer-v1/3mm-1703/program.json" --output "$OUT/3mm.json"
python "$d/test_controls.py" "$EXP" "$OUT/controls.json"
python "$d/verify.py" "$EXP"
```

The loader rederives the whole certificate before using a cached artifact. The rejection matrix covers a different middle of the same schema, stale first and last references, changed Set keys, an already internal terminal, absent native dependency, the wrong output of the correct middle record, a reused middle row, Set passed to the old Let checker, missing target static alias, edited donor bytes and retyped cached output.
