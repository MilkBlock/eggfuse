"""Install the independent-witness experiment in a temporary copy of the native crate."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def one(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:raise RuntimeError(f'{path.name}: source boundary changed: {old}')
    path.write_text(text.replace(old,new))


def install(crate_dir):
    crate=Path(crate_dir);src=crate/'src'
    shutil.copyfile(HERE/'single.rs',src/'single_witness.rs')
    with (src/'lib.rs').open('a') as f:f.write('\nmod single_witness;\n')
    one(src/'cell_observation.rs','        QueryFacts::None => vec![],','        QueryFacts::Neural(original,_)=>retained_witnesses(original),\n        QueryFacts::None => vec![],')
    q=src/'cell_match.rs'
    one(q,'pub(crate) enum QueryFacts {','pub(crate) enum QueryFacts {\n    Neural(Box<QueryFacts>,crate::single_witness::Mark),')
    one(q,'impl QueryFacts {','''impl QueryFacts {
    pub(crate) fn tagged(self,t:crate::single_witness::Mark)->Self{Self::Neural(Box::new(self),t)}
    pub(crate) fn neural(&self)->Option<&crate::single_witness::Mark>{
        match self{Self::Neural(_,t)=>Some(t),_=>None}
    }''')
    one(q,'            Self::One(source, slot) if *source == atom => *slot = fact,','            Self::Neural(base,_)=>base.record(atom,witness),\n            Self::One(source, slot) if *source == atom => *slot = fact,')
    one(q,'            Self::One(source, fact) if *source == atom => *fact,','            Self::Neural(base,_)=>base.get(atom),\n            Self::One(source, fact) if *source == atom => *fact,')
    one(q,'            Self::Ports(rows) => rows[atom],','            Self::Neural(base,_)=>base.receipt(atom),\n            Self::Ports(rows) => rows[atom],')
    p=src/'runtime.rs'
    one(p,'        let stage_cursor = self.stage_spine.begin_step(','        if let Some(s)=self.stage_spine.single.as_mut(){s.winner=b.known.neural().cloned();}\n        let stage_cursor = self.stage_spine.begin_step(')
    marker='        let tables = &mut self.required_tables[rid];'
    one(p,marker,'''        if !probe && self.stage_spine.single.as_ref().is_some_and(|s|s.accepts(rid)){
            let facts=self.stage_spine.alias_query_facts(&self.graph,rid);
            let wm=self.watermarks[rid];
            let mut rows=self.stage_spine.single.as_mut().unwrap().generate(&self.graph,rid,wm)?;
            let (mut routed,_)=self.stage_spine.resume_tokens(&mut self.graph,&mut self.entry_schedule,rid,wm,&rows,&facts)?;
            for row in &mut rows{
                let known=facts.with_rows((0..self.graph.program.rules[rid].query.len()).filter_map(|i|row.known.receipt(i).map(|w|(i,w))));
                row.known=match row.known.neural(){Some(mark)=>known.tagged(mark.clone()),None=>known};
            }
            routed.append(&mut rows);self.pending[rid].clear();
            return self.dedup_bindings(rid,routed);
        }
        if !probe && self.stage_spine.single.as_ref().is_some_and(|s|!s.unsupported){self.pending[rid].clear();return Ok(Vec::new());}
'''+marker)
    one(p,'    pub fn execute(&mut self) -> Result<()> {','''    pub fn use_single_witness(&mut self,path:&std::path::Path)->Result<()>{
        let spec:serde_json::Value=serde_json::from_slice(&std::fs::read(path).map_err(|e|e.to_string())?).map_err(|e|e.to_string())?;
        let model=spec.get("model").filter(|v|!v.is_null()).map(|v|serde_json::from_value(v.clone())).transpose().map_err(|e|e.to_string())?;
        self.stage_spine.single=Some(crate::single_witness::Trial::new(&self.graph,spec["mode"].as_str().ok_or("missing mode")?.to_string(),model,spec["residual"].as_bool().ok_or("missing completion flag")?)?);
        if let Some(v)=spec["complete_unsupported"].as_bool(){self.stage_spine.single.as_mut().unwrap().unsupported=v;}
        Ok(())
    }
    pub fn single_report(&self)->Option<serde_json::Value>{self.stage_spine.single.as_ref().map(|s|s.report())}
    pub fn execute(&mut self) -> Result<()> {''')
    p=src/'stage_spine.rs'
    one(p,'pub struct Programs {','pub struct Programs {\n    pub(crate) single:Option<crate::single_witness::Trial>,')
    one(p,'            forest: None,','            forest: None,\n            single:None,')
    one(p,'        if let Some(forest)=&mut self.forest {forest.issue_root(rid,epoch);}','        if let Some(forest)=&mut self.forest {forest.issue_root(rid,epoch);}\n        if let Some(single)=&mut self.single{single.commit(rid,epoch,values,p);}')
    # Make the existing verified-binding cursor continuation available without a Metal build.
    text=p.read_text().replace('#[cfg(feature="gpu-bindings")]','').replace('#[cfg(feature = "gpu-bindings")]','')
    text=text.replace('for atom in 0..2 {\n                if self.queries.get(rid, atom).is_none()', 'for atom in 0..g.program.rules[rid].query.len() {\n                if self.queries.get(rid, atom).is_none()')
    text=text.replace('facts.with_rows((0..2).map(|i|(i,supplied.known.receipt(i).expect("verified witness"))))',
                      'facts.with_rows((0..g.program.rules[rid].query.len()).filter_map(|i|supplied.known.receipt(i).map(|w|(i,w))))')
    text=text.replace('record_answer(&mut results,supplied.values.clone(),projected,supplied.epoch,cursor);',
                      'let projected=match supplied.known.neural(){Some(t)=>projected.tagged(t.clone()),None=>projected};\n                record_answer(&mut results,supplied.values.clone(),projected,supplied.epoch,cursor);')
    p.write_text(text)
    p=src/'main.rs'
    one(p,'    let mut runtime = Executor::new(graph, audit);','    let mut runtime = Executor::new(graph, audit);\n    if let Some(policy)=std::env::var_os("EGGFUSE_SINGLE_POLICY"){runtime.use_single_witness(std::path::Path::new(&policy))?;}')
    one(p,'    if let Some(forest)=runtime.precomputed_report()', '    if let Some(single)=runtime.single_report(){report["single_witness"]=single;}\n    if let Some(forest)=runtime.precomputed_report()')
