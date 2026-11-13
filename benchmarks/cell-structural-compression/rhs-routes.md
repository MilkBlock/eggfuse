# Result existence is not Cell Entry reachability

Offline follow-up to `8b5895d0`; no workload rerun and no runtime changes.
The analyzer joins the existing pre-boundary trace to actual returned fact owners
and the exact compiled `(producer, effect, consumer)` Entry key. It uses the
current program checksum to reject unrelated catalogs.

| Cross-Run visible-prior boundary | Count |
| --- | ---: |
| Total | 1,074 |
| Returned receipt unavailable | 98 |
| Returned fact owner outside pure-completion archive | 128 |
| Returned owner observed in an earlier Run | 848 |
| Of those, owner and consumer have the same rule | 553 |
| Exact returned effect has a consumer Entry | 15 |
| Exact returned effect has an Entry with no residual atoms | **0** |

The 976 returned fact receipts refer to **436 distinct fact identities**. This
is repeated work on existing facts, not 976 duplicate facts ready to delete.
The retained instance/field/index contribution must be established separately.

Two tempting approximations would overstate readiness. Using any Entry from the
owner rule, regardless of effect, reports 163 reachable boundaries and 117
without residual atoms; checking the actual returned operation reduces these to
15 and zero. Using the last rule that reused a result as its owner is also wrong:
that rule may have returned a constructor owned by another Cell.

This analysis uses the receipt returned after the current boundary. It does not
assert it is the same physical receipt inspected before the boundary. It also
does not assert absence of a different valid route via some other matched fact,
that any existing route was actually selected, or that non-observed owners are
unavailable. Residual enumeration, visibility and source scheduling remain live.

## Consequence for the next Bake iteration

Do not enlarge a history capture catalog based only on the 1,074 repeated keys.
The existing Entry representation starts from a producer's published effect;
most observed reused effects do not themselves supply a complete next query.
A completion donor instead needs to be reached through the current match's
existing instance/component connections. The next observation must distinguish:

1. Current matched source and result donor already share a composed owner:
   compile a static result projection, keep original residual matching, and
   replace the RHS lookup at its legal source boundary.
2. Donor is outside that owner but an actual retained Entry/history route exists:
   compile that route, charging its live result and slot requirements.
3. Neither connection exists: an equal-key archive is not an executable proof.
   Do not add a permanent reverse subscription/cache to manufacture ancestry.

Only then can a larger completed Cell take over the covered small instances.
The measured goal is fewer simultaneously retained instances/fields/index bytes
and fewer constructor/publication operations, not a higher diagnostic hit count.

Reproduce using the existing audited archive:

```sh
python3 benchmarks/cell-structural-compression/analyze_rhs_routes.py out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/rhs-before-audit.json benchmarks/cell-structural-compression/rhs-routes-results.json
python3 benchmarks/cell-structural-compression/test_rhs_routes.py
```

Three tests separate actual owner from last reuser, reject a different effect's
Entry as a complete route, retain residual obligations, and distinguish missing
owner evidence from a checksum mismatch. The source trace already passed all
1,428 Run checks and the reviewed sum-bits semantic acceptance; no new runtime
behavior, memory saving or latency improvement is claimed here.
