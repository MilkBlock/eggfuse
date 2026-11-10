#![cfg(feature = "sparse-cells")]
use eggfuse_cell_runtime::{
    compiler,
    executor::Executor,
    graph::Graph,
    iterative::{Catalog, Limits},
    program::Program,
};
use serde_json::json;

const SOURCE: &str = r#"
(datatype E (N i64) (Get E i64) (Single E) (SubTuple E i64 i64) (Seen E))
(ruleset seed) (ruleset a) (ruleset b) (ruleset read) (ruleset retire)
(rule ((= x (N i))) ((Get x i)) :ruleset seed)
(rule ((Get x i)) ((union (Single (Get x i)) (SubTuple x i 1))) :ruleset a :name "producer")
(rule ((= s (SubTuple x i 1))) ((union s (Single (Get x i)))) :ruleset b :name "consumer")
(rule ((Single g)) ((Seen g)) :ruleset read)
(rule ((Get x 999)) ((delete (SubTuple x 999 1))) :ruleset retire)
(N 1) (N 2) (Single (Get (N 1) 1))
(run-schedule (seq (run seed) (run a) (run b) (run read) (run retire) (run a) (run b) (run read)))
(check (Seen (Get (N 1) 1)) (Seen (Get (N 2) 2)))
"#;

fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("joint-results", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let named = |name| {
        rules
            .iter()
            .position(|r| r["metadata"]["name"] == name)
            .unwrap()
    };
    let (a, b) = (named("producer"), named("consumer"));
    let output = rules[a]["effects"]
        .as_array()
        .unwrap()
        .iter()
        .position(|op| op["call"]["table"] == "SubTuple")
        .unwrap();
    let profile = json!({"schema":"eggfuse-spine-shapes/v1", "program_sha256":p.artifact["sha256"],
        "prefixes":[{"edge":[0,0,a,0],"visits":2},{"edge":[0,0,b,0],"visits":2}]});
    let blocks = compiler::bake_spine_blocks(&p, &profile, &p, 2).unwrap();
    let entries = blocks["entries"].as_array().unwrap();
    let left = entries.iter().position(|e| e["consumer"] == a).unwrap();
    let right = entries.iter().position(|e| e["consumer"] == b).unwrap();
    let mut raw = p.artifact;
    raw["spine_blocks"] = blocks;
    let p = Program::parse(raw.clone()).unwrap();
    let mut plan = Catalog::seed(&p, Limits::default()).unwrap();
    plan["joins"] = json!([{"left":left,"output":output,"right":right}]);
    Catalog::emit_handoffs(&p, &mut plan).unwrap();
    raw["iterative_bake"] = plan;
    Program::parse(raw).unwrap()
}

#[test]
fn rhs_results_survive_entry_delivery_and_boundary_recreation_without_recapture() {
    for source in [
        SOURCE.to_owned(),
        SOURCE
            .replace("(Get x 999)", "(Get x 1)")
            .replace("SubTuple x 999 1", "SubTuple x 1 1"),
    ] {
        let mut audited = None;
        for audit in [true, false] {
            let p = program(&source);
            let mut reference =
                Executor::new(Graph::new_with_local_congruence(p.clone()).unwrap(), audit);
            let mut shared = Executor::new(Graph::new_with_local_congruence(p).unwrap(), audit);
            shared.use_entry_publications().unwrap();
            #[cfg(feature = "iterative-bake")]
            let digests = {
                let execute = |e: &mut Executor| {
                    use eggfuse_cell_runtime::transfer_audit as audit;
                    audit::set_active(true);
                    audit::enable_write_audit();
                    e.execute().unwrap();
                    audit::set_active(false);
                    (
                        audit::take_digests(),
                        audit::take_write_digests(),
                        audit::take_resume_digests(),
                    )
                };
                let expected = execute(&mut reference);
                let actual = execute(&mut shared);
                assert_eq!(expected, actual);
                actual
            };
            #[cfg(not(feature = "iterative-bake"))]
            let digests = {
                reference.execute().unwrap();
                shared.execute().unwrap();
            };
            assert_eq!(reference.snapshots, shared.snapshots);
            assert_eq!(reference.binding_audit, shared.binding_audit);
            assert_eq!(
                reference.graph.export().unwrap(),
                shared.graph.export().unwrap()
            );
            let a = reference.report();
            let b = shared.report();
            let old = &a["stage_spine"]["stats"];
            let new = &b["stage_spine"]["stats"];
            let runs = shared
                .steps
                .iter()
                .map(|s| {
                    [
                        "ordinal",
                        "ruleset",
                        "path",
                        "iterations",
                        "epoch",
                        "logical_matches",
                        "executed_bindings",
                        "changed",
                    ]
                    .map(|k| s[k].clone())
                })
                .collect::<Vec<_>>();
            let signature = (digests, shared.graph.export().unwrap(), runs);
            if audit {
                assert_eq!(
                    new["joint_history_frames"], 0,
                    "audit uses raw receipt capture"
                );
                audited = Some(signature);
            } else {
                assert_eq!(
                    audited.as_ref().unwrap(),
                    &signature,
                    "shared storage must match raw capture"
                );
            }
            if !audit {
                assert!(new["joint_history_frames"].as_u64().unwrap() > 0, "{new}");
                assert!(new["joint_output_reads"].as_u64().unwrap() > 0, "{new}");
                assert!(new["history_shared_slots"].as_u64().unwrap() > 0);
                // Both executors automatically own eligible Entries. This fixture
                // covers only joint captures: no second history copy may remain.
                // Work savings against old code are checked with a frozen binary.
                assert_eq!(new["history_capture_reads"], 0);
                assert_eq!(new["history_slots_written"], 0);
                assert!(new["history_result_reads"].as_u64().unwrap() > 0);
                assert_eq!(new["cell_output_receipts"], new["cell_output_deliveries"]);
                assert_eq!(old["history_result_reads"], new["history_result_reads"]);
            }
            for (a, b) in reference.steps.iter().zip(&shared.steps) {
                for key in [
                    "ordinal",
                    "ruleset",
                    "path",
                    "iterations",
                    "epoch",
                    "logical_matches",
                    "executed_bindings",
                    "changed",
                ] {
                    assert_eq!(a[key], b[key], "{key}");
                }
            }
            assert_eq!(reference.steps.len(), shared.steps.len());
            let mut native = egglog::EGraph::default();
            native.parse_and_run_program(None, &source).unwrap();
        }
    }
}
