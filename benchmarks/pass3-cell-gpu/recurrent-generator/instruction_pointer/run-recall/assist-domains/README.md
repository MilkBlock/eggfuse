## Native assist on sealed, typed port domains

The CPU Actor and the native Cell receiver ran the full source schedule on fact, loopfact and sum-divisors. These EggCC programs have guided development. Both root-threshold calibrations used 50 reserved Runs from 21 training programs. The 221,770 terminal training requests came from sum-bits (100,599), dot-product (120,502) and 48 generated training programs (669). The source/program/tape identities and checkpoint lineage are recorded in the [training exposure audit](../assist-cost/training-split.json). The Actor weights stayed frozen for the domain comparison.

**Work removed.** Only the bounded, port-local Actor opts into projected encoding by default. Each Run uses the union of the possible typed read domains of the scheduled rules. A legal fresh anchor retains the complete typed domains for its other inputs, including old independent parents. The reduction happens before neural encoding. The receiver sends its normal sealed history. Python still processes and shuffles that history. No host predicate compares parent fields or supplies pairs.

For a pivot whose compiled continuation uses only deterministic primitives and point reads, one input row can yield at most one distinct projected RHS binding. A full-table cardinality certificate can discharge the rule. At a seminaive boundary the receiver can also discharge the rule when it accounts for every fresh Entry in every orientation using the named witnesses and point continuations. Missing proofs retain ordinary matching, and native continuation handling stays on the original boundary. Proof costs include scanning fresh entries and allocating temporary witness sets.

| Program | Visible ports visited → encoded | Exact matching outputs, old → new | Native residual candidates, old → new | Additional rule calls skipped | Fresh entries checked |
|---|---:|---:|---:|---:|---:|
| fact | 1,769,135 → 79,060 | 1,573 → 1,314 | 1,848 → 1,845 | 39 | 571 |
| loopfact | 1,718,698 → 70,913 | 1,348 → 1,161 | 1,634 → 1,626 | 51 | 511 |
| sum-divisors | 36,307,164 → 2,524,397 | 17,179 → 16,111 | 22,685 → 22,677 | 242 | 2,813 |

The 32,425 requests, including the order, named parents and versions, were byte-identical with both encoders on all three programs. Native verification credited 10,840 distinct commits out of 20,428, marked 18,833 duplicates and rejected 2,752. Exact search supplied 9,588 commits. Comparison of the prior and current receivers covered every pre-write observation, ordered schedule, RHS, writes, resumes, events and final state. Full, incomplete and wrong-version streams exercise the fallback separately. An additional prototype for discharging individual direct-rule seeds activated zero times on each of the three programs and was discarded.

**Rule-start precision.** A separate full assist pass enabled the previously trained seminaive rule screen. It reads the scheduled rule's prior commit age and per-table visible and fresh port counts. Its cutoff was frozen on training-program data. Productive activations (rules with a reference commit that Run) went from 3,055/13,912 to 3,039/13,206, or 21.96% to 23.01%. Across the three programs it eliminated 22 proposals, including 13 duplicates and nine unique accepted commits on sum-divisors. The rejected count stayed at 2,752. All three final states and ordered audits still matched with residual search. The primary timing series uses the frozen Actor without this extra screen.

**Independent execution.** With residual search off, the first mismatching Runs remain 7, 8 and 11. Sum-divisors reaches a source panic at Run 85. Of 144 generated held programs, 143 reproduce the exact final state. The complete real assist result relies on the residual matcher.

**Paired CPU timing.** Each program ran four alternating exact / assist / offline teacher comparisons using the same release binary on an Apple M3 Max. Each arm launched a fresh native process. The service was warm and loaded the frozen Actor for each timed assist. Wall includes process startup, parsing and final export. Assist also pays for its online history, encoding, transfer and inference. Audit-mode encoder comparisons ran alongside part of the timing series on the same machine, so small differences between the oracle and exact wall times require caution.

| Program | Exact wall (s) | Oracle wall (s) | Assist wall (s) | Actor (s) | Verify all (ms) | Rejected portion (ms) | Residual matcher (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|
| fact | 0.146 | 0.143 | 2.645 | 1.705 | 2.64 | 0.15 | 6.33 |
| loopfact | 0.147 | 0.148 | 2.714 | 1.749 | 2.98 | 0.17 | 7.42 |
| sum-divisors | 0.230 | 0.228 | 49.646 | 33.260 | 17.98 | 1.13 | 49.28 |

The exact arm won all twelve comparisons against live assist. With decoding and final export excluded, the native in-memory teacher replay took 7.03, 6.45 and 49.86 ms, versus 7.94, 7.96 and 58.12 ms for native search. This oracle signs the complete stream in advance and incurs zero model cost. In a separate full-audit comparison, changing only the Actor port path reduced the median wall from 21.67 to 2.82 s on fact and from 21.40 to 2.62 s on loopfact (four wins per program). The sum-divisors encoder comparison checks stream equality and encoding work only.

**Reproduction.** Run the following from the instruction_pointer directory. ROOT contains the exported native programs, reference captures and model training manifest. Set OLD and NEW to the previous and current release cell_token_replay binaries and WEIGHTS to the frozen opaque Actor checkpoint. ART holds outputs. SCREEN is the previously trained rule-start screen. All timed Actor inference uses one PyTorch CPU thread.

```sh
mkdir -p "$ART"
git show HEAD:benchmarks/pass3-cell-gpu/token-replay/study.py > "$ART/oracle_study.py"
python audit_parent_split.py "$ROOT" "$ROOT/alternate-proofs/root-calibration" "$ART/training-split.json"
python check_addressable_ports.py "$ROOT/fact"
for name in fact loopfact sum-divisors; do
  python "$ART/oracle_study.py" "$NEW" "$ROOT/$name/program.json" --output "$ART/oracle-$name.json"
  python live_domain_study.py "$ROOT" "$name" "$OLD" "$WEIGHTS" "$ART/$name-full.json" "$ART/$name-full-stream.json"
  python live_domain_study.py "$ROOT" "$name" "$NEW" "$WEIGHTS" "$ART/$name-live.json" "$ART/$name-issues.json" --project
  cmp "$ART/$name-full-stream.json" "$ART/$name-issues.json"
  python assist_domain_audit.py "$ROOT/$name" "$ART/$name-issues.json" "$OLD" "$NEW" "$ART/$name-audit.json"
  python assess_assist_screen.py "$ROOT" "$NEW" "$WEIGHTS" "$ART/$name-plain.json" --case "$name"
  python assess_assist_screen.py "$ROOT" "$NEW" "$WEIGHTS" "$ART/$name-screen.json" --case "$name" --screen "$SCREEN"
done
python check_assist_domains.py "$ROOT" "$OLD" "$NEW" "$ART/negative.json" --issues "$ART"
python prefix_exclusive.py "$ROOT" "$NEW" "$WEIGHTS" "$ART/exclusive.json" --top-k 32
python port_cost.py "$ROOT" "$NEW" "$WEIGHTS" "$ART" --cases fact loopfact
python assist_cost.py "$ROOT" "$NEW" "$WEIGHTS" "$ART/cost" --cases fact loopfact sum-divisors --project-ports
python summarize_domains.py "$ART" "$ART/summary.json"
```
