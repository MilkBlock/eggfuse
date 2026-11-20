"""Optional exact source Run capture in the same frozen integrated engine."""
from pathlib import Path
def change(p,old,new):
    s=p.read_text()
    if s.count(old)!=1:raise ValueError((p,old[:50],s.count(old)))
    p.write_text(s.replace(old,new))
def install(crate):
    src=crate/'src'
    m=src/'ordinary_witness.rs'
    change(m,'if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}', '''if s.trial_attempts>=s.cap{s.counts.exhausted+=1;
        DEBUG_CAP.with_borrow_mut(|a|a.push([run,rid,s.trial_attempts,s.cap,c.pick_count]));
    }''')
    with m.open('a') as f:f.write("""
thread_local!{
    static DEBUG_CAP:std::cell::RefCell<Vec<[usize;5]>>=const{std::cell::RefCell::new(Vec::new())};
    static DEBUG_RUN:std::cell::Cell<usize>=const{std::cell::Cell::new(0)};
    static DEBUG_RHS:std::cell::RefCell<Vec<serde_json::Value>>=const{std::cell::RefCell::new(Vec::new())};
}
pub fn request_watch(run:usize){DEBUG_RUN.set(run);DEBUG_RHS.take();DEBUG_CAP.take();}
pub(crate) fn watch_rows<'a>(run:usize,rows:impl Iterator<Item=(&'a usize,&'a crate::cell::Instance)>){
    if run==DEBUG_RUN.get(){DEBUG_RHS.with_borrow_mut(|out|out.extend(rows.map(|(rid,b)|serde_json::json!([rid,b.values]))));}
}
pub fn watch_result()->serde_json::Value{serde_json::json!({"cap":DEBUG_CAP.take(),"rows":DEBUG_RHS.take()})}
""")
    p=src/'runtime.rs'
    change(p,'        crate::transfer_audit::record_run(patch.iter().map(|(rid, b)| (rid, &b.values)))?;', '''        crate::transfer_audit::record_run(patch.iter().map(|(rid, b)| (rid, &b.values)))?;
        crate::ordinary_witness::watch_rows(self.steps.len()+1,patch.iter());''')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let start = Instant::now();', '''        ordinary_witness::request_watch(req["watch_run"].as_u64().unwrap_or(0) as usize);
        let stop=req["stop_after"].as_u64().map(|v|v as usize);
        let start = Instant::now();''')
    change(p,'if let Err(error) = runtime.execute()', 'if let Err(error) = runtime.execute_until(stop)')
    change(p,'        report["root_recipe"]=', '        report["diagnostic"]=ordinary_witness::watch_result();\n        report["root_recipe"]=')
