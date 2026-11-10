#![cfg(feature = "iterative-bake")]
use eggfuse_cell_runtime::{checksum::artifact_digest, compiler, executor::Executor,
    graph::Graph, iterative::{Catalog,Limits}, program::Program};
use serde_json::{Value,json};
#[path = "../examples/emit_cell_retention.rs"]
mod fixture;

fn seal(mut raw:Value) -> Value {
    raw.as_object_mut().unwrap().remove("sha256");
    raw["sha256"]=artifact_digest(&raw).into(); raw
}
#[test]
fn alternate_routes_share_the_native_cell_registry_but_keep_entry_proofs() {
    let source=r#"
(datatype E (N i64) (Start E) (Left E) (Right E) (End E E))
(ruleset a)
(rule ((= s (Start x))) ((Left x) (Right x)) :ruleset a :name "left-first")
(rule ((= anchor (Start input))) ((Right input) (Left input)) :ruleset a :name "right-first")
(rule ((= s (Start x)) (= l (Left x))) ((Right x)) :ruleset a :name "stronger-entry")
(Start (N 1))
(run-schedule (run a))
"#;
    let core=eggfuse_bake::device_frontend::core("ripsat",source).unwrap();
    let p=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let profile=json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":(0..3).map(|r|json!({"edge":[0,0,r,0],"visits":2})).collect::<Vec<_>>()});
    let blocks=compiler::bake_spine_blocks(&p,&profile,&p,3).unwrap();
    let mut raw=p.artifact; raw["spine_blocks"]=blocks;
    let p=Program::parse(seal(raw.clone())).unwrap();
    let mut plan=Catalog::seed(&p,Limits::default()).unwrap();
    Catalog::emit_query_handoffs(&p,&mut plan).unwrap();
    raw["iterative_bake"]=plan;
    let p=Program::parse(seal(raw)).unwrap();
    let result=eggfuse_cell_compiler::state_plan::completion(&p).unwrap();
    let implementations=result["contracts"]["implementations"].as_array().unwrap();
    let class=|r|implementations.iter().find(|i|i["source_path"][0][1][0]==r).unwrap()["class"].clone();
    assert_eq!(class(0),class(1));
    assert_ne!(class(0),class(2));
    assert_eq!(implementations.len(),3);
    assert_eq!(result["contracts"]["structures"].as_array().unwrap().len(),2);
    // The actual ripsat registry, not a CPU-only map, interns both derivations.
    assert_eq!(result["cell_egraph"]["registered_compositions"],3);
    assert_eq!(result["cell_egraph"]["eclasses"],2);
}

#[test]
fn failed_rhs_does_not_train_a_completed_transition() {
    let source=include_str!("fixtures/history-retention.egg")
        .replace("((Mid x))", "((Mid x) (panic \"not-completed\"))");
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(&source,&dir.path().join("case")).unwrap();
    let raw=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let p=Program::parse(raw).unwrap();
    let entries=p.iterative.entries();
    let bridge=p.templates.iter().position(|t|t.name=="bridge").unwrap();
    let bridge=p.rules.iter().position(|r|r.template==bridge).unwrap();
    let mut e=Executor::new(Graph::new(p).unwrap(),true);
    e.collect_iterative_pairs();
    assert!(e.execute().is_err());
    let history = e.iterative_training().completion_history(&e.graph.program);
    assert!(history["events"].as_array().unwrap().iter().all(|event| event["entry"][0] != bridge),
        "failed RHS must not enter the runtime trace");
    let report=e.report();
    assert!(report["stage_spine"]["stats"]["resumed_steps"].as_u64().unwrap()>0);
    let hits=report["stage_spine"]["iterative_bake"]["applied_units"].as_object().unwrap();
    for (unit,_) in hits {
        let entry=&entries[unit.parse::<usize>().unwrap()];
        assert_ne!(entry["expanded"].as_array().unwrap().last().unwrap()[1][0],bridge,
            "the bridge RHS failed and must not establish its completion: {hits:?}");
    }
}

