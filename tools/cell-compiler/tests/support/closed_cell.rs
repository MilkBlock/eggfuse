use eggfuse_cell_runtime::{compiler, iterative::{Catalog, Limits}, program::Program};
use serde_json::json;

pub const SOURCE: &str = include_str!("../fixtures/closed-cell-aliases.egg");

pub fn program(source: &str, congruence: bool) -> Program {
    let core = eggfuse_bake::device_frontend::core("closed-cell-aliases", source).unwrap();
    let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
    let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
    let id = |name| rules.iter().position(|r| r["metadata"]["name"] == name).unwrap();
    let (producer, consumer) = (id("producer"), id("consumer"));
    let output = rules[producer]["effects"].as_array().unwrap().iter()
        .position(|e| e["call"]["table"] == "Gateway").unwrap();
    // Both policies enter the same actual matching leaves. In particular, the
    // legacy union-policy control must exercise transfers instead of no work.
    let prefixes = vec![json!({"edge":[producer,output,consumer,0],"visits":2}),
        json!({"edge":[0,0,producer,0],"visits":2})];
    let profile = json!({"schema":"eggfuse-spine-shapes/v1", "program_sha256":p.artifact["sha256"],
        "prefixes":prefixes});
    let leaves = compiler::bake_stage_blocks(&p, &profile, &p, prefixes.len()).unwrap();
    let entries = leaves["entries"].as_array().unwrap();
    assert_eq!(entries.len(), prefixes.len());
    let right = entries.iter().position(|e| e["consumer"] == consumer).unwrap();
    let left = entries.iter().position(|e| e["consumer"] == producer).unwrap();
    let mut raw = p.artifact;
    raw["spine_blocks"] = leaves;
    let p = Program::parse(raw).unwrap();
    let mut plan = Catalog::seed(&p, Limits { support: 1, ..Default::default() }).unwrap();
    plan["joins"] = json!([{"left":left,"output":output,"right":right}]);
    if congruence { Catalog::emit_congruence_handoffs(&p, &mut plan).unwrap(); }
    else { Catalog::emit_handoffs(&p, &mut plan).unwrap(); }
    let mut raw = p.artifact;
    raw["iterative_bake"] = plan;
    Program::parse(raw).unwrap()
}
