# Sharing premises across the sealed tuples of a rule

The neural issuer has already sealed every parent in a page before the source verifier reads the first parent. For each independent parent role, the Rust compiler assigns repeated fields and literal guards to the role itself, and emits explicit column pairs for equalities with earlier roles. A rule-local slot is projected from the first role that binds it. At verification the source frame is immutable. A role, typed fact/function address, and source version identify a local physical observation that can be shared by nonadjacent tuples. Cross-role equalities and the tuple's seminaive epoch still depend on the selected tuple. An independent point cache can also reuse successes and absences for up to 4,096 complete scalar keys per page. The row cache admits up to 8,192 entries per page. No cached row proposes an independent witness.

The stock control and every treatment use the same frozen CPU issuer, page order, ordered source effects and schedule. The checked control reads each source and uses the original exact extension. Rows reuses physical reads. Wired compiles the role tests and cross-parent slot projections. Shared combines rows and wiring. Points retains only repeated suffix lookups. Block enables all three. On the detailed run every partial prefix is independently reread and compared with the ordinary verifier, including rejected prefixes, fully bound slots, witness roles and maximum epoch. Ordinary wall timings exclude those extra checks. Each program has four rotated samples after warmup at seed 1703. Default CPU is a separate unmodified EggFuse process.

| Program | Default CPU | Stock learned | Checked | Shared reads only | Wiring only | All three, ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 23.06 | 33.05 | 33.62 | 34.69 | 33.94 | 33.31 |
| conjugate-gradient | 377.74 | 675.05 | 660.50 | 651.03 | 655.55 | 665.38 |
| 3mm | 904.94 | 1,931.27 | 1,952.54 | 1,955.12 | 1,950.45 | 1,926.37 |
| deriche | 1,603.02 | 3,548.33 | 3,673.14 | 3,700.83 | 3,642.61 | 3,662.49 |

| Program | Logical parent reads | Physical reads | Hits beyond first parent | Original / remaining suffix reads | Cached absence hits |
|---|---:|---:|---:|---:|---:|
| sum-bits | 13,260 | 10,602 | 1,556 | 1,627 / 1,188 | 63 |
| conjugate-gradient | 189,772 | 131,480 | 32,728 | 37,475 / 22,569 | 2,473 |
| 3mm | 526,257 | 325,615 | 112,418 | 104,197 / 68,388 | 6,058 |
| deriche | 786,926 | 452,398 | 213,219 | 121,695 / 79,527 | 4,643 |

The 3mm page dictionaries saved 200,642 physical reads, of which 112,418 were beyond the first role. Deriche saved 334,528. These are avoided reads after issuing the same complete tuple stream. The caches themselves are constructed and probed in the measured interval. Complete runtime medians did not improve consistently across the four programs. [Smaller runs](core.json) · [Larger runs](large.json)

```sh
d=benchmarks/pass3-cell-gpu/page-premise-programs
python "$d/build.py" "$EXP/premises"
python "$d/study.py" "$EXP" "$EXP/premises/session" "$EXP/premises-core"
python "$d/study.py" "$EXP" "$EXP/premises/session" "$EXP/premises-large" --cases 3mm deriche --arms check rows wired block
python "$d/verify.py"
```
