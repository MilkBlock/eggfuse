from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent


def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {tier:Tiered,')
    s=change(s,'let s=Store{','let s=Store{tier:Tiered::default(),')
    s=change(s,'"prepared":s.prepared.stats,','"tier":s.tier.stats,"prepared":s.prepared.stats,')
    s=change(s,'            s.issued_generations.clear();','''            if s.tier.materialize && steps.len()>=3{s.prepare_tiers(&mut steps);}
            s.issued_generations.clear();''')
    p.write_text(s+'\ninclude!("tiered_ports.rs");\n');shutil.copyfile(HERE/'tiers.rs',src/'tiered_ports.rs')
    p=src/'forward_feasibility.rs';s=p.read_text()
    s=change(s,'self.code(&row.values[col]).key','self.key_only(&row.values[col])')
    s=change(s,'self.code(&canon(v, &c.graph.parents)).key','self.key_only(&canon(v, &c.graph.parents))')
    p.write_text(s)
    s=p.read_text().replace('rows: rustc_hash::FxHashMap<u32, u64>', 'rows: rustc_hash::FxHashMap<u64, u64>')
    s=change(s,'struct ForwardState {','struct ForwardState {\n    extra_views:usize,')
    s=change(s,'Literal(u16),','Literal(u32),')
    assert s.count('let mut key = 0u32;')==2
    s=s.replace('let mut key = 0u32;','let mut key = 0u64;')
    s=change(s,'(key << B) | u32::from(self.key_only(&row.values[col]))',
            '(key << ((1+self.forward.extra_views)*B)) | u64::from(self.proof_word(&row.values[col]))')
    s=change(s,'PortSource::Literal(self.key_only(&canon(v, &c.graph.parents)))',
             'PortSource::Literal(self.proof_word(&canon(v, &c.graph.parents)))')
    s=change(s,'ports[*slot].ok_or("missing proposed source slot")?.key',
             'signature(ports[*slot].ok_or("missing proposed source slot")?,false,1+self.extra_views)')
    s=change(s,'(key << B) | u32::from(code)','(key << ((1+self.extra_views)*B)) | u64::from(code)')
    p.write_text(s)
    p=src/'atom_checks.rs';s=p.read_text()
    for before,after in [('self.code(&canon(v, &c.graph.parents)).key','self.key_only(&canon(v, &c.graph.parents))'),
                         ('self.code(&row.values[col]).key','self.key_only(&row.values[col])'),
                         ('self.code(&row.values[a]).key','self.key_only(&row.values[a])'),
                         ('self.code(&row.values[b]).key','self.key_only(&row.values[b])')]:
        s=change(s,before,after)
    p.write_text(s)
    p=src/'incremental_raw.rs';s=p.read_text()
    s=change(s,'let code = self.code(&row.values[col]).key as usize;','let code = self.key_only(&row.values[col]) as usize;')
    p.write_text(s)
    p=src/'single_epochs.rs';s=p.read_text()
    s=change(s,'let code = |v: &Value| codes.port(v, s.views).key as usize;', '''let code = |v: &Value| if s.tier.primary{
        codes.pair(mix(code_seed(v))).1 as usize
    }else{codes.port(v, s.views).key as usize};''')
    p.write_text(s)
    p=src/'ordinary_shortlist.rs';s=p.read_text()
    s=change(s,'struct StackStep {compiled:Option<PreparedStep>,','struct StackStep {tier:Option<TierStep>,compiled:Option<PreparedStep>,')
    s=change(s,'descriptors.push(StackStep{compiled:None,','descriptors.push(StackStep{tier:None,compiled:None,')
    anchor='if let Some(idx)=d.compiled.as_ref().and_then(|p|p.index.as_ref()){'
    s=change(s,anchor,'''if let Some(idx)=d.tier.as_ref().and_then(|t|t.index.as_ref()){
                Some(self.shortlist(&d.frame,idx,col,q))
            }else '''+anchor)
    anchor='if let Some(compiled)=d.compiled.as_ref().filter(|p|p.columns_ready){'
    # There are two distinct sites. Use full surrounding statements to pin each change.
    s=change(s,'let value='+anchor,'''let value=if let Some(t)=d.tier.as_ref().filter(|t|t.complete){
                        self.tier.stats.extra_reads+=1;
                        decode_port(t.extra[&col][j])
                    }else '''+anchor)
    s=change(s,'            '+anchor+'\n                for (slot,keys)', '''            if let Some(t)=d.tier.as_ref().filter(|t|t.complete){
                for (slot,keys) in &t.publish{ports[*slot]=Some(decode_port(keys[j]));}
                self.tier.stats.published_reads+=t.publish.len() as u64;
                self.memo_counts.emitted_port_codes+=t.publish.len() as u64;
            }else '''+anchor+'\n                for (slot,keys)')
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),anchor,'''        if let Some(cfg)=req.get("tiered_ports"){ordinary_witness::enable_tiers(cfg.clone())?;}
'''+anchor))
