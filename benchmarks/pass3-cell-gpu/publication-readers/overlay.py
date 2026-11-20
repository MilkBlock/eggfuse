from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent

def change(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise RuntimeError((p.name,a,s.count(a)))
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';p=src/'runtime.rs'
    change(p,'    readers: Vec<Vec<usize>>,','    readers: Vec<Vec<usize>>,\n    notification_readers:Option<ReaderPlan>,')
    change(p,'            readers,','            readers,notification_readers:None,')
    change(p,'    fn deliver(&mut self) {','    fn deliver(&mut self) {\n        if self.notification_readers.is_some(){return self.deliver_with_plan();}')
    change(p,'        if !probe && self.stage_spine.single.as_ref().is_some_and(|s|!s.unsupported)',
        '        if !probe && self.notification_readers.as_ref().is_some_and(|p|p.mode!=0 && p.dedicated[rid]){return Err("complete provider fell through to a retired native search reader".into());}\n        if !probe && self.stage_spine.single.as_ref().is_some_and(|s|!s.unsupported)')
    shutil.copyfile(HERE/'readers.rs',src/'strict_publication_readers.rs')
    with p.open('a') as f:f.write('\ninclude!("strict_publication_readers.rs");\n')
    p=src/'stage_spine.rs'
    change(p,'    pub(crate) fn active_for_rule(&self, rid: usize) -> bool {','    pub(crate) fn can_read_future_entries(&self,rid:usize,arity:usize)->bool{self.enabled && (0..arity).any(|atom|self.queries.get(rid,atom).is_some())}\n    pub(crate) fn active_for_rule(&self, rid: usize) -> bool {')
    p=src/'entry_schedule.rs'
    change(p,'    #[cfg(feature = "gpu-bindings")]\n    pub(crate) fn retire_dedicated','''    pub(crate) fn reader_fanout(&self)->Vec<usize>{
        self.plan.tables.iter().enumerate().map(|(_t,ns)|{
            if !self.enabled{return 0;}
            #[cfg(feature="sparse-cells")] if self.publication_nodes[_t].is_some(){return 0;}
            ns.len()
        }).collect()
    }
    pub(crate) fn retire_dedicated''')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'        let initial_cells =','''        if let Some(mode)=req.get("reader_mode").and_then(|v|v.as_u64()){
            runtime.install_publication_readers(u8::try_from(mode)?,audit)?;
        }
        let initial_cells =''')
    change(p,'        if one_shot {\n            let single =','        report["publication_readers"]=runtime.reader_report();\n        if one_shot {\n            let single =')
