from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def replace(text,old,new):
    if text.count(old)!=1:raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    path=src/'ordinary_witness.rs'
    s=replace(path.read_text(),'struct Store {','struct Store {route_gate:RouteGate,')
    s=replace(s,'let s=Store{','let s=Store{route_gate:RouteGate::default(),')
    s=replace(s,'"wake":s.wake.stats,','"route_gate":s.route_gate.report,"wake":s.wake.stats,')
    s=replace(s,'        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}',
              '        s.route_gate.finish();\n        if s.trial_attempts>=s.cap{s.counts.exhausted+=1;}')
    path.write_text(s+'\ninclude!("request_route_gate.rs");\n')
    copyfile(HERE/'gate.rs',src/'request_route_gate.rs')
    path=src/'connected_requests.rs'
    anchor='        let index = self.index(target.table, join_col, &target.frame);'
    path.write_text(replace(path.read_text(),anchor,'''        if self.route_gate.mode!=0 && !self.route_gate.choose(self.run,self.rule,c,src,point,target){
            return Ok(false)
        }
'''+anchor))
    path=crate/'examples/joint_witness_session.rs'
    anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    path.write_text(replace(path.read_text(),anchor,'''        if let Some(v)=req.get("request_route_gate"){
            let mut policy=v.clone();
            if audit {policy["capture"]=Value::Bool(true);}
            ordinary_witness::configure_route_gate(&policy)?;
        }
'''+anchor))
