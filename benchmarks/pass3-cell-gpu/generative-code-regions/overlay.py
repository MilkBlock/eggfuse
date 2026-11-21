from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def replace(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/'src';p=src/'learned_pair_family.rs';s=p.read_text()
    s=replace(s,'struct Family {','struct Family {\n    region:RegionWork,')
    s=replace(s,'struct SourceProjection {','struct SourceProjection {\n    region_max_epoch:HashMap<FamilyKey,u64>,')
    a='        s.family.compound=cfg["compound"]==true;'
    s=replace(s,a,'''        s.family.region.mode=cfg["region_mode"].as_u64().unwrap_or(0).try_into().map_err(|_|"bad region mode")?;
        if s.family.region.mode>3 || (s.family.region.mode!=0 && cfg["mode"].as_u64()!=Some(2)){return Err("regions require wide pair plans".into());}
        if s.family.region.mode==2{s.family.region.weights=serde_json::from_value(cfg["region_weights"].clone()).map_err(|_|"bad region head")?;
            if !s.family.region.weights.iter().all(|v|v.is_finite()){return Err("nonfinite region weights".into());}}
        s.family.region.corrupt=cfg["bad_region_keys"]==true;
'''+a)
    a='        let p = Rc::new(SourceProjection {'
    s=replace(s,a,'''        let mut region_max_epoch=HashMap::<u64,u64>::new();
        if matches!(self.family.region.mode,1|2){
            for (&key,(_,epoch)) in codes.iter().zip(rows.iter()){
                let entry=region_max_epoch.entry(key).or_default();*entry=(*entry).max(*epoch);
            }
            self.family.region.receiver_indexed_epochs+=rows.len() as u64;
        }
'''+a+'\n            region_max_epoch,')
    s=replace(s,'let (span, key_cap, limit) = if self.family.mode == 1 {',
                 'let (span,key_cap,limit)=if self.family.region.mode==3{(REGION_ROOTS,8usize,REGION_PAIRS)}else if self.family.mode==1{')
    orig='let packets = self.issue_families(c,steps,&lp,&hist,second.as_ref().map(|p|p.0.as_slice()),cut);'
    s=replace(s,orig,'''let packets=if !matches!(self.family.region.mode,1|2){
            self.issue_families(c,steps,&lp,&hist,second.as_ref().map(|p|p.0.as_slice()),cut)
        }else{
            self.issue_regions(c,steps,&lp,&hist,second.as_ref().map(|p|p.0.as_slice()),cut)
        };''')
    s=replace(s,'let (max_roots, max_keys, max_pairs) = if self.family.mode == 1 {',
                'let (max_roots,max_keys,max_pairs)=if matches!(self.family.region.mode,1|2){(REGION_ROOTS,REGION_ROOTS,REGION_PAIRS)}else if self.family.region.mode==3{(REGION_ROOTS,8,REGION_PAIRS)}else if self.family.mode==1{')
    a='let p = Packet::read(&wire, first_action + offset as u64,compound)?;'
    s=replace(s,a,'''let p=if matches!(self.family.region.mode,1|2){
                if self.family.region.corrupt{wire[96]^=0x80;}
                decode_region(&wire,first_action+offset as u64,compound,c.graph.epoch,self.rule,
                    left.frame.generation,right.frame.generation,c.graph.stats.unions,cut,&lp,&rp,&mut self.family.region)?
            }else{Packet::read(&wire,first_action+offset as u64,compound)?};''')
    p.write_text(s+'\ninclude!("learned_code_regions.rs");\n');copyfile(HERE/'region.rs',src/'learned_code_regions.rs')
    p=src/'ordinary_witness.rs';s=p.read_text()
    s=replace(s,'"compound_work":s.family.compound_work,','"region_work":s.family.region,"compound_work":s.family.compound_work,')
    p.write_text(s)