#[cfg(feature = "sparse-cells")]
fn execute(raw:Value) -> (Executor,Value) {
    let p=Program::parse(raw).unwrap();
    let mut e=Executor::new(Graph::new_with_local_congruence(p).unwrap(),false);
    use eggfuse_cell_runtime::transfer_audit as audit;
    audit::take_digests(); audit::take_write_digests(); audit::take_resume_digests();
    audit::set_active(true); audit::enable_write_audit();
    let mut snapshots=vec![e.graph.export().unwrap()];
    loop {
        let previous=e.steps.len();
        e.execute_until(Some(previous+1)).unwrap();
        if e.steps.len()==previous {break;}
        snapshots.push(e.graph.export().unwrap());
    }
    audit::set_active(false);
    let evidence=json!({"states":snapshots,"inputs":audit::take_digests(),
        "writes":audit::take_write_digests(),"resumes":audit::take_resume_digests()});
    (e,evidence)
}

#[test]
#[cfg(feature = "sparse-cells")]
fn direct_completion_projects_real_results_and_preserves_every_run() {
    let base=include_str!("fixtures/history-retention.egg")
        .replace("(rule ((= x (N 2))) ((delete (Right x))) :ruleset retire)","")
        .replace("(Mid E)","(Mid E) (Seen E)")
        .replace("(N 1) (N 2)","(N 1) (N 2)\n(ruleset observe)\n(rule ((Left x)) ((Seen x)) :ruleset observe)\n(rule ((Right x)) ((Seen x)) :ruleset observe)")
        .replace("(run c)","(run c) (run observe)");
    for (case,source) in [base.clone(),base.replace("(N 1) (N 2)","(Left (N 1)) (Right (N 2))"),
        base.replace("(N 1) (N 2)","(N 1) (N 2)\n(rule ((= first (N 1)) (= second (N 2))) ((union first second)) :ruleset retire)"),
        base.replace("((Left x) (Right x) (Gateway x))","((Left x) (Right x) (Mid x) (Gateway x))")
            .replace("((Mid x))","((Right x) (Left x) (Mid x))"),
        base.replace("((Left x) (Right x) (Gateway x))","((Left x) (Right x) (Gateway x) (union (Left x) (Mid x)))")
            .replace("(rule ((= m (Mid x))) ((Left x) (Right x)) :ruleset c :name \"consume\")",
                "(rewrite (Mid x) (Left x) :ruleset c :name \"consume\")"),
    ].into_iter().enumerate() {
        let dir=tempfile::tempdir().unwrap();
        fixture::emit(&source,&dir.path().join("case")).unwrap();
        let raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
        let compiled=eggfuse_cell_compiler::completion_bake::compile(Program::parse(raw.clone()).unwrap()).unwrap();
        check_entry_dispatch(&compiled);
        let (before,expected)=execute(raw); let (after,actual)=execute(compiled.clone());
        assert_eq!(expected,actual,"exact boundaries and ordered inputs/effects on the actual optimized path");
        assert_eq!(before.graph.export().unwrap(),after.graph.export().unwrap());
        assert_eq!(before.snapshots,after.snapshots);
        assert_eq!(before.binding_audit,after.binding_audit);
        for (a,b) in before.steps.iter().zip(&after.steps) {
            for key in ["ordinal","ruleset","path","iterations","epoch","logical_matches","executed_bindings","changed"] {assert_eq!(a[key],b[key],"{key}");}
        }
        let a=before.report(); let b=after.report();
        let stats=&b["stage_spine"]["stats"];
        assert!(stats["ripsat_completed"].as_u64().unwrap()>0,"case {case}; completion programs: {}; {stats}",compiled["iterative_bake"]["rhs_handoffs"]["completion_states"]);
        if case==3 {
            assert_eq!(stats["ripsat_completed"],4);
            assert!(stats["ripsat_projection_checks"].as_u64().unwrap()>0);
        }
        assert!(a["stats"]["handoff_attempts"].as_u64().unwrap()>b["stats"]["handoff_attempts"].as_u64().unwrap());
        assert!(a["stage_spine"]["stats"]["effect_slots_initialized"].as_u64().unwrap()>stats["effect_slots_initialized"].as_u64().unwrap());
        let mut corrupt=compiled.clone();
        let state=corrupt["iterative_bake"]["rhs_handoffs"]["completion_states"].as_array_mut().unwrap()
            .iter_mut().find(|s|!s.is_null()).unwrap();
        state["sources"][0][1]=json!(99999);
        assert!(Program::parse(seal(corrupt)).is_err());
        let mut corrupt=compiled;
        corrupt["iterative_bake"]["completion"]["contracts"]["structures"]=json!([]);
        assert!(Program::parse(seal(corrupt)).is_err());
    }
}

