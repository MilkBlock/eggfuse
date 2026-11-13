//! Learn from actual executions of an installed catalog; preserve its transitions.
use super::*;
use eggfuse_cell_runtime::graph::cell_ownership::composition::Fragment;

pub(super) fn run(root:&Path,seed:&str,variant:&str)->Result<()> {
    if seed==variant {return Err("learning output must differ from seed catalog".into());}
    let mut summaries=Vec::new();
    for name in ["fact","loopfact","sum-bits","dot-product"] {
        let dir=root.join(name);
        let original=read(dir.join("candidate.json"))?;
        let mut raw=read(root.join(seed).join(name).join("candidate.json"))?;
        if original["recipe"]!=raw["recipe"] || source_digest(&original)!=source_digest(&raw) {
            return Err("result learning requires unchanged source Cell definitions".into());
        }
        let observed=read(dir.join("catalog-observation.json"))?;
        let terminal=read(dir.join("terminal-check.json"))?;
        if observed["source_program"]!=original["sha256"] || observed["all_saved_run_checks_equal"]!=true
            || terminal["source_program"]!=original["sha256"] {return Err("unaudited source checks".into());}
        let checks=observed["run_checks"].as_array().ok_or("missing Run checks")?;
        let seed_sha=raw["sha256"].clone();
        let mut e=executor(raw.clone())?;
        let bound=e.graph.program.cell_ownership.composition.max_frames;
        e.graph.continue_ownership_fragment_training(bound)?;
        for (i,expected) in checks.iter().enumerate() {
            if step(&mut e,i+1)?!=*expected {return Err(format!("{name}: learning differs at Run {}",i+1).into());}
        }
        if step(&mut e,checks.len()+1)?!=terminal["check"] || e.steps.len()!=checks.len() {
            return Err(format!("{name}: terminal learning mismatch").into());
        }
        let full_profile=e.graph.ownership_fragment_profile()?;
        let mut profile=full_profile.clone();
        let has_result=|f:&Value|->Result<bool> {
            let fragment:Fragment=serde_json::from_value(f.clone())?;
            Ok(fragment.hops.iter().any(|h|h.entry>=e.graph.program.cell_ownership.entries[h.rule].len()))
        };
        let mut records=Vec::new();
        for row in full_profile["records"].as_array().ok_or("missing learned records")? {
            if has_result(&row["fragment"])? {records.push(row.clone());}
        }
        profile["records"]=records.into();
        let selected=select_profile_with_budget(&profile,1024,65536)?;
        let mut added=0;
        let fragments=raw["ownership_fragments"]["fragments"].as_array_mut().ok_or("missing seed fragments")?;
        let seed_count=fragments.len();
        for fragment in selected["fragments"].as_array().ok_or("missing result selection")? {
            if !fragments.contains(fragment) {fragments.push(fragment.clone());added+=1;}
        }
        raw["ownership_fragments"]["max_fragments"]=json!(4096);
        raw["ownership_fragments"]["ranking"]=json!({"seed_fragments":seed_count,"added_result_fragments":added,
            "additional_selection":selected["ranking"],"performance_admission":"unvalidated; compare actual production work and storage"});
        raw.as_object_mut().unwrap().remove("ownership_markers");
        raw.as_object_mut().unwrap().remove("sha256");raw["sha256"]=artifact_digest(&raw).into();
        let mut checked=Program::parse(raw.clone())?;checked.prepare_cell_ownership()?;
        let previous=&e.graph.program.cell_ownership.composition;
        for (key,target) in &previous.transitions {
            if checked.cell_ownership.composition.transition(key)!=Some(*target) {
                return Err("result catalog changed a seed transition".into());
            }
        }
        let output=root.join(variant).join(name);fs::create_dir_all(&output)?;
        write(output.join("candidate.json"),&raw)?;
        write(output.join("selection.json"),&json!({"source_program":original["sha256"],
            "seed_program":seed_sha,"selection":raw["ownership_fragments"]}))?;
        write(output.join("profile.json"),&profile)?;
        let summary=json!({"case":name,"seed_program":seed_sha,"program":raw["sha256"],"runs":checks.len(),
            "all_saved_run_checks_equal":true,"terminal_check_equal":true,"seed_transitions_preserved":true,
            "learned_result_records":profile["records"].as_array().unwrap().len(),"seed_fragments":seed_count,
            "added_result_fragments":added,"training_ownership":e.graph.ownership_report(),
            "scope":"actual exploratory learning; training counts are not production savings"});
        write(output.join("learning.json"),&summary)?;summaries.push(summary);
        eprintln!("learned {name}: {} Runs, {added} additional result fragments",checks.len());
    }
    write(root.join(variant).join("learning.json"),&json!({"cases":summaries}))
}
