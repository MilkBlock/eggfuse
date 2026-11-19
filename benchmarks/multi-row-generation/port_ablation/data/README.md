# Candidate frontiers and full-witness acceptance

The generator reads the two ordered `stages` in each row of the Bake corpus manifest. Run 1 joins four bound producer frames A to four candidate functional fact rows B. Run 2 joins the generated fact rows to four candidate consumer frames, including their residual key/result columns when present. Each predicate and projected output column comes from the selected template. `side=2` is an integer literal. `Unit` columns always carry zero. Other free columns use typed integer symbols in 0–7. The four B rows have distinct complete keys. Two producer events may consult the same B fact and remain distinct source events.

The generator constructs candidate inputs around a random subset of desired witnesses, including empty and multiply matching cases. It enumerates *all* witnesses on the resulting source tables before assigning labels. Samples with more than eight complete witnesses in either Run are resampled, so no gold set is truncated. This is a bounded synthetic frontier experiment. The typed contracts come from real Bake compositions. Complete workload data, effect execution, canonical union history and full eggcc scheduling lie outside the data generator.

`dataset(split, template)` returns integer source arrays `a`, `b`, `requests` and unordered padded labels. A target row stores activation, two indices and the full ordered projected row. A Run 1 target references source A/B slots. For training, a Run 2 target references a Run 1 *label* and a supplied Request slot. Deployment inputs contain none of those labels. Run 2 audit follows the predicted index into actual generated Run 1 slots. `request_slots` aliases the second pointer in the Run 2 labels.

## Split and counterfactuals

Every training template has 1,024 seeded training graphs. Both seen and held-out templates have 64 fresh IID samples and a separate 64-graph collision panel. Holdout templates are rejected by `dataset('train', ...)`. Structural signatures for the two stages preserve all column positions, normalize predicate order and operand symmetry, and omit template IDs, graph names and sorts. `freeze.py` checks that no signature crosses the train/held-out boundary. An identical-input substitution across equal-width templates separately checks that different source wiring can change the required bindings.

Each collision panel contains 32 pairs of counterfactual consumer queries. Within a twin pair A and B stay fixed. The same two real producer witnesses have identical values on some but not all output columns. The varied Request differs only in the columns required to activate the other parent. In each graph its sibling parent fails an actual consumer predicate. A single correct request slot or field guess cannot serve both twins. The `probe` array stores both witness identities `(A index,B index)` and the changed Request slot for post-run analysis. It is excluded from model inputs. Nonempty training and IID graphs also include collisions. The novel condition under study is the held-out wiring family. Twin members are correlated samples.

Consumer rows are candidate bound frames. On templates with a residual read, some candidate sets can contain different results for the same residual key. The audit labels `residual_reads_consistent` on every graph, indicating only whether the supplied residual keys have unique values *within that graph*. Per-graph entries permit recomputation of complete coverage, wrong parents, duplicates and omissions on the physically consistent subset. Other feasibility conditions of a full source program have not been reconstructed.

## Scoring

The CPU verifier builds Cartesian products from source arrays, applies the compiler equalities to a NumPy boolean mask and derives the exact projected rows. It works independently of the scalar label interpreter and reads no target labels. Every result must identify an actual active generated parent and a valid supplied consumer frame. A source obligation is one `(A event,B fact,Request event)` witness. Distinct source events producing identical rows can both be valid. The reported complete set is a witness set, distinct from the number of physical RHS records ultimately committed after deduplication.

- `wrong_live_parent` counts a selected live, legally generated source binding that fails the chosen consumer's actual constraints. `absent_parent_reference` counts an inactive or unavailable generated slot. `illegal_producer_binding` counts an active slot whose own source match was illegal. Invalid Request positions and Request rows with zero source witnesses have their own counts. These five disjoint categories make up `illegal`.
- `duplicates` counts repeated legal witness identities; `missing` counts unseen legal witness identities. Wrong projected values and wrong consumed-parent payloads are tracked, so semantic completeness also accounts for both rows. A different parent satisfying all source constraints is legal. Emitting one legal parent twice and thereby omitting a different required legal parent yields one duplicate and one omission.
- `unavailable_parent_obligations` counts source obligations whose correct parent identity and payload never appeared in Run 1. It is measured over required witnesses, independently of which slots Run 2 selected. `parent_ready_nonempty_graphs` and `parent_ready_nonempty_complete_graphs` condition consumer success on all required correct parents actually being present.
- `wrong_live_parent_same_payload` compares only the payload columns shared by the controlled twins when a probe is present. An actual join column is still different. On other samples it compares the complete source row. Exactly identical full rows satisfy the same source predicates and can give rise to multiple legal witnesses.
- `probe_wrong_twin` counts choices of the deliberately similar but invalid sibling parent for the varied Request. `probe_claims_exact` counts controlled requested witness identities emitted correctly exactly once. Whole-graph completeness additionally checks every other demand and excludes extras.

Use `freeze.py OUTPUT.json` to reproduce split statistics and hashes. `test_port_data.py` checks that permuting physical output slots preserves valid ancestry, wrong twins and absent references are separately rejected, and alternative legal parents are not called wrong.

## Frozen corpus

The manifest contains 12 training templates covering nine type-erased wiring signatures and seven held-out templates covering two more signatures. The 12,288 training graphs contain 11,092 nonempty second-Run graphs. Held-out IID has 407 nonempty graphs among 448, with 950 source consumer witnesses. The 448 held-out collision graphs are all nonempty and have 917 witnesses; they form 224 counterfactual pairs. Of these collision graphs, 317 satisfy the residual-read functional consistency filter. Membership is fixed by source data independently of the model. Do not treat all 448 as observed states from an actual eggcc execution.

On the 64 same-width collision inputs of template `t-190d47775d444806`, substituting the wired checks/projections of `t-27bf08b4a5836427` changes the first source witness set on 62 graphs and the second on 60. This counterfactual concerns interface-level obligations. The rest of the caller program and effect scheduling would also need to be considered for a whole-program substitution.

When reporting similar-parent errors, the deliberately colliding parent shares
only some payload columns. A genuine key/check column distinguishes it. If the
entire projected row is equal and both source witnesses satisfy the consumer,
both are legal. The primary wrong-live-parent count excludes references to a
missing/inactive parent, illegal producer bindings and consumer observations
with no source match. These categories remain visible separately.
