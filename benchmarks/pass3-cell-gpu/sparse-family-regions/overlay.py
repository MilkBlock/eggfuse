from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def edit(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def install(crate):
    src=crate/'src';p=src/'learned_pair_family.rs';s=p.read_text()
    def rep(a,b):
        nonlocal s
        s=edit(s,a,b)
    rep('struct Family {','struct Family {\n    sparse:SparseRegions,')
    rep('        s.family.mode = mode as u8;', '        s.family.sparse.enabled=cfg["sparse_regions"]==true;\n        s.family.mode = mode as u8;')
    rep('        let stat = &mut self.family.metrics;', '''        let mut gathered=if self.family.sparse.enabled{
            let rcol=steps[1].shared[0].1;
            let col=steps[0].publish.iter().find(|(_,s)|*s==rcol).unwrap().0;
            let role=(steps[0].table,col,if second.is_some(){1+self.rule}else{0},span);
            let frame=&steps[0].frame;
            let index=self.family.sparse.directory(role,(frame.generation,frame.born_at_union),left,second,&steps[0],self.views);
            let (found,absent,stale)=self.family.sparse.gather(&index,right,cut,left.len().div_ceil(span));
            self.family.metrics.absent+=absent;self.family.metrics.stale+=stale;self.family.metrics.prototypes+=index.entries as u64;
            Some(found)
        }else{None};
        let stat = &mut self.family.metrics;''')
    start=s.index('            stat.inspected_left += ls.len() as u64;')
    end=s.index('            let mut keys = Vec::new();',start)
    original=s[start:end].replace('            let lo = span * block;','').replace('            let hi = lo + ls.len();','')
    s=s[:start]+'''            let lo=span*block;let hi=lo+ls.len();
            let regions=if let Some(pub_regions)=gathered.as_mut(){std::mem::take(&mut pub_regions[block])}else{
'''+original+'''                self.family.sparse.counts.left_rows+=ls.len() as u64;
                self.family.sparse.counts.construction_key_updates+=ls.len() as u64;
                let mut regions=Vec::new();
                for (code,(lcount,lmax)) in heads{
                    stat.prototypes+=1;self.family.sparse.counts.keys_probed+=1;
                    let Some(&(rn,rmax))=right.get(&code) else{stat.absent+=1;self.family.sparse.counts.keys_absent+=1;continue};
                    self.family.sparse.counts.epoch_checks+=1;
                    if lmax.max(rmax)<cut{stat.stale+=1;self.family.sparse.counts.no_fresh_region+=1;continue}
                    regions.push((code,lcount,rn));self.family.sparse.counts.materialized_regions+=1;
                }
                regions
            };
'''+s[end:]
    start=s.index('            for (code, (lcount, lmax)) in heads {');end=s.index('                let volume =',start)
    s=s[:start]+'            for (code,lcount,rn) in regions {\n'+s[end:]
    rep('        let rp = self.projected_column(right, rc);','        self.family.sparse.sending=true;\n        let rp = self.projected_column(right, rc);')
    rep('        let rule = self.family.rules.entry(self.rule).or_default();','''        self.family.sparse.sending=false;
        if self.family.trace{
            for packet in &packets {
                self.family.sparse.digest.update((packet.len() as u64).to_le_bytes());
                self.family.sparse.digest.update(packet);
            }
        }
        let rule = self.family.rules.entry(self.rule).or_default();''')
    p.write_text(s+'\ninclude!("sparse_family_regions.rs");\n');copyfile(HERE/'sparse.rs',src/'sparse_family_regions.rs')
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=edit(s,'    fn code(&mut self,v:&Value)->Port{','''    fn code(&mut self,v:&Value)->Port{
        if self.family.sparse.sending{
            let c=&mut self.family.sparse.counts;c.model_port_requests+=1;
            if self.baked_codes.is_some(){c.model_table_lookups+=1;}else if !self.codes.contains_key(v){c.model_online_encodes+=1;}
        }''')
    s=edit(s,'"compound_work":s.family.compound_work,','"sparse_regions":s.family.sparse.counts,"sparse_wire_sha":format!("{:x}",s.family.sparse.digest.clone().finalize()),"compound_work":s.family.compound_work,')
    p.write_text(s)