fn check_entry_dispatch(raw: &Value) {
    let plan = &raw["iterative_bake"];
    let dispatch = &plan["completion"]["entry_dispatch"];
    let switch = &plan["rhs_handoffs"];
    assert_eq!(dispatch["switch_sha256"], artifact_digest(switch));
    let programs = switch["completion_states"].as_array().unwrap();
    let mut routed = std::collections::BTreeSet::new();
    for entry in dispatch["entries"].as_array().unwrap() {
        assert!(!entry["states"].as_array().unwrap().is_empty());
        for pc in entry["states"].as_array().unwrap() {
            let pc = pc.as_u64().unwrap() as usize;
            assert!(routed.insert(pc), "one execution entry per program");
            assert!(!programs[pc].is_null());
            assert_eq!(entry["rule"], programs[pc]["rule"]);
        }
    }
    // Includes all suffix/fallback destinations, not just learned join edges.
    for (pc, program) in programs.iter().enumerate() {
        assert_eq!(routed.contains(&pc), !program.is_null());
    }
    assert_eq!(dispatch["programs"], routed.len());
    // Existing v1 artifacts remain valid without the optional dispatch export.
    let mut old = raw.clone();
    old["iterative_bake"]["completion"].as_object_mut().unwrap().remove("entry_dispatch");
    old["iterative_bake"]["completion"]["contracts"].as_object_mut().unwrap().remove("transitions");
    Program::parse(seal(old)).unwrap();
    let mut corrupt_transition = raw.clone();
    corrupt_transition["iterative_bake"]["completion"]["contracts"]["transitions"] = json!([{"from":99999}]);
    assert!(Program::parse(seal(corrupt_transition)).is_err());
    for field in ["entries", "switch_sha256", "dynamic_checks", "default"] {
        let mut forged = raw.clone();
        forged["iterative_bake"]["completion"]["entry_dispatch"][field] = Value::Null;
        assert!(Program::parse(seal(forged)).is_err(), "unchecked {field}");
    }
    if !routed.is_empty() {
        let mut forged = raw.clone();
        forged["iterative_bake"]["completion"]["entry_dispatch"]["entries"][0]["states"][0] = json!(0);
        assert!(Program::parse(seal(forged)).is_err());
    }
}

#[test]
#[cfg(feature = "sparse-cells")]
fn deletable_results_keep_the_original_rhs_responsibility() {
    let dir=tempfile::tempdir().unwrap();
    fixture::emit(include_str!("fixtures/history-retention.egg"),&dir.path().join("case")).unwrap();
    let raw:Value=serde_json::from_slice(&std::fs::read(dir.path().join("case/program.json")).unwrap()).unwrap();
    let compiled=eggfuse_cell_compiler::completion_bake::compile(Program::parse(raw.clone()).unwrap()).unwrap();
    check_entry_dispatch(&compiled);
    let (before,expected)=execute(raw); let (after,actual)=execute(compiled);
    assert_eq!(expected,actual);
    assert_eq!(before.graph.export().unwrap(),after.graph.export().unwrap());
    assert_eq!(before.snapshots,after.snapshots);
    assert_eq!(before.binding_audit,after.binding_audit);
    assert_eq!(after.report()["stage_spine"]["stats"]["ripsat_completed"],0);
}

