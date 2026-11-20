# Moving checked bindings across the source Run

The verifier first accepts a proposed rule and physical parent addresses, then the source scheduler selects a winning binding and executes its ordered RHS. A single-parent mark carries a token, a checked recipe and an input vector. The former runtime cloned the mark when attaching it to the projected source witnesses, then cloned it again to identify the source winner. Each accepted multi-parent tuple left a ticket, including its checked root, in the executor's directory until pass exit.

We kept the two-view actor, incrementally published single-parent table headers, lazy arithmetic ports and the original exact verifier from the [composed CPU configuration](../composed-cpu/README.md). The experiment runs the standalone Rust Cell engine on two complete eggcc Pass 3 programs, sum-bits and 3mm. All expensive work remains in the timed execution. The four treatments share the same binary.

* **Move** takes the single-parent mark from the owned winning query facts at reprojection and ordered commit. Its underlying source witness projection stays readable. Spine branches that borrow a competing binding can still clone a mark when they actually need to share it.
* **Receipt** compares the values consumed by the winner against the checked-slot root recipe's immutable, still-unconsumed projection. This replaces a second value vector in the single-parent mark. The recipe still checks its exact source references and values before physical allocation. A recipe without checked slots retains the original snapshot. An independent audit removes an input from a copy of an actual binding and requires rejection by the new comparison.
* **Run tickets** releases the previous Run's directory of multi-parent proofs at first access in a subsequent Run. Competing proofs and the original order remain available throughout winner selection. Cross-Run descendants keep their original absolute serials. A ticket lookup past its lifetime rejects explicitly. The backing vector can reuse its largest capacity. Explicit audit archives of winners can retain separate proof references.
* **All** enables the three changes together. **Off** uses the existing algorithm with the same reporting fields.

Resident inference includes issuance, verification, ordered effects and graph repair; the process already contains its program. Four interleaved samples follow one warm-up for each arm, at frozen seed 1703. The logical ticket count counts directory entries.

## Complete execution

| Program | Vanilla | Off | Move | Receipt | Run tickets | All | Faster paired repeats, all vs off |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.05 | 32.29 | 33.07 | 31.90 | 33.67 | 33.01 | 2/4 |
| 3mm | 925.73 | 1,969.04 | 1,929.20 | 1,936.88 | 2,003.33 | 1,924.78 | 3/4 |

All times are median resident inference ms. The combined path reduced the 3mm median by 2.25% and increased the sum-bits median by 2.24%. Four repeats constrain conclusions about the timing differences. The combined measurements still take 2.08× and 1.50× the respective vanilla times on 3mm and sum-bits. [Full timing samples and source/physical checks](results.json)

| Program | Reprojections moved | Winning marks moved | Extra input values avoided | Peak multi-parent ticket entries, ordinary → scoped | Source RHS | Recipe-allocated / fresh physical Cells |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 2,677 | 2,677 | 10,686 | 4,588 → 122 | 7,265 | 5,867 / 5,868 |
| 3mm | 147,952 | 147,952 | 646,333 | 146,965 → 7,696 | 294,917 | 229,311 / 229,880 |

Each arm preserved raw proposed tuples and their order, single- and multi-parent winners, actual root and nested physical IDs, ordered source RHS and writes, union events, Spine resumes, schedule, and final graph. All source RHS had neural provenance with exact completion disabled. The withdrawal check in each receipt arm rejected a missing input before ordered consumption.

## Whole-process high-water RSS

Each macOS sample is one native child that imports the program and graph, performs one complete unaudited inference and exports the result. Three rotating samples per arm follow one warmup. The high-water mark includes code, initialization, model, graph, verifier, export and teardown. The child also checks Run/RHS totals, final graph and direct root count against the audited execution.

| Source | Off MiB | Run tickets MiB | All MiB |
|---|---:|---:|---:|
| sum-bits | 271.66 | 269.89 | 269.86 |
| 3mm | 747.14 | 693.50 | 699.66 |

On 3mm the isolated Run directory reduced the full process high-water mark. The handoff timings and RSS come from distinct executions. [Per-process byte measurements](rss.json)

## Reproduction

Use the existing external Pass 3 inputs, native vanilla executable and frozen weights. Each output directory must be new.

```sh
d=benchmarks/pass3-cell-gpu/verified-binding-transfer
python "$d/build.py" "$EXP/binding-transfer"
python "$d/study.py" "$EXP" "$EXP/binding-transfer/session" "$EXP/binding-transfer-results"
python "$d/peak.py" "$EXP" "$EXP/binding-transfer/session" "$EXP/binding-transfer-results/results.json" "$EXP/binding-transfer-rss"
python "$d/verify.py"
```
