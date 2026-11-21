from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)
def install(crate):
    src=crate/'src';p=src/'ordinary_witness.rs';s=p.read_text()
    s=rep(s,'struct Store {wave:', 'struct Store {pair_actor:PairActor,wave:')
    s=rep(s,'let s=Store{wave:', 'let s=Store{pair_actor:Default::default(),wave:')
    s=rep(s,'json!({"wave":s.wave.stats,','json!({"pair_actor":s.pair_actor.work,"pair_examples":s.pair_actor.examples,"wave":s.wave.stats,')
    a='''            for refs in groups{
                let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;
                if g.spec_cells.is_some(){g.spec_page(rid,bank.stage_serial(),bank.count(),crate::graph::speculative::Handle::Multi(bank.clone()));}

                tuples+=bank.count();s.max_sealed_page=s.max_sealed_page.max(bank.count());pages.push(bank);
            }'''
    s=rep(s,a,'''            let mut actions=std::mem::take(&mut s.pair_actor.pending).into_iter().peekable();
            let n=groups.len();let mut ordinary=groups.into_iter();
            for offset in 0..=n {
                while actions.peek().is_some_and(|x|x.0==offset){
                    let (_,packet,features)=actions.next().unwrap();
                    let bank=s.receive_bucket(&c,packet,features)?;
                    tuples+=bank.count();s.max_sealed_page=s.max_sealed_page.max(bank.count());pages.push(bank);
                }
                if let Some(refs)=ordinary.next(){
                    let bank=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;
                    s.pair_actor.work.external_residual+=bank.count() as u64;
                    if g.spec_cells.is_some(){g.spec_page(rid,bank.stage_serial(),bank.count(),crate::graph::speculative::Handle::Multi(bank.clone()));}
                    tuples+=bank.count();s.max_sealed_page=s.max_sealed_page.max(bank.count());pages.push(bank);
                }
            }
            assert!(actions.next().is_none());
            if s.detailed{
                for page in &pages {for i in 0..page.count(){let parents=page.parents(i);
                    s.raw_digest.update((run as u64).to_le_bytes());s.raw_digest.update((rid as u64).to_le_bytes());
                    s.raw_digest.update((parents.len() as u64).to_le_bytes());
                    for r in parents.iter(){s.raw_digest.update((r.atom as u64).to_le_bytes());match r.row{
                        Dependency::Fact(f)=>{s.raw_digest.update([1]);s.raw_digest.update(f.cell.to_le_bytes());s.raw_digest.update(f.op.to_le_bytes());},
                        Dependency::Function(k)=>{s.raw_digest.update([2]);s.raw_digest.update((k as u64).to_le_bytes());}
                    }}
                }}
            }''')
    p.write_text(s+'\ninclude!("pair_bucket_actor.rs");\n');copyfile(HERE/'actor.rs',src/'pair_bucket_actor.rs')
    p=src/'ordinary_shortlist.rs';s=p.read_text()
    s=rep(s,'if self.detailed{\n                self.raw_digest.update','if self.detailed && !self.wave.preparing{\n                self.raw_digest.update');p.write_text(s)
    p=src/'incremental_raw.rs';s=p.read_text()
    a='            let shortlist;\n            let reverse = back.get(&l);'
    s=rep(s,a,'''            if self.pair_actor.enabled && self.wave.preparing {
                // Never borrow an already enumerated reverse join. These static and
                // watermark conditions certify that an entire primary key bucket
                // passes the original issuer (the exact verifier still runs).
                let clean=!corr && (!selective || right_fresh==0) && !back.contains_key(&l) &&
                    right.shared.len()==1 && eq.is_none() && delayed.is_none() &&
                    self.atoms.stages.get(1).is_none_or(|a|a.tests.is_empty()) &&
                    row.epoch>=mark && self.cap==usize::MAX;
                if clean && let Some(bins)=index.as_ref().and_then(|h|h.packed.as_ref()){
                    let key=signature(left_cols[0].1[l],true,self.views);
                    let count=bins.get(&key).map_or(0,|b|b.len());
                    if self.issue_bucket(c,steps,row,left_cols[0].0,key,count){continue;}
                }else{self.pair_actor.work.hard_ineligible+=1;}
            }
'''+a)
    p.write_text(s)
    p=src/'multi_root_pages.rs';s=p.read_text()
    s=rep(s,'    refs: Vec<Ref>,\n    withheld:', '    refs: Vec<Ref>,\n    bucket:Option<VerifiedBucket>,\n    withheld:')
    s=rep(s,'            refs,\n            withheld,','            refs,bucket:None,\n            withheld,')
    s=rep(s,'pub(crate) fn parents(&self, slot: usize) -> &[Ref] {\n        self.slice(slot).expect("sealed multi-witness slot")','''pub(crate) fn parents(&self, slot: usize) -> PageLane<'_> {
        if let Some(b)=&self.0.bucket{
            let &(row,version)=b.posting.get(slot).expect("verified group lane");
            PageLane::Generated([b.left.clone(),Ref{atom:b.atom,row,version}])
        }else{PageLane::External(self.slice(slot).expect("sealed multi-witness slot"))}''')
    s=rep(s,'let mut refs = self.slice(slot)?.to_vec();','if slot>=self.count(){return None;}\n        let mut refs = self.parents(slot).to_vec();')
    p.write_text(s+'\ninclude!("pair_bucket_page.rs");\n');copyfile(HERE/'page.rs',src/'pair_bucket_page.rs')
    p=crate/'examples/joint_witness_session.rs';s=p.read_text();a='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(rep(s,a,'        if let Some(v)=req.get("pair_actor"){ordinary_witness::configure_pair_actor(v)?;}\n'+a))
