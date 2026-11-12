# Keep the Cell in place during constructor registration

This is the actual standalone Cell CPU, not native egglog performance. Work
checks compare with `0ef4a130` using the same frozen programs, catalog, release
features and arguments. This is implementation five after timing checkpoint
`2166a3fb`; the separate periodic timing gate determines speed acceptance.

## Opportunity and ownership

The preceding catalog execution returned 32,433 Cell frames through registration
events. It paid for removing/reinserting each entire Cell in the dense arena,
which can relocate another physical record, although the worker only writes
that Cell's fact slots. It also retained an `Installed` record for every Cell
and scanned the complete successful prefix after all owners returned.

The compiled terminal instruction region supplies the existing proof: no
intervening union, mutable read, fallible suffix or other Function allocation;
sealed Eq inputs; fresh constructor slots; exact old/new Unit merge; and no
pending dirty/union work. Parents in a leased region precede children. The
registration owner does not write input values, parent links, execution position
or lifecycle state. Those parts of the same Cell can remain where they are.

Only the original fact-slot container now moves to the worker and back in its
completion buffer. The Cell stays in its existing arena position. The worker
continues to install the actual facts and original shared indexes; the source
attaches those slots once before completing the Cell. The source then consumes
publication certificates directly from that same event buffer. There is no
second all-Cell certificate vector.

The source/error protocol permits an additional deletion: it completes each
offered Cell before offering the next, and stops offering on error while still
draining every owner. Therefore only the last offered Cell and the untouched
suffix need rollback certificates. An error after taking a certificate but
before committing that Cell must retain the last certificate. Success no longer
scans every completed Cell after the registration scope.

These are representations of the same existing Cell, not another fact graph,
binding copy, marker relation or per-producer subscription list. Existing actual
returned witnesses and compiled Shared Entry projections remain authoritative
across Runs. The catalog already repeatedly exercises this terminal shape;
this change deletes its handoff/retirement work without adding a new catalog or
claiming extra query elimination. The Run visibility fence, source order and
exclusive shared-index owners remain live obligations.

## Work evidence and remaining cost

| Raytrace observation | `0ef4a130` | Candidate |
| --- | ---: | ---: |
| Event payload per Cell | 200 bytes | 104 bytes |
| Cells passing through constructor registration | 32,433 | 32,815 |
| Success retirement checks | 32,433 (old full scan) | 988 |
| Constructor metadata capacity, cumulative bytes | 6,435,208 | 4,019,120 |
| Cell/fact event capacity, cumulative bytes | 6,486,600 | 3,412,760 |
| All six recorded registration/handoff capacity counters | 28,937,456 | 23,741,032 |
| Cells completed with registration work still pending | 16,535 | 16,441 |
| Unit subscriptions handled by the existing worker owner | 64,866 | 65,630 |

The payload is 48% smaller, and cumulative recorded capacity falls by 5,196,424
bytes (18.0%). The old retirement-check count follows its exact per-frame loop;
the candidate counts actual checks, one last-offered check per successful
constructor region. The pointer/layout test verifies that leasing and returning
facts never changes the Cell arena order or physical positions.

Capacity counters are not peak memory or total allocator traffic. Original fact
payloads and slot values are not deep-copied. Event arrival changes region sizes,
coverage and some counter totals; these are not counts of logical effects
removed. The existing early-completion counter includes queued followups and
does not establish CPU utilization or time saved. Reserved invalid Function
slots and all real reverse incidences remain costs.

Sum-bits has no eligible registration region; this takeover does not directly
improve its four-worker path. Work-count reductions alone do not establish an
end-to-end speedup for either workload.

## Validation

170 runtime tests and 87 relevant integration tests pass, along with forced
hash/Bloom collision checks, 20 repeated blocking handshakes, all-feature,
sparse-only and legacy builds. Constructor tests now exercise the production
ownership path rather than a separate borrowed-owner helper. They check errors
both before and after taking an uncommitted publication certificate, actual
row-allocation identity, retained changes/subscriptions, and a subsequent
union/repair against ordinary source execution. The handshake still blocks
constructor directories and subscriptions until an earlier Cell prefix commits.

Exact final exports, 1,428 / 16,883 ordered Run summaries, logical effects,
queries, reverse-edge work/occupancy, Sieve counts and iterative Bake evidence
agree with the control. Omitted root-read counts can change with eligible region
coverage; all other maintenance counters must agree. This is work accounting,
not a change to the semantic contract. Integration fixtures cover Run-boundary
visibility, deletion/recreation, late union and actual returned aliases; final
exports and Run summaries alone do not prove every intermediate state.

The unchanged native sum-bits choice validator passes and is linked to the
fresh CPU export hash. Raytrace remains exact differential validation. README
compile/run/one-repeat bench commands pass as smoke checks, not timing evidence.
See [results.json](results.json) for commands, counts and hashes.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

Use fresh output paths when reproducing the commands recorded in
`out/cell-fact-lease/manifest.json`:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-fact-lease/semantic-acceptance.json
python3 benchmarks/cell-fact-lease/check.py out/cell-local-registration out/cell-fact-lease benchmarks/cell-fact-lease/results.json
cargo cell-compile --case sum-bits --output out/cell-fact-lease/readme-program
cargo cell-run --program out/cell-fact-lease/readme-program/program.json --output out/cell-fact-lease/readme-run
cargo cell-bench --program out/cell-fact-lease/readme-program/program.json --repeat 1
```
