from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent

def change(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)

def install(crate):
    src=crate/'src'
    p=src/'joint_root.rs'
    p.write_text(p.read_text()+'\ninclude!("rank_inputs.rs");\n')
    copyfile(HERE/'accessors.rs',src/'rank_inputs.rs')
    p=src/'runtime.rs';anchor='                crate::ordinary_witness::wave_sealed();'
    p.write_text(change(p.read_text(),anchor,anchor+'\n                self.graph.seal_ranked_staging()?;'))
    p=src/'speculative_staging.rs';s=p.read_text()
    s=change(s,'struct Page {','struct Page {\n    rank_state:LaneState,')
    s=change(s,'        r.pages.push(Page {','        r.pages.push(Page {rank_state:LaneState::default(),')
    s=change(s,'pub(crate) struct Staging {','pub(crate) struct Staging {\n    rank:LaneRank,')
    s=change(s,'        Ok(Self {\n            timing,','        Ok(Self {\n            rank:LaneRank::configure(cfg,storage,timing)?,\n            timing,')
    s=change(s,'        if self.storage == Storage::Named {','        if self.storage == Storage::Named && self.rank.policy.is_none() {')
    s=change(s,'handle: (granted > 0 && self.storage == Storage::Named).then_some(handle)','handle: ((granted > 0 || self.rank.policy.is_some()) && self.storage == Storage::Named).then_some(handle)')
    s=change(s,'        if let Some(j) = page {\n            r.pages[j].fresh += 1;','''        if self.rank.policy.is_some() {
            if let Some(j)=page {
                let p=&mut r.pages[j];let lane=(serial-p.first) as usize;
                let bit=1u64<<(lane%64);let word=&mut p.rank_state.fresh[lane/64];
                if *word&bit==0{
                    *word|=bit;self.rank.counts.fresh_lanes+=1;
                    self.rank.counts.first_fresh+=u64::from(p.rank_state.offset+lane<r.span.len);
                    if p.rank_state.chosen.binary_search_by_key(&lane,|v|v.0).is_ok(){
                        self.rank.counts.selected_fresh+=1;
                        self.rank.counts.beyond_first_fresh+=u64::from(p.rank_state.offset+lane>=r.span.len);
                    }
                    if let Some(x)=p.rank_state.features.get(lane){
                        let pair=self.rank.hist.get_mut(x).unwrap();pair[0]-=1;pair[1]+=1;
                    }
                }else{self.rank.counts.repeated_fresh+=1;}
            }else{self.rank.counts.unlisted_fresh+=1;}
        }
        if let Some(j) = page {
            r.pages[j].fresh += 1;''')
    start=s.index('            if lane >= p.granted {');end=s.index('            if s.named !=',start)
    s=s[:start]+'''            let i=if self.rank.policy.is_some(){
                let Ok(idx)=p.rank_state.chosen.binary_search_by_key(&lane,|v|v.0) else{
                    self.stats.underforecast+=1;self.stats.fallback+=1;return None
                };
                p.rank_state.chosen[idx].1
            }else{
                if lane>=p.granted{self.stats.underforecast+=1;self.stats.fallback+=1;return None}
                p.span.start+lane
            };
            let slab=if self.rank.policy.is_some(){r.span.slab}else{p.span.slab};
            let s=&mut self.slabs[slab][i];
'''+s[end:]
    s=change(s,'.and_then(|h| h.recipe(lane))','.and_then(|h| h.recipe(if self.rank.policy.as_ref().is_some_and(|v|v.foreign){(lane+1)%p.n.max(2)}else{lane}))')
    # A nullary singleton page has an unchecked constructor for an out-of-range
    # lane, but subsequent recipe decoding checks bounds before comparing parents.
    mark='            let rec = self.rules.remove(&rid).unwrap();'
    s=change(s,mark,mark+'''
            if self.rank.policy.is_some(){
                let births:usize=rec.pages.iter().flat_map(|p|&p.rank_state.fresh)
                    .map(|v|v.count_ones() as usize).sum();
                self.rank.counts.oracle_fresh+=rec.span.len.min(births) as u64;
                if rec.now.offers>0 && self.rank.policy.as_ref().is_some_and(|p|p.groups){
                    let mut hist=std::collections::BTreeMap::<Features,[u64;2]>::new();
                    for p in &rec.pages{
                        for (i,x) in p.rank_state.features.iter().enumerate(){
                            let label=(p.rank_state.fresh[i/64]>>(i%64))&1;
                            hist.entry(*x).or_default()[label as usize]+=1;
                        }
                    }
                    self.rank.groups.push((self.epoch,rid,rec.span.len,hist.into_iter().map(|(x,[n,p])|(x,n,p)).collect()));
                }
            }''')
    s=change(s,'        self.used_budget = 0;','        self.rank.done=false;\n        self.used_budget = 0;')
    s=change(s,'json!({"counts":self.stats,"samples":std::mem::take(&mut self.samples),"grants":std::mem::take(&mut self.grants)})','json!({"counts":self.stats,"samples":std::mem::take(&mut self.samples),"grants":std::mem::take(&mut self.grants),"lane_rank":self.rank.report()})')
    p.write_text(s+'\ninclude!("lane_rank.rs");\n')
    copyfile(HERE/'rank.rs',src/'lane_rank.rs')
    p=crate/'examples/joint_witness_session.rs';k='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(p.read_text(),k,'''        if req["spec_cells"].get("lane_rank").is_some() && req["proposal_wave"]!=65536 {
            return Err("lane ranking requires whole Run issue".into())
        }
'''+k))
