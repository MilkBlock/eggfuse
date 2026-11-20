# Typed pages for verified root receipts

The full standalone Rust Cell CPU executor runs the frozen neural parent issuer, exact LHS verifier and original ordered source RHS. Both independent-parent and single-parent batches issue all model-chosen addresses before their validators inspect the source rows. The prior CPU configuration hashed the identity and address of every issued tuple during ordinary inference. It also packed every single-parent page into a fresh word buffer after the issuer had already collected an owned vector of typed source addresses. When validation succeeded, both page formats allocated a fresh vector of parent references for the bound recipe. Commit only consults that vector when detailed provenance is enabled.

This study keeps the [joint CPU configuration](../composed-cpu/README.md), including shared single-parent headers, lazy arithmetic ports and the frozen tied weights. The repository's [earlier binding transfer](../verified-binding-transfer/README.md) moved marks and released a pass-wide ticket directory. This experiment measures the initial issuing and binding of those marks. Ordinary source scheduling and physical Cell allocation continue to use their original code.

## Controls

- **Off** keeps the ordinary page and computes its diagnostic FNV fingerprint. **Hash** skips this optional fingerprint in production. The report returns a JSON null for a fingerprint that was not computed. Checked serial numbering and all graph operations still execute. Detailed audits compute the original fingerprint on every arm.
- **Borrow** validates the single address directly on the stack or borrows a multi-parent slice from its immutable page. The single-parent verifier directly reads the known receipt of a requested atom. The production bound retains the selected template, source epoch, serial and checked RHS values until consumption. After a successful bind the parent-reference archive is needed only in the detailed run.
- **Atoms** adds a stack mask covering source atoms whose identity and liveness were verified during this binding. Every explicit parent still checks its own advertised source row and version. Later compiler projection fields of the same atom reuse that check. Every projected RHS field still reads its typed value. Atoms beyond the inline mask retain individual checks.
- **Headers** adds a typed `(table, epoch)` accessor to the borrowing arm. It obtains both fields with one visit to the source fact or function header. Hidden facts, retired functions and unsupported instruction kinds supply no valid header. **Typed** instead transfers the gather vector directly into the immutable single-parent page. There is no second packed payload. The original wire encoding digest can still be independently streamed from the typed page during audit.
- **All** uses borrowing, grouped atoms, fused header reads, typed single pages and audit-only fingerprinting. The graph validates the current source layout, Run, template and version, then delivers the bound input buffer once at the original commit point. It checks the winning inputs and template again at commit and allocation.

## Measurement

A source-only CPU binary supplies ordered RHS, effective writes, actual Spine resumes, union history, schedule and final graph. Detailed runs compare individual winning parent identities, root ordinals and physical Cell IDs. Each uninstrumented timing also checks the final state and Run count, the sealed/applied/allocated counts and the activity of the actual optimization, including the incidence of archived references. Timings are single-process resident inference after one warmup. Arms rotate and reverse across four repetitions at seed 1703. Separate injected faults cover expired versions, wrong templates and withheld pages.

```sh
d=benchmarks/pass3-cell-gpu/lean-root-receipts
python "$d/build.py" "$EXP/lean-root"
python "$d/study.py" "$EXP" "$EXP/lean-root/session" "$EXP/lean-root-runs" --cases sum-bits 3mm
python "$d/verify.py"
```

The timing differences measure all costs of implementing each arm. Packed bytes avoided count the old transient word image and exclude the still-owned typed address vector. No total heap or RSS reduction is inferred from that counter. Source-header savings count redundant checks of a single atom inside one immutable binding. Neither a repeated source address at another atom nor a reference from a later Run can use that mask.

## Measured full inference

| Program | Vanilla | Off | Hash | Borrow | Atoms | Typed | Headers | All, ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.73 | 30.80 | 30.68 | 30.92 | 30.37 | 31.15 | 31.31 | 30.83 |
| 3mm | 884.94 | 1,909.24 | 1,957.57 | 1,978.68 | 1,876.53 | 1,908.52 | 1,907.36 | 1,888.46 |

| Program | Diagnostic tuple hashes omitted | Typed single-parent rows | Old wire bytes avoided | Source refs checked, retained after bind | Physical header checks, off → all | Source RHS | Direct / all fresh Cells |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 13,801 | 7,889 | 287,128 | 12,872, 0 | 50,745 → 15,371 | 7,265 | 5,867 / 5,868 |
| 3mm | 1,066,140 | 845,168 | 20,817,600 | 510,693, 0 | 2,031,145 → 688,003 | 294,917 | 229,311 / 229,880 |

On 3mm the combined median decreased 1.09%, with two of four paired runs faster. Sum-bits increased 0.10%, also with two paired wins. Grouped checks alone had the lowest observed 3mm median. These results show actual avoided work without a consistent full-pass latency advantage. All three multi-parent faults stop at RHS 17 on sum-bits. Wrong-port, wrong-template and withheld roots stop at the same first RHS as the original checker. The wrong-port test on a nullary rule also exercises rejection of an out-of-range atom before accessing the source receipt array. [Per-run evidence, source checks and timings](results.json)