#[test]
#[cfg(feature = "sparse-cells")]
fn a_second_derivation_inherits_an_existing_completion_at_its_own_output_position() {
    let source=r#"
(datatype E (N i64) (Start E) (Left E) (Right E) (Gateway E) (Seen E))
(ruleset first) (ruleset second) (ruleset consume) (ruleset observe)
(rule ((Start x)) ((Left x) (Right x) (Gateway x)) :ruleset first :name "first")
(rule ((Start renamed)) ((Gateway renamed) (Right renamed) (Left renamed)) :ruleset second :name "second")
(rule ((Gateway x)) ((Left x) (Right x)) :ruleset consume :name "consumer")
(rule ((Left x)) ((Seen x)) :ruleset observe)
(rule ((Right x)) ((Seen x)) :ruleset observe)
(Start (N 1))
(run-schedule (seq (run second) (run consume) (run observe) (run first)))
"#;
    for local in [false, true] {
        let core=eggfuse_bake::device_frontend::core("alternative",source).unwrap();
        let p=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
        let rules=p.artifact["recipe"]["rules"].as_array().unwrap();
        let rule=|name|rules.iter().position(|r|r["metadata"]["name"]==name).unwrap();
        let (a,b,c)=(rule("first"),rule("second"),rule("consumer"));
        let gateway=|rid:usize|rules[rid]["effects"].as_array().unwrap().iter()
            .position(|e|e["call"]["table"]=="Gateway").unwrap();
        let (source_output,other_output)=(gateway(a),gateway(b));
        assert_ne!(source_output,other_output);
        let profile=json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
            "prefixes":([a,b,c].map(|r|json!({"edge":[0,0,r,0],"visits":2})))});
        let blocks=compiler::bake_spine_blocks(&p,&profile,&p,3).unwrap();
        let entries=blocks["entries"].as_array().unwrap();
        let entry=|r|entries.iter().position(|e|e["consumer"]==r).unwrap();
        let (first,second,consumer)=(entry(a),entry(b),entry(c));
        let mut raw=p.artifact;raw["spine_blocks"]=blocks;
        let p=Program::parse(seal(raw.clone())).unwrap();
        let mut plan=Catalog::seed(&p,Limits::default()).unwrap();
        plan["joins"]=json!([{"left":first,"output":source_output,"right":consumer}]);
        Catalog::emit_query_handoffs(&p,&mut plan).unwrap();
        raw["iterative_bake"]=plan;
        let raw=seal(raw);
        let checked = Program::parse(raw.clone()).unwrap();
        let mut unseen = raw["iterative_bake"].clone();
        Catalog::emit_observed_ripsat_handoffs(&checked, &mut unseen, &Default::default()).unwrap();
        assert_eq!(unseen["joins"], raw["iterative_bake"]["joins"], "unobserved catalog implementations must not seed inferred routes");
        let observed = eggfuse_cell_runtime::iterative::ObservedCompletions {
            units: [first,second,consumer].into_iter().collect(), joins:Default::default(),
        };
        Catalog::emit_observed_ripsat_handoffs(&checked, &mut unseen, &observed).unwrap();
        assert_eq!(unseen["joins"], raw["iterative_bake"]["joins"], "seeing both endpoints is not observing their transition");
        assert_eq!(unseen["completion_search"]["indexed_outputs"],0,"no trace edge means no recognition index to build");
        // Measured Bake must not insert the inferred route while constructing its
        // baseline. Even without observed proposals it must score that route.
        let tmp = tempfile::tempdir().unwrap();
        let seed = tmp.path().join("seed.json");
        let catalog = tmp.path().join("catalog.json");
        std::fs::write(&seed, serde_json::to_vec(&raw).unwrap()).unwrap();
        std::fs::write(&catalog, serde_json::to_vec(&raw["iterative_bake"]).unwrap()).unwrap();
        for (rounds, support) in [(0, "1000000"), (1, "1000000"), (1, "1")] {
            let out = tmp.path().join(format!("rounds-{rounds}-{support}"));
            let result = std::process::Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
                .args(["iterate", "--program"]).arg(&seed)
                .arg("--resume-catalog").arg(&catalog).arg("--output").arg(&out)
                .args(["--objective", "ripsat-completion", "--score", "measured-work",
                    "--local-congruence", if local { "true" } else { "false" }, "--min-support", support, "--rounds", &rounds.to_string()])
                .output().unwrap();
            assert!(result.status.success(), "{}", String::from_utf8_lossy(&result.stderr));
            let history: Value = serde_json::from_slice(&std::fs::read(out.join("rounds.json")).unwrap()).unwrap();
            assert_eq!(history[0]["units"], 4, "unscored inferred route entered baseline");
            let trace: Value = serde_json::from_slice(&std::fs::read(out.join("round-0/cell-history.json")).unwrap()).unwrap();
            let graph: Value = serde_json::from_slice(&std::fs::read(out.join("round-0/cell-egraph.json")).unwrap()).unwrap();
            assert_eq!(graph["origin"]["kind"], "completed-cell-runtime-history");
            assert_eq!(trace["program_sha256"], history[0]["source_program"]);
            let events = trace["events"].as_array().unwrap();
            assert!(!events.is_empty());
            assert!(events.iter().any(|e| e["parent"].is_u64() && e["run"] != e["producer_run"]));
            assert_eq!(graph["registered_compositions"], trace["contracts"]["implementations"].as_array().unwrap().len());
            let samples = trace["sampled_applications"].as_array().unwrap();
            assert!(!samples.is_empty());
            for sample in samples {
                assert_eq!(sample["sample_policy"], "latest-retained-application");
                assert!(sample["consumer_run"].as_u64().unwrap() > sample["producer_run"].as_u64().unwrap());
                assert!(sample["retained_support"].as_u64().unwrap() > 0);
                assert!(sample.get("parent").is_none(), "aggregate evidence is not an event chain");
            }
            for (id, event) in events.iter().enumerate() {
                if let Some(parent) = event["parent"].as_u64() {
                    assert!((parent as usize) < id);
                    assert_eq!(events[parent as usize]["run"], event["producer_run"]);
                }
            }
            if rounds == 1 {
                let trials = history[0]["credit"]["trials"].as_array().unwrap();
                assert_eq!(history[0]["credit"]["duplicate_executable_proposals"], if support == "1" { 1 } else { 0 });
                assert_eq!(trials.len(), 1);
                if support != "1" { assert_eq!(trials[0]["proposal"]["kind"], "equivalent-routes"); }
                let score = trials[0]["work"]["net_saved_operations"].as_i64().unwrap();
                eprintln!("equivalent-route local={local}, credit={score}");
                assert_eq!(score > 0, local, "fixture must cover both admission and rejection");
                if let Some(hash) = history[0]["credit"].get("selected_program_sha256") {
                    assert_eq!(*hash, trials[0]["program_sha256"]);
                    assert_eq!(history[1]["source_program"], *hash, "next round must use exact scored artifact");
                    let final_program: Value = serde_json::from_slice(&std::fs::read(out.join("program.json")).unwrap()).unwrap();
                    assert_eq!(final_program["sha256"], *hash);
                    if support != "1" {
                        let inferred = final_program["iterative_bake"]["completion_extensions"].as_array().unwrap();
                        assert!(inferred.iter().any(|route| route["from"]["left"]==second
                            && route["to"]["left"]==second && route["observed_application"]==true
                            && route["origin"]=="completed-runtime-history"),
                            "recognition must start at the executed route, not the unused catalog join");
                    }
                } else {
                    assert_eq!(history[0]["stop"], "no_measured_gain");
                    assert_eq!(history.as_array().unwrap().len(), 1);
                }
            }
        }
        let compiled=eggfuse_cell_compiler::completion_bake::compile(Program::parse(raw.clone()).unwrap()).unwrap();
        check_entry_dispatch(&compiled);
        let search = &compiled["iterative_bake"]["completion_search"];
        assert_eq!(search["route_probes"], 1);
        assert_eq!(search["candidate_visits"], 2, "only the two equivalent output sources are visited");
        assert_eq!(search["proof_checks"], 1);
        assert_eq!(search["admitted"], 1);
        let additions=compiled["iterative_bake"]["completion_extensions"].as_array().unwrap();
        assert!(additions.iter().any(|e|e["to"]==json!({"left":second,"output":other_output,"right":consumer})),"{additions:?}");
        let edges=&compiled["iterative_bake"]["completion"]["cell_egraph"]["completion_transitions"];
        assert_eq!(edges["source_edges"],2);
        assert_eq!(edges["shared_edges"],1,"equal completion transitions share the actual native relation: {edges}");
        let (_,expected)=execute(raw);
        let (after,actual)=execute(compiled);
        assert_eq!(expected,actual);
        assert!(after.report()["stage_spine"]["stats"]["ripsat_completed"].as_u64().unwrap()>0,
            "the second producer's untrained route must execute the derived completion");
    }
}

