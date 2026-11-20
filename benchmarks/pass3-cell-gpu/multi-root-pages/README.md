# Immutable pages for multi-parent root proposals

The Cell CPU runtime freezes one contiguous array of typed, versioned parent references at each nonempty compiled rule occurrence. The page includes its source Run, verified compiler layout, template, first serial, arity and tuple count. The neural generator supplies the ordered addresses. Before reading any exact source row, the issuer finishes the entire page and hashes every candidate in its original order. A retained root recipe references a page slot. The exact parent verifier consumes its immutable address slice, then the existing root verifier checks the actual template, layout identity, address versions, visible inputs and final allocation. No proposer runs after seeing the verifier's result.

In the separate-envelope arm the source allocates one resident recipe and one parent list per raw tuple. A page shares its header and typed parent storage, and the surviving recipes decode their source slice when bound. The single-parent adaptive RootPage, original source order, checked-slot transfer, model, scoring row and correction behavior are common to all three arms. The experiment runs frozen Pass 3 in the standalone Rust engine, CLI allocator, CPU checkpoint seed 1703. The full joint multi-parent model uses the exported tied weights, zero-radius packed lookup and incremental freshness pruning. The immediate verifier runs with one CPU worker.

| Dataset | Raw parent tuples → pages | Separate, winner archive ms | Separate, audit-only ms | Paged, audit-only ms | API round-trip separate → paged ms |
|---|---:|---:|---:|---:|---:|
| Jacobi | 142,365 → 2,632 | 324.15 | 324.92 | 320.77 | 384.04 → 382.49 |
| Conjugate gradient | 914,791 → 4,189 | 1477.31 | 1458.63 | 1425.93 | 1569.16 → 1533.02 |

The page arm was faster in four of six paired trials on Jacobi and five of six on conjugate gradient. The median difference was small compared with the remaining distance to vanilla. No update to the default engine follows from these two single-machine measurements. A larger sample is necessary to distinguish the Jacobi timing from runtime variation. [Raw timings, clocks, source digests and negative controls](results.json)

Both arms verified every one of the 41,319 and 131,371 source RHS winners and directly constructed 32,721/32,819 and 97,026/97,139 fresh physical Cells. The complete RHS, effective writes, actual Spine resumes, union order, graph, source parent identities, root recipe hashes, allocator IDs and original per-RHS source ordinals agreed. Three targeted interventions changed a parent version, changed the template or withheld the multi-parent root. Under the no-fallback configuration each failed at the first physical Cell needing that receipt, Cell 187 at ordinal 59 after 14 Runs for Jacobi, and Cell 226 at ordinal 98 after 16 Runs for conjugate gradient.

```sh
d=benchmarks/pass3-cell-gpu/multi-root-pages
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-multi-pages"
python "$d/study.py" "$e/NEW-multi-pages/session" "$e/compact-vanilla-20261121" "$e/compact-holdouts-20261121-v1" "$e/baked-port-packed-study-v1" "$e/NEW-multi-page-study"
python "$d/verify.py"
```
