from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'slots.rs';s=p.read_text()
    marker='    pub fn values(&self) -> impl Iterator<Item = &V> {'
    p.write_text(change(s,marker,'''    pub(crate) fn ordered_fields(&self)->&[(K,V)]{&self.0}
'''+marker))
    p=src/'runtime.rs';s=p.read_text()
    s=change(s,'    dedup_rows: u64,','    order_policy: BindingOrder,\n    dedup_rows: u64,')
    s=change(s,'            dedup_rows: 0,','            order_policy: BindingOrder::default(),\n            dedup_rows: 0,')
    marker='    fn dedup_bindings(&mut self, rid: usize, mut found: Vec<Binding>) -> Result<Vec<Binding>> {'
    s=change(s,marker,'''    fn dedup_bindings(&mut self,rid:usize,found:Vec<Binding>)->Result<Vec<Binding>>{
        let start=self.order_policy.clock.then(Instant::now);
        let answer=self.order_source_bindings(rid,found);
        if let Some(start)=start{self.order_policy.stats.time_ns+=start.elapsed().as_nanos() as u64;}
        answer
    }
    fn order_source_bindings(&mut self, rid: usize, mut found: Vec<Binding>) -> Result<Vec<Binding>> {''')
    marker='        self.dedup_elements += n * key_slots.len() as u64;'
    s=change(s,marker,marker+'''
        if self.order_policy.mode>0 && self.order_policy.sort(rid,key_slots,&mut found){
            self.dedup_duplicates+=n-found.len() as u64;
            return Ok(found)
        }''')
    p.write_text(s+'\ninclude!("binding_order.rs");\n');shutil.copyfile(HERE/'order.rs',src/'binding_order.rs')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();marker='        let initial_cells = runtime.graph.stats.cells_created;'
    s=change(s,marker,'''        if let Some(v)=req.get("binding_order"){runtime.configure_binding_order(v)?;}
'''+marker)
    marker='        report["pre_post_ms"]=';p.write_text(change(s,marker,'''        report["binding_order"]=runtime.binding_order_report();
'''+marker))