#[test]
fn separate_pair_instances_do_not_train_a_three_cell_bridge() {
    for connected in [false, true] {
        let source = format!(r#"
(datatype E (N i64) (Start E) (Left E) (Right E) (Gateway E) (Mid E))
(ruleset init) (ruleset a) (ruleset b) (ruleset c)
(rule ((= x (N 1))) ((Start x)) :ruleset init)
(rule ((= x (N 2))) ((Gateway x)) :ruleset init)
(rule ((Start x)) ((Left x) (Right x) (Gateway x)) :ruleset a :name "a")
(rule ((Gateway x)) ((Mid x)) :ruleset b :name "b")
(rule ((Mid x) (= x (N {}))) ((Left x) (Right x)) :ruleset c :name "c")
(N 1) (N 2)
(run-schedule (seq (run init) (run a) (run b) (run c)))
"#, if connected {1} else {2});
        let core = eggfuse_bake::device_frontend::core("bridge-ancestry", &source).unwrap();
        let p = Program::parse(compiler::compile(core, &Default::default()).unwrap()).unwrap();
        let rules = p.artifact["recipe"]["rules"].as_array().unwrap();
        let ids = ["a","b","c"].map(|name| rules.iter().position(|r| r["metadata"]["name"] == name).unwrap());
        let profile = json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
            "prefixes":ids.map(|r|json!({"edge":[0,0,r,0],"visits":2}))});
        let blocks = compiler::bake_spine_blocks(&p,&profile,&p,3).unwrap();
        assert_eq!(blocks["entries"].as_array().unwrap().len(),3);
        let mut raw = p.artifact; raw["spine_blocks"] = blocks;
        let tmp = tempfile::tempdir().unwrap();
        let seed = tmp.path().join("seed.json");
        let out = tmp.path().join("learned");
        std::fs::write(&seed,serde_json::to_vec(&seal(raw)).unwrap()).unwrap();
        let result = std::process::Command::new(env!("CARGO_BIN_EXE_eggfuse-cell-compiler"))
            .args(["iterate","--program"]).arg(&seed).arg("--output").arg(&out)
            .args(["--rounds","1","--objective","rhs-lookups","--score","static","--min-support","1"])
            .output().unwrap();
        assert!(result.status.success(),"{}",String::from_utf8_lossy(&result.stderr));
        let rounds: Value = serde_json::from_slice(&std::fs::read(out.join("rounds.json")).unwrap()).unwrap();
        assert!(rounds[0]["work"]["candidate_shapes"].as_u64().unwrap() >= 2,
            "both pair shapes must actually execute: {rounds}");
        let bridges = rounds[0]["admitted"].as_array().unwrap().iter()
            .filter(|e|e[1]["bridge_support"].as_u64().unwrap()>0).count();
        assert_eq!(bridges,usize::from(connected),"{rounds}");
    }
}

