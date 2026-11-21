from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def install(crate):
    src=crate/'src'
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=rep(s,'struct Store {','struct Store {windows:WindowSurvey,')
    s=rep(s,'let s=Store{','let s=Store{windows:Default::default(),')
    s=rep(s,'json!({"pair_actor":','json!({"windows":s.windows.report(),"pair_actor":')
    # Some overlays insert fields before "wave", retaining the wave-report anchor.
    p.write_text(s+'\ninclude!("window_survey.rs");\n')
    p=src/'ordinary_shortlist.rs';s=p.read_text()
    a='        for pos in 0..len{'
    i=s.index('    fn emit_stack('); s0=s[:i];tail=s[i:]
    tail=rep(tail,a,'''        // Register an entire public root window before visiting any of its descendants.
        let survey=i==0 && steps.len()>=3 && self.windows.width>0 && self.wave.preparing;
        if survey && list.is_some(){return Err("root had an unexpected parent posting".into());}
        for pos in 0..len{
            if survey && pos%self.windows.width==0{
                self.windows.finish(self.counts.raw_tuples);
                self.windows.start(c,self.rule,steps,pos,len,self.counts.raw_tuples);
            }''')
    needle='        Ok(())\n    }\n}\n\nimpl Store {\n    fn verify_flat'
    tail=rep(tail,needle,'        if survey {self.windows.finish(self.counts.raw_tuples);}\n'+needle)
    p.write_text(s0+tail)
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(rep(s,a,'        if let Some(n)=req["prefix_window_survey"].as_u64(){ordinary_witness::window_survey(n)?;}\n'+a))
    copyfile(HERE/'survey.rs', src/'window_survey.rs')
