# Carry a checked multi-parent root with the winning source instance

The native Cell CPU engine builds a verified root for every successful independent multi-parent match. The directory control stores a ticket containing that root for every validated tuple until the Pass exits. An instance keeps its ordinal, then the original commit clones its ticket and looks up its checked root again.

The new path keeps the exact checked root and its serial, source rule and width with the move-only query instance through winner selection. A losing instance drops its claim with its other fields. The surviving instance transfers ownership directly to the original ordered RHS; that loop verifies the serial and rule then updates ordinary commit and width counters. The existing root checks its Run, template and checked slot projection before supplying the physical Cell's inputs. Merge descendants keep the pre-dedup ordinal. Spine, repair, fresh Cell registration and source ordering continue through the same native execution code.

The detailed audit constructs the independent ticket archive and requires the instance's root pointer, original serial, rule, width and slot vector to agree with the legacy ticket. Production records the same counters and constructs zero archive entries when handoff is enabled. A deliberately changed serial must fail at the first affected source commit. The previous verified-binding-transfer experiment retained the directory for the duration of each Run; this arm removes it from ordinary execution altogether. It preserves the independently checked RHS slot buffer and parent verification.

Both measurement arms use identical scalar negative certificates, packed single-parent waves and the same frozen neural issuer and exact suffix verifier. The added optional claim fields occupy space in the instance representation of both arms. The caller wall timer covers the request, native inference, result construction and reply on a prepared process; it excludes startup and the independent audit. The dedicated RSS samples start new processes and include initialization and export.

## Matched native runs

| Program | Multi-parent root transfers | Ticket vector, MiB | Native inference, ms | Prepared caller wall, ms | Process peak RSS, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| conjugate-gradient | 57,695 | 6 → 0 | 636.42 → 640.68 | 735.65 → 760.64 | 464.05 → 449.42 |
| 3mm | 146,965 | 24 → 0 | 1,731.99 → 1,777.55 | 1,974.99 → 2,033.96 | 758.48 → 704.53 |

In both workloads every validated multi-parent claim went on to win. Dropping a claim at commit shortened retention, while losing-match reclamation had no opportunity here. Moving the proof reduced peak RSS in both full-process measurements. Both native inference and prepared caller wall were slower at the measured medians. RHS phase medians on CG were 118.83 → 118.03 ms and on 3mm 291.88 → 296.78 ms. Search occupied about 69–73% of the control inference time. These traces provide no evidence of a twofold inference speedup from eliminating the directory. The shared prototype source instance was 272 bytes in both arms.

All 131,371 CG and 294,917 3mm RHS firings matched the independent CPU reference. The winning parent, physical root and child digests agree, as do ordered writes, Spine resumptions, unions, schedule, final graph, issued page streams and model decisions. A modified claim serial failed explicitly on both programs. The table uses six rotating resident samples per arm after a warmup and median RSS over three fresh processes per arm. [Native timings and complete audits](results.json) · [Peak RSS](rss.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/instance-handoff-build"
python3 study.py "$exp" "$exp/instance-handoff-build/session" "$exp/instance-handoff-time"
python3 peak.py "$exp" "$exp/instance-handoff-build/session" "$exp/instance-handoff-time/results.json" "$exp/instance-handoff-rss"
python3 verify.py
```
