# Nullary historical sources are traffic, not the main depth bottleneck

This is a CPU structural counterfactual on the saved dot-product trace, not a
GPU benchmark or semantic optimization. `audit_history_dependencies.py` rebuilds
the fallback-history dependency DAG and compares it with a DAG omitting only
historical nullary-constructor edges. Adjacent sources stay intact. No model is
refitted, inference run, union applied or runtime dependency deleted.

Of 50,424 edges, 36,315 are historical and 12,388 are historical nullary results.
The largest such groups are Add (4,493), PtrAdd (3,766), NoTerm (2,174), and IntT
(1,561). Omitting these edges would reduce base coefficients from 6,454,272 to
4,868,608 floats, affect 1,122 consumers and remove all sources from two consumers.
It lowers depth for 3,362 nodes, but maximum layer count only falls **91 to 89**.
Thus nullary observations are substantial traffic but cannot explain most of
the serial dependency chain.

One deterministic longest path in the reduced graph contains 88 edges, including
26 TCPair, 24 HasType and 12 PotentialExtractedExpr producer operations. These
are labels of observed provider operations, not a unique causal derivation or a
proof that these families dominate every critical path. Parallel edges from one
provider to one consumer use a representative operation label. Remaining NoTerm
edges are legal in this counterfactual because adjacent edges were not removed.

The result redirects further investigation toward repeated type-analysis and
extraction context dependencies rather than treating constants as the dominant
stall source. A template's fixed constructor identity does not imply its Eq
class carries no dynamic information; even the traffic reduction remains
unproved semantically. The report explicitly denies takeover authorization.

Reproduce:

```sh
python3 benchmarks/eggcc-gpu-supervision/audit_history_dependencies.py \
  "$ROOT/observed-corpus-20261113/rhs-dot-product.json" \
  history-dependency-results.json
```

The committed report includes the exact trace fingerprint. Six focused tests
pass for chronological source selection and dependency-depth accounting,
including rejecting future edges and not treating duplicate edges as extra
sequential steps. This experiment provides no speedup or accuracy claim.
