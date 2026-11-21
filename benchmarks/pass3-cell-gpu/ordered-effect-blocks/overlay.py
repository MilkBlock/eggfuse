from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def change(text, old, new):
    if text.count(old)!=1:
        raise ValueError(old)
    return text.replace(old,new)


def install(crate):
    src=crate/'src'
    p=src/'graph.rs';s=p.read_text()
    s=change(s,'pub struct Graph {','pub struct Graph {pub(crate) effect_operand_audit:bool,pub(crate) effect_audit_fields:std::cell::Cell<u64>,')
    s=change(s,'        let mut g = Self {','        let mut g = Self {effect_operand_audit:false,effect_audit_fields:std::cell::Cell::new(0),')
    p.write_text(s+'\ninclude!("ordered_effect_audit.rs");\n')
    copyfile(HERE/'audit.rs',src/'ordered_effect_audit.rs')
    p=src/'cell_prefix.rs'
    s=p.read_text()
    a='        let cell = self.reserve_cell_id()?;'
    s=change(s,'receipts: &mut crate::cell::Effects, mut prefix: P) -> Result<Start> {','receipts: &mut crate::cell::Effects, prefix: P) -> Result<Start> {')
    s=change(s,'        let ops = self.program.templates[template].ops.clone();\n        prefix.enter();','        prefix.enter();')
    s=change(s,a,'''        let ops=self.program.templates[template].ops.clone();
        self.start_cell_ops(template,values,parent,receipts,prefix,ops)
    }
    pub(crate) fn start_cell_ops<P:Prefix>(&mut self,template:usize,values:crate::slots::Slots,parent:Option<FactRef>,
        receipts:&mut crate::cell::Effects, mut prefix:P,ops:std::rc::Rc<Vec<Op>>)->Result<Start>{
'''+a)
    a='            let instruction = &ops[op];'
    s=change(s,a,a+'\n            if self.effect_operand_audit{self.audit_ordered_effect(template,op,instruction,cell,Some(&frame))?;}')
    p.write_text(s)
    p=src/'runtime.rs'
    s=change(p.read_text(),'pub struct Executor {','pub struct Executor {\n    effect_blocks:BlockRuntime,')
    s=change(s,'        let mut e = Self {','        let mut e = Self { effect_blocks:BlockRuntime::default(),')
    for fname in ('apply','apply_owned'):
        a=f'    fn {fname}(\n        &mut self,\n        rid: usize,\n        b: Binding,'
        s=change(s,a,a+'\n        block:Option<&EffectBlock>,')
    s=change(s,'self.apply_owned(rid,b,#[cfg','self.apply_owned(rid,b,block,#[cfg')
    s=change(s,'        for (rid, rows) in groups {','        for (rid, rows) in groups {\n            let group_block=self.block_for_group(rid,rows.len());')
    s=change(s,'                    binding,\n                    #[cfg(feature = "structural-depth")]','                    binding,group_block.as_deref(),\n                    #[cfg(feature = "structural-depth")]')
    a='        let ordinary = |me: &mut Self, values: crate::slots::Slots,'
    s=change(s,a,'''        let block=block.filter(|x|x.template==template);
        let wired=self.effect_blocks.mode==2 && block.is_some_and(|p| {
            let conflict=p.protected.iter().any(|s|b.values.contains_key(s));
            self.effect_blocks.work.materialized_copy_conflicts+=u64::from(conflict);
            !conflict
        });
'''+a)
    a='                let width = me.graph.program.templates[template].ops.len();'
    s=change(s,a,'''                if let Some(plan)=block{
                    me.effect_blocks.work.constructor_calls+=1;
                    let pos=EffectPositions{block:plan,pos:0,wired,work:&mut me.effect_blocks.work};
                    return me.graph.start_cell_ops(template,values,b.parent,receipts,pos,plan.ops(wired));
                }
'''+a)
    a='        let ops = self.graph.program.templates[template].ops.clone();\n        let mut completed = true;'
    s=change(s,a,'''        let ops = block.map_or_else(||self.graph.program.templates[template].ops.clone(),|plan|plan.ops(wired));
        if block.is_some(){self.effect_blocks.work.dynamic_calls+=1;}
        let mut tape=block.map(|plan|EffectPositions{block:plan,pos:first_op,wired,work:&mut self.effect_blocks.work});
        let mut ordinary_positions=first_op..ops.len();
        let mut completed = true;''')
    a='        for (i, op) in ops.iter().enumerate().skip(first_op) {\n            if self.graph.known_stats.elide_static(aliases, i) {'
    s=change(s,a,'''        while let Some(i)=if let Some(cursor)=tape.as_mut(){cursor.advance(&mut self.graph.known_stats,false)}else{ordinary_positions.next()} {
            let op=&ops[i];
            if self.graph.effect_operand_audit && wired{self.graph.audit_ordered_effect(template,i,op,cell,None)?;}
            if tape.is_none() && self.graph.known_stats.elide_static(aliases,i) {''')
    a='        let state = self.graph.rhs_frame_mut(cell).unwrap();\n        state.completed = completed;'
    s=change(s,a,'        if completed && block.is_some(){completed_prefix=ops.len();}\n'+a)
    a='            let group_block=self.block_for_group(rid,rows.len());'
    s=change(s,a,a+'\n            let effect_before=self.graph.effect_operand_audit.then(||self.group_effect_counts());')
    a='            if let Some((clock, bindings, before)) = profile {'
    s=change(s,a,'            if let Some(before)=effect_before{self.save_group_counts(rid,before); }\n'+a)
    p.write_text(s+'\ninclude!("ordered_effect_blocks.rs");\n')
    copyfile(HERE/'block.rs',src/'ordered_effect_blocks.rs')
    p=crate/'examples/joint_witness_session.rs'
    s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    s=change(s,a,'        if let Some(mode)=req["ordered_effect_blocks"].as_u64(){runtime.configure_effect_blocks(mode,audit,req["ordered_effect_fault"].as_bool()==Some(true))?;}\n'+a)
    a='        report["phases_ms"]='
    p.write_text(change(s,a,'        report["ordered_effect_blocks"]=runtime.ordered_block_report();\n'+a))
    import os
    if os.environ.get("EGGFUSE_ORDERED_WRITE_STUDY")=="1":
        import importlib.util
        spec=importlib.util.spec_from_file_location("group_writes",HERE/"writer.py")
        writer=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(writer)
        writer.install(crate)
