# Share source validation across installed Cell catalogs

The actual original-source witness experiment removes 280 constructor lookups
but does not improve inference. It also increases Program load from 98.712 to
122.797 ms. Inspection finds a concrete duplicate cost: composition fragments,
dual-source patterns and constructor witnesses independently hash the entire
same source artifact during one ownership Plan construction. The last audited
408-recipe catalog contains both fragments and witnesses; another observation
cannot eliminate this repeated compiler work.

The ownership Plan now validates every installed header against a single lazy
source digest. The artifact is immutably borrowed throughout this construction.
No digest is stored in Program, no global cache is added, and catalog-free Plans
do not compute it. Private subcompilers retain schema, budget, typed port/code,
query substitution and actual-result-source checks. Agreement between catalog
headers is not enough: each must match the current source independently.

This removes redundant source serialization/hash work during loading, not rule
matches or committed effects. It adds no runtime instance state, producer lists,
fact graph or cross-Run assumptions. Scheduled visibility, source retirement,
union generations, exact unproved keys and residual matching are untouched.
No new Cell completion is credited. Load, inference and full-process time must
be reported separately; a smaller load time is not a parallel speedup.

The regression test loads all three header kinds together and separately,
rejects each stale/missing/non-string source, and then loads a different valid
source carrying the old headers. Existing fragment/witness/join tests still
exercise the typed subcompilers after common source validation. Actual-workload
validation and sequential timing compare with the frozen pre-change runtime.

Compute job 355 passes 71 ownership, 19 compiler and 13 witness integration
tests, plus the no-default runtime compile. The ownership suite includes
storage, composed sources, deletion/union and worker continuation fixtures;
the new header test also exercises lazy ownership preparation without fragments.
