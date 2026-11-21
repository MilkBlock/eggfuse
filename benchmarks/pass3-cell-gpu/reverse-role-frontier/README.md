# Gather the root frontier from smaller compiled parent roles

The packed whole-Run CPU issuer normally enumerates the first parent of a three-or-more-parent plan and probes later learned relations. Existing forward filters test viability after a root has been read. The sparse pair issuer and stable posting directories handle two-parent plans. This experiment changes how the root loop of the general multi-parent stack is populated.

For example, rule 241 of the held-out 3mm Pass 3 program starts with `BodyContainsExpr(body, expr)`. Its compiled plan subsequently requires a `DoWhile` whose column 1 refers to `body`, and a `Get` whose result refers to `expr`. Rule 242 shares the first two roles and has a `Concat` requirement in place of `Get`. A valid complete proposal for either rule needs a `body` code present in the `DoWhile` role. A rule can also use one of the other descendant roles if it is smaller and its primary join column comes directly from a published root slot. This is checked from the actual compiled plan on each call.

At zero radius with tied query and key weights, the intersection of the root and descendant's packed learned signatures yields the root rows that can pass that primary equality. The issuer gathers lists of physical root positions from the existing model-produced indexes, sorts them in original order, then runs the original model-based multi-parent generation, source validation, ordered commits and graph maintenance. Signature collisions admit extra work. A role supplied by an intermediate parent cannot be used for this projection. The implemented general admission requires at least 64 root rows and a descendant no more than a quarter as large. The empty test applies to any independent frame and needs no learned index.

The cached treatment shares this ordered frontier across occurrences and different rules with identical source tables and column roles. Both immutable frame generations and both union generations must match. The cache limits stored position arrays to 4 MiB and 1,024 role pairs. The charged size excludes existing runtime indexes, map headers and temporary vectors. A separate uncached treatment measures the cost of gathering each time. Detailed audit independently scans every original root query and every descendant key for each gathered frontier, checks equality of the complete ordered list, and compares all actually issued proposals and winning physical parents to the baseline. All arms retain the original exact verifier. The reference is actual Pass 3 in the CPU engine. Four rotated, uninstrumented inference samples follow warmup. Phase timings are from a separate three-sample run and include compiling the stack, downstream viability and port preparation and enumeration. They exclude earlier frame/watermark preparation, subsequent verification and RHS publication.

## Held-out results

| Program | Mode | Root-loop positions visited | Multi-parent issuer phase, ms | Frontier construction / lookup, ms | Whole inference, ms |
|---|---|---:|---:|---:|---:|
| conjugate-gradient | packed baseline | 4,336,560 | 205.94 | 0.06 | 644.38 |
| conjugate-gradient | empty only | 4,336,560 | 200.38 | 0.05 | 632.35 |
| conjugate-gradient | gather every time | 1,221,865 | 186.33 | 7.75 | 622.55 |
| conjugate-gradient | share gathered frontier | 1,221,865 | 182.10 | 4.72 | 626.37 |
| 3mm | packed baseline | 14,942,662 | 631.74 | 0.08 | 1,856.95 |
| 3mm | empty only | 14,942,662 | 617.53 | 0.08 | 1,802.97 |
| 3mm | gather every time | 4,763,725 | 607.04 | 35.68 | 1,844.79 |
| 3mm | share gathered frontier | 4,763,725 | 588.15 | 19.67 | 1,850.06 |

The shared frontier removes 3,114,695 and 10,178,937 actual general-stack root-loop positions (71.82% and 68.12%). Of the 397 / 521 cache hits, 388 / 507 reused a frontier last consulted by a different source rule. On 221 / 383 calls the chosen relationship belonged to a parent beyond the immediate second role. Compared with rebuilding the gathered list on every call, caching reduced distinct child-bucket probes from 8,410 to 4,082 on CG and 24,889 to 10,502 on 3mm. Peak cached position arrays were 32,000 and 127,248 bytes. The root posting builder still indexed 328,938 / 1,299,471 rows over the runs. The phase measurements include this cost.

The old forward guards already prevented most unproductive roots from reaching later parents. Consequently the issuer's aggregate approximate visits changed only from 407,758 to 407,630 on CG and 1,327,608 to 1,326,035 on 3mm. The same online models issued the original 83,313 and 220,972 multi-parent tuples. The independent root membership audit checked 3,785,634 / 13,264,864 candidate positions before the source watermark exclusions. Root-loop savings use actual loop bounds after those exclusions. The separate exact CPU ran in 352.23 / 981.58 ms.

The measured issuer phase was 23.84 / 43.59 ms shorter with sharing. The full shared arm took less time than baseline in three of four pairs on both workloads, but the empty-only gate activated zero times and its 3mm median was 47.10 ms below the shared arm. The four end-to-end pairs support the root-work reduction much more clearly than a stable full-inference improvement. [Detailed source alignment and full timings](results.json) · [Separate phase measurements](phase.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/reverse-role-frontier
python "$d/build.py" "$EXP/reverse-role-build"
python "$d/study.py" "$EXP" "$EXP/reverse-role-build/session" "$EXP/reverse-role-heldout"
python "$d/study.py" "$EXP" "$EXP/reverse-role-build/session" "$EXP/reverse-role-phase" --phase
python "$d/verify.py"
```
