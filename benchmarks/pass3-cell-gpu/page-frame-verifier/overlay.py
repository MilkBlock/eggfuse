from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def change(p,old,new):
    v=p.read_text()
    if v.count(old)!=1:raise ValueError((p.name,old,v.count(old)))
    p.write_text(v.replace(old,new))


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs'
    shutil.copyfile(HERE/'kernel.rs',src/'page_frame_reader.rs')
    with p.open('a') as f:f.write('\ninclude!("page_frame_reader.rs");\n')
    change(p,'struct Store {','struct Store {page_kernel:PageKernel,')
    change(p,'let s=Store{','let s=Store{page_kernel:PageKernel::default(),')
    change(p,'json!({"pages":s.pages,','json!({"page_reads":s.page_kernel.work,"pages":s.pages,')
    change(p,'        let mut out=vec![];let mut raw=vec![];if s.accel>=4{',
           '        let mut page_frames=vec![];let mut out=vec![];let mut raw=vec![];if s.accel>=4{')
    change(p,'            s.issued_generations.clear();','''            if matches!(s.page_kernel.mode,1|3|7){page_frames=steps.iter().map(|step|step.frame.clone()).collect();}
            s.issued_generations.clear();''')
    v=p.read_text();a=v.index('                for i in 0..page.count(){');b=v.index('            }\n            let stack_recipes',a)
    p.write_text(v[:a]+'                if s.page_kernel.on { s.check_parent_page(g,&c,&p,&page,&page_frames,&mut out,&mut no_more)?; }else{\n'+v[a:b]+'                }\n'+v[b:])
    change(p,'let root_recipe=crate::joint_root::bind(p.root_recipe.take(),c.graph,self.rule,&p.witness,&p.slots)?;',
        'let root_recipe=if self.page_kernel.seal_active{crate::joint_root::bind_checked_page(p.root_recipe.take(),c.graph,self.rule,&p.witness,&p.slots,self.page_kernel.mode>=8,&mut self.page_kernel.work.seals)?}else{crate::joint_root::bind(p.root_recipe.take(),c.graph,self.rule,&p.witness,&p.slots)?};')
    for args,values in [('&atom.args','&row.values'),('&atom.args[atom.args.len()-1..]','std::slice::from_ref(&v)')]:
        old='if self.accel<5{self.publish_ports('+args+','+values+',&mut p);}'
        count='atom.args.len() as u64' if args=='&atom.args' else '1'
        change(p,old,'if self.page_kernel.tail_active{self.page_kernel.work.dead_port_calls+=1;self.page_kernel.work.dead_port_args+='+count+';}else '+old)
    root=src/'joint_root.rs'
    change(root,'refs:Vec<Ref>,ports:Option<Vec<Field>>','refs:ParentRefs,ports:Option<Vec<Field>>')
    change(root,'template,refs,ports:shared.', 'template,refs:ParentRefs::Owned(refs),ports:shared.')
    change(root,'template,refs,ports:None','template,refs:ParentRefs::Owned(refs),ports:None')
    for name in ('multi_root_pages.rs','adaptive_root_page.rs'):
        change(src/name,'            refs,\n            ports: None,','            refs:ParentRefs::Owned(refs),\n            ports: None,')
    shutil.copyfile(HERE/'parent_refs.rs',src/'verified_parent_refs.rs')
    with root.open('a') as f:f.write('\ninclude!("verified_parent_refs.rs");\n')
    shutil.copyfile(HERE/'seal.rs',src/'verified_page_seal.rs')
    with (src/'joint_root.rs').open('a') as f:f.write('\ninclude!("verified_page_seal.rs");\n')
    p=src/'ordinary_shortlist.rs'
    for op in ('push(j as u32);','pop();'):
        change(p,'if self.accel>=5 || self.raw_cache.capturing{self.flat_offsets.'+op,
               'if self.accel>=5 || self.raw_cache.capturing || matches!(self.page_kernel.mode,1|3|7|9|11){self.flat_offsets.'+op)
    change(p,'            let refs=steps.iter().zip(path.iter()).map(|(step,w)|crate::joint_root::Ref{','''            if self.page && matches!(self.page_kernel.mode,9|11){
                for (j,(step,&w)) in steps.iter().zip(path.iter()).enumerate(){
                    let f=&step.frame;
                    let candidate=self.flat_offsets.get(j).and_then(|pos|f.rows.get(*pos as usize));
                    let checked=candidate.filter(|r|r.witness==w && !r.hidden && r.table==f.table);
                    if checked.is_none(){self.page_kernel.work.issue_offset_mismatches+=1;}
                    let version=if let Some(r)=checked && f.generation==c.graph.query_versions[f.table] && f.born_at_union==c.graph.stats.unions {
                        self.page_kernel.work.issue_frame_refs+=1;r.epoch
                    }else{
                        self.page_kernel.work.issue_source_refs+=1;
                        c.graph.visible_epoch(w).expect("issued source witness must be visible")
                    };
                    self.page_refs.push(crate::joint_root::Ref{atom:step.atom,row:w,version});
                }
                return;
            }
            let refs=steps.iter().zip(path.iter()).map(|(step,w)|crate::joint_root::Ref{''')
    change(p,'                self.page_refs.extend(refs);','''                if matches!(self.page_kernel.mode,1|3|7){
                    self.page_kernel.positions.extend_from_slice(&self.flat_offsets);
                }
                self.page_refs.extend(refs);''')
    p=crate/'examples/joint_witness_session.rs'
    change(p,'            ordinary_witness::set_multi_pages(fault)?;','''            ordinary_witness::set_multi_pages(fault)?;
            if let Some(q)=req.get("page_reader"){ordinary_witness::configure_page_kernel(u8::try_from(q["mode"].as_u64().unwrap_or(0))?,u8::try_from(q["fault"].as_u64().unwrap_or(0))?)?;}''')
    change(p,'        let start = Instant::now();','        let start_decode=runtime.graph.fact_decode_calls.get();\n        let start = Instant::now();')
    change(p,'        let ms = start.elapsed()', '        let decode_count=runtime.graph.fact_decode_calls.get()-start_decode;\n        let ms = start.elapsed()')
    change(p,'        report["merge_child"]=', '        report["physical_decodes"]=json!(decode_count);\n        report["merge_child"]=')
