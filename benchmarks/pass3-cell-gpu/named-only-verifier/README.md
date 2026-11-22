# Named-only native verifier

The verifier build replaces the native rule matching entry. Its executable takes a program and a stream of packet batches, one JSON array per independent execution. There is no runtime option for a baseline, residual matching, candidate pages or an exact query. A packet names its Run, rule and one physical address and epoch for every table atom in schema order. Functional table reads also require explicit references. Missing or extra references reject the packet before the first graph read. No packets yields no rule bindings. Source schedule probes without a named proof fail closed.

The checking loop has a read-only snapshot interface for a named row, binding consistency and scalar primitives. The CPU can execute the checked RHS, repair the graph, maintain native storage and serialize the result. It cannot supply a missing LHS match. The build uses the frozen CPU runtime from joint-witness; the restriction applies to this executable. Compound certificates with internal static wiring and a live neural issuer have yet to be integrated. Primitive dependencies currently execute in source order and an unbound operand rejects the packet.

The acceptance tool executes the packet replay to completion before starting native exact in a separate process. It compares the full ordered RHS, writes, resumes, events, schedule and final graph digest. The returned accepted, rejected, unused and read counts describe verifier behavior. Handwritten or offline packet streams exercise this boundary; neither their provenance nor the absence of generator-side enumeration can be established by packet replay.

```sh
D=benchmarks/pass3-cell-gpu/named-only-verifier
python "$D/build.py" "$OUT"
cargo cell-compile --source "$D/two-parents.egg" --output "$JOIN"
cargo cell-compile --source benchmarks/pass3-cell-gpu/ripsat-strict-acceptance/local-equality.egg --output "$EQUALITY"
python "$D/check_fixture.py" "$OUT/session" "$EXACT" "$EQUALITY/program.json" "$JOIN/program.json"
python "$D/accept.py" "$OUT/session" "$EXACT" "$PROGRAM" "$PLANS" "$ISSUED"
```

Use the separate search-work-ledger native executable for EXACT. The two-parent control passes only with both real parents supplied. The two-Run fixture reaches the reference final graph with explicit references, but differs on three native resume events and its strict trajectory comparison fails. Omitting second-Run packets executes zero second-Run bindings. An empty packet stream on sum-bits executed zero bindings over 208 Runs and failed the reference comparison. None of these tests measures learned completion.