#[test]
fn already_proven_union_does_not_hide_constructor_structure() {
    let source = r#"
(datatype E (N i64) (Start E) (F E) (G E))
(ruleset a)
(rule ((Start x)) ((F x)) :ruleset a :name "plain")
(rule ((Start x)) ((let lhs (F x)) (let rhs (F x)) (union lhs rhs)) :ruleset a :name "inert")
(rule ((Start x)) ((let lhs (F x)) (let rhs (G x)) (union lhs rhs)) :ruleset a :name "real")
(rule ((Start x)) ((let lhs (F x)) (let rhs (G x)) (union lhs rhs) (F lhs)) :ruleset a :name "after")
(rule ((Start x)) ((let lhs (F x)) (let rhs (G x)) (F lhs) (union lhs rhs)) :ruleset a :name "before")
(Start (N 1))
(run-schedule (run a))
"#;
    let core=eggfuse_bake::device_frontend::core("inert-union",source).unwrap();
    let p=Program::parse(compiler::compile(core,&Default::default()).unwrap()).unwrap();
    let rules=p.artifact["recipe"]["rules"].as_array().unwrap();
    let ids=["plain","inert","real","after","before"].map(|name|rules.iter().position(|r|r["metadata"]["name"]==name).unwrap());
    let profile=json!({"schema":"eggfuse-spine-shapes/v1","program_sha256":p.artifact["sha256"],
        "prefixes":ids.map(|r|json!({"edge":[0,0,r,0],"visits":1}))});
    let blocks=compiler::bake_spine_blocks(&p,&profile,&p,5).unwrap();
    let mut raw=p.artifact; raw["spine_blocks"]=blocks;
    let p=Program::parse(seal(raw)).unwrap();
    let plan=Catalog::seed(&p,Limits::default()).unwrap();
    assert!(p.templates[p.rules[ids[1]].template].ops.iter().any(|op|matches!(op,eggfuse_cell_runtime::program::Op::Union(..))));
    let mut raw=p.artifact; raw["iterative_bake"]=plan;
    let p=Program::parse(seal(raw)).unwrap();
    let contracts=p.iterative.completion_contracts(&p);
    let implementations=contracts["implementations"].as_array().unwrap();
    let entry=|rid|implementations.iter().find(|i|i["source_path"][0][1][0]==rid).unwrap();
    assert!(entry(ids[0]).get("normalization").is_none());
    assert_eq!(entry(ids[0])["class"],entry(ids[1])["class"]);
    assert!(entry(ids[2]).get("normalization").is_none());
    assert_ne!(entry(ids[0])["class"],entry(ids[2])["class"]);
    let shape=&contracts["structures"][entry(ids[2])["class"].as_u64().unwrap() as usize];
    assert_eq!(shape["terminal_unions"].as_array().unwrap().len(),1);
    assert!(entry(ids[3]).get("normalization").is_none());
    assert_ne!(entry(ids[2])["class"],entry(ids[3])["class"]);
    assert_eq!(entry(ids[3])["class"],entry(ids[4])["class"],
        "queued Union must not change same-RHS constructor congruence");
    let compiled=eggfuse_cell_compiler::completion_bake::compile(p.clone()).unwrap();
    let (before,expected)=execute(p.artifact);
    let (after,actual)=execute(compiled);
    assert_eq!(expected,actual);
    assert_eq!(before.graph.export().unwrap(),after.graph.export().unwrap());
    assert_eq!(before.snapshots,after.snapshots);
}
