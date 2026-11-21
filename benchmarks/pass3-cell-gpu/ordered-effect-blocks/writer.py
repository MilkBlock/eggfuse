"""Compile the existing single-function write descriptors into ordered port programs."""
from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def rep(text,a,b):
    if text.count(a)!=1:raise ValueError(a)
    return text.replace(a,b)


def install(crate):
    src=crate/'src';path=src/'ordered_effect_blocks.rs';s=path.read_text()
    s=rep(s,'struct EffectWork {','struct EffectWork {\n    lower_ns:u64,')
    s=rep(s,'            let b = EffectBlock::compile(', '            let lower_clock=std::time::Instant::now();\n            let b = EffectBlock::compile(')
    s=rep(s,'            plans[rid] = Some(Rc::new(b));','            plans[rid] = Some(Rc::new(b));\n            self.effect_blocks.work.lower_ns+=lower_clock.elapsed().as_nanos() as u64;')
    s=rep(s,'struct EffectBlock {','struct EffectBlock {\n    writer: Option<crate::graph::CompiledWrite>,')
    s=rep(s,'            template: rule.template,','            writer: crate::graph::CompiledWrite::lower(program,rid),\n            template: rule.template,')
    s=rep(s,'!(1..=2).contains(&mode)','!(1..=6).contains(&mode)')
    s=rep(s,'        let p = &self.graph.program;', '        self.graph.ordered_writes.reset();\n        let p = &self.graph.program;')
    s=rep(s,'report["audited_fields"] = json!(self.graph.effect_audit_fields.get());',
          'report["audited_fields"] = json!(self.graph.effect_audit_fields.get());\n            report["writer"]=json!(self.graph.ordered_writes.stats);')
    path.write_text(s)
    p=src/'graph.rs';s=p.read_text()
    s=rep(s,'pub struct Graph {','pub struct Graph {pub(crate) ordered_writes:OrderedWrites,')
    s=rep(s,'        let mut g = Self {','        let mut g = Self {ordered_writes:OrderedWrites::default(),')
    a='        let index = self.function_index(t, key);\n        if let Some(i) = index {\n            let old = canon(&self.functions[i].value, &self.parents);'
    s=rep(s,a,'''        let index=self.function_index(t,key);
        self.set_function_at(t,key,value,site,index)
    }
    fn set_function_at(&mut self,t:usize,key:&[Value],value:Value,site:Option<(u32,usize,Option<usize>)>,index:Option<usize>)->Result<usize>{
        if let Some(i)=index {
            let old=canon(&self.functions[i].value,&self.parents);''')
    p.write_text(s+'\ninclude!("ordered_write_plan.rs");\n')
    copyfile(HERE/'write_plan.rs',src/'ordered_write_plan.rs')
    p=src/'runtime.rs';s=p.read_text()
    a='''            let (cell, index, mut key, changed) = self
                .graph
                .apply_write(template, b.values, b.parent, &write, keep_key)?;'''
    s=rep(s,a,'''            let program=block.filter(|p|p.template==template && self.effect_blocks.mode>=3).and_then(|p|p.writer.as_ref());
            let (cell,index,mut key,changed)=if let Some(plan)=program {
                self.graph.apply_compiled_write(template,b.values,b.parent,&write,keep_key,plan,self.effect_blocks.mode>=5,self.effect_blocks.mode==6)?
            }else{self.graph.apply_write(template,b.values,b.parent,&write,keep_key)?};''')
    s=rep(s,'let block=block.filter(|x|x.template==template);','let block=block.filter(|x|x.template==template && self.effect_blocks.mode!=3);')
    s=rep(s,'let wired=self.effect_blocks.mode==2','let wired=matches!(self.effect_blocks.mode,2|4|5|6)')
    p.write_text(s)
