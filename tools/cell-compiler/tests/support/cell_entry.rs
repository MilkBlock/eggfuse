use eggfuse_cell_runtime::{compiler, iterative::{Catalog, Limits}, program::{Call, Program}};
use serde_json::json;

// The keeper already demands A's receipt for RHS reuse. The residual consumer
// must use that same published receipt, without another capture/history packet.
pub const SOURCE: &str = r#"
(datatype E (N i64) (A E) (B E i64) (Edge E i64) (Out E i64) (Keep E))
(ruleset make) (ruleset consume) (ruleset keep)
(rule ((= x (N n))) ((A x) (B x n)) :ruleset make :name "producer")
(rule ((B x n) (= a (A x)) (Edge x y)) ((Out a y)) :ruleset consume :name "consumer")
(rule ((B x n)) ((Keep (A x))) :ruleset keep :name "keeper")
(A (N 0)) (A (N 1))
(Edge (N 0) 10) (Edge (N 0) 11) (Edge (N 1) 12)
(run-schedule (seq (run make) (run consume) (run keep)))
(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))
"#;

pub fn program(source: &str) -> Program {
    let core = eggfuse_bake::device_frontend::core("witness-sources", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let id = |name| rules.iter().position(|r| r["metadata"]["name"] == name).unwrap();
    let (producer, keeper) = (id("producer"), id("keeper"));
    let publication = rules[producer]["effects"].as_array().unwrap().iter()
        .position(|e| e["call"]["table"] == "B").unwrap();
    let pivot = p.rules[keeper].query.iter()
        .position(|a| matches!(a.call, Call::Table(t) if p.tables[t].name == "B")).unwrap();
    let profile = json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":[{"edge":[producer,publication,keeper,pivot],"visits":2}]});
    let leaves = compiler::bake_stage_blocks(&p, &profile, &p, 1).unwrap();
    assert_eq!(leaves["entries"].as_array().unwrap().len(), 1);
    let mut raw = p.artifact;
    raw["spine_blocks"] = leaves;
    let p = Program::parse(raw).unwrap();
    let mut plan = Catalog::seed_with_roots(&p, Limits { support: 1, ..Default::default() }, &[producer]).unwrap();
    plan["joins"] = json!([{"left":1,"output":publication,"right":0}]);
    Catalog::emit_query_handoffs(&p, &mut plan).unwrap();
    let mut raw = p.artifact;
    raw["iterative_bake"] = plan;
    Program::parse(raw).unwrap()
}

pub fn aliased_source(source: &str) -> String {
    source.replace("(N i64)", "(N i64) (Seed i64)")
        .replace("((= x (N n))) ((A x) (B x n))", "((Seed n)) ((A (N n)) (B (N n) n))")
        .replace("(run-schedule", "(Seed 0) (Seed 1)\n(run-schedule")
}

pub fn replaced_source() -> String {
    SOURCE.replace("(ruleset make)", r#"
(ruleset reset) (ruleset again) (ruleset late)
(rule ((B x n)) ((delete (B x n))) :ruleset reset)
(rule ((= x (N n))) ((A x) (B x n)) :ruleset again)
(rule ((= x (N n))) ((Edge x (+ n 100))) :ruleset late)
(ruleset make)"#)
        .replace("(run consume) (run keep)",
            "(run consume) (run reset) (run consume) (run again) (run late) (run consume) (run keep)")
        + "\n(check (Out (A (N 0)) 100) (Out (A (N 1)) 101))\n"
}

pub fn full_source() -> String {
    SOURCE.replace("(Edge x y)) ((Out a y))", "(= n y)) ((Out a y))")
        .replace("(check (Out (A (N 0)) 10) (Out (A (N 0)) 11) (Out (A (N 1)) 12))",
            "(check (Out (A (N 0)) 0) (Out (A (N 1)) 1))")
}


// Candidate aliases and scalar results must follow each borrowed expansion row,
// including a later delta whose owner is the expanded relation itself.
pub fn borrowed_source() -> String {
    SOURCE.replace("(Edge E i64)", "(Edge E i64 i64)")
        .replace("(Edge x y)) ((Out a y))", "(Edge x y y) (= z (+ y n)) (< z 25)) ((Out a z))")
        .replace("(Edge (N 0) 10)", "(Edge (N 0) 10 10)")
        .replace("(Edge (N 0) 11)", "(Edge (N 0) 11 11)")
        .replace("(Edge (N 1) 12)", "(Edge (N 1) 12 12) (Edge (N 0) 20 21) (Edge (N 0) 50 50)")
        .replace("(ruleset make)", r#"
(ruleset late)
(rule ((= x (N 1))) ((Edge x 14 14)) :ruleset late)
(ruleset make)"#)
        .replace("(run keep)", "(run keep) (run late) (run consume)")
        .replace("(Out (A (N 1)) 12)", "(Out (A (N 1)) 13) (Out (A (N 1)) 15)")
}
