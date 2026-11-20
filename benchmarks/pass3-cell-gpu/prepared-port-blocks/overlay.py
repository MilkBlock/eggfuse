from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def repl(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    s=repl(p.read_text(),'struct Store {','struct Store {prepared:PreparedPorts,')
    s=repl(s,'let s=Store{','let s=Store{prepared:PreparedPorts::default(),')
    s=repl(s,'"forward":s.forward.stats,','"prepared":s.prepared.stats,"forward":s.forward.stats,')
    s=repl(s,'            s.issued_generations.clear();','''            if s.prepared.mode!=0 && steps.len()>=3{s.prepare_columns(&mut steps);}
            s.issued_generations.clear();''')
    p.write_text(s+'\ninclude!("prepared_columns.rs");\n')
    p=src/'ordinary_shortlist.rs'
    s=repl(p.read_text(),'struct StackStep {','struct StackStep {compiled:Option<PreparedStep>,')
    s=repl(s,'descriptors.push(StackStep{atom:','descriptors.push(StackStep{compiled:None,atom:')
    s=repl(s,'            if self.signatures.enabled{','''            if let Some(idx)=d.compiled.as_ref().and_then(|p|p.index.as_ref()){
                self.prepared.stats.hoisted_probes+=1;
                Some(self.shortlist(&d.frame,idx,col,q))
            }else if self.signatures.enabled{''')
    s=repl(s,'            for &(col,slot) in &d.publish{ports[slot]=Some(self.code(&row.values[col]));self.memo_counts.emitted_port_codes+=1;}',
'''            if let Some(compiled)=d.compiled.as_ref().filter(|p|p.columns_ready){
                for (slot,keys) in &compiled.publish{
                    let code=keys[j];
                    ports[*slot]=Some(Port{query:code,key:code,certified:0,uncertain:0,extra:[[0;4];2]});
                }
                self.memo_counts.emitted_port_codes+=compiled.publish.len() as u64;
                self.prepared.stats.reused_values+=compiled.publish.len() as u64;
            }else{
                for &(col,slot) in &d.publish{ports[slot]=Some(self.code(&row.values[col]));self.memo_counts.emitted_port_codes+=1;}
            }''')
    s=repl(s,'let value=self.code(&row.values[col]);\n                    if !self.compatible',
'''let value=if let Some(compiled)=d.compiled.as_ref().filter(|p|p.columns_ready){
                        let code=compiled.extra[&col][j];
                        self.prepared.stats.reused_values+=1;
                        Port{query:code,key:code,certified:0,uncertain:0,extra:[[0;4];2]}
                    }else{self.code(&row.values[col])};
                    if !self.compatible''')
    p.write_text(s)
    shutil.copyfile(HERE/'columns.rs',src/'prepared_columns.rs')
    p=crate/'examples/joint_witness_session.rs';a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(repl(p.read_text(),a,'''        if let Some(config)=req.get("prepared"){ordinary_witness::configure_prepared(config.clone())?;}
'''+a))
