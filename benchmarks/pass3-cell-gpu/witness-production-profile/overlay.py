"""Keep typed winner validation live while making historical proof JSON opt-in."""
from pathlib import Path


def replace(path, before, after):
    source = path.read_text()
    if source.count(before) != 1:
        raise ValueError(f'unsupported {path.name}: {before[:70]}')
    path.write_text(source.replace(before, after))


def install(crate):
    crate = Path(crate)
    src = crate / 'src'
    s = src / 'single_witness.rs'
    replace(s, 'pub(crate) struct Trial{', 'pub(crate) struct Trial{\n    pub(crate) archive_winners:bool,')
    replace(s, 'initial,residual,unsupported:residual,mode,', 'initial,residual,archive_winners:true,unsupported:residual,mode,')
    # receipt identity, graph/epoch consistency and RHS slot checks still run when archiving is off.
    replace(s, 'let witnesses=(0..r.query.len()).filter_map(|i|binding.known.receipt(i).map(|w|(i,address(w)))).collect();',
            'let witnesses=if self.archive_winners{(0..r.query.len()).filter_map(|i|binding.known.receipt(i).map(|w|(i,address(w)))).collect()}else{Vec::new()};')
    replace(s, 'initial:w.is_some_and(|w|self.initial.contains(&w)),score:s', 'initial:self.archive_winners && w.is_some_and(|w|self.initial.contains(&w)),score:s')
    replace(s, 'self.committed.push(json!([self.ordinal', 'if self.archive_winners{self.committed.push(json!([self.ordinal')
    replace(s, 't.id,mark.witnesses]));', 't.id,mark.witnesses]));}')
    # The original three generation clocks end before the single-parent verifier starts.
    # Two reads per rule occurrence charge its whole exact verification/attaching loop.
    if 'self.rows.verify.begin(' in s.read_text():
        replace(s,'        self.rows.verify.begin(g,r,&p,rid);',
                '        let verification_start=self.rows.profile.then(std::time::Instant::now);\n        self.rows.verify.begin(g,r,&p,rid);')
        replace(s,'        if self.mode=="capture"&&n>0', '        if let Some(t)=verification_start {self.rows.phase[3]+=t.elapsed().as_nanos() as u64;}\n        if self.mode=="capture"&&n>0')
    runtime=src/'runtime.rs'
    replace(runtime, '    pub fn single_report(&self)', '''    pub fn set_single_winner_archive(&mut self, enabled:bool){
        if let Some(s)=self.stage_spine.single.as_mut(){s.archive_winners=enabled;}
    }
    pub fn single_report(&self)''')
    driver = crate / 'examples/joint_witness_session.rs'
    replace(driver, '        let mut runtime = Executor::new', '        let ingest_start=Instant::now();\n        let mut runtime = Executor::new')
    replace(driver, '        if baseline {', '        let initial_graph_ms=ingest_start.elapsed().as_secs_f64()*1000.;\n        let setup_start=Instant::now();\n        if baseline {')
    replace(driver, '        let start = Instant::now();','        let setup_ms=setup_start.elapsed().as_secs_f64()*1000.;\n        let start = Instant::now();')
    replace(driver, '        let mut state = vec![];', '        let export_start=Instant::now();\n        let mut state = vec![];')
    replace(driver, '        let mut report = json!', '        let export_ms=export_start.elapsed().as_secs_f64()*1000.;\n        let mut report = json!')
    replace(driver, '        let initial_cells =', '''        runtime.set_single_winner_archive(audit || req["archive_single_winners"].as_bool().unwrap_or(false));
        let initial_cells =''')
    replace(driver, '        report["root_recipe"]=', '''        report["pre_post_ms"]=json!([initial_graph_ms,setup_ms,export_ms]);
        report["phases_ms"]=json!(runtime.steps.iter().fold([0.;5],|mut phases,step|{
            phases[0]+=1000.*step.phases.search;
            phases[1]+=1000.*step.phases.rhs;
            phases[2]+=1000.*step.phases.repair;
            phases[3]+=1000.*step.phases.query_update;
            phases[4]+=1000.*step.phases.delivery_gc;
            phases
        }));
        report["root_recipe"]=''')
