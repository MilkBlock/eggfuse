// Optional learned-signature directory. Cached values are TypedRow indexes, never verified bindings.
#[derive(Default,Serialize)]
struct MemoStats {
    calls:u64, hits:u64, hits_across_runs:u64, directory_words:u64, nonempty_buckets:u64,
    header_probes:u64, build_row_visits:u64, rebuilds:u64, clears:u64,
    entries:usize, indexes:usize, stored_row_indexes:usize, peak_entries:usize,
    peak_row_indexes:usize, released_entries:u64, emitted_port_codes:u64, snapshot_row_reads:u64,offset_rejects:u64,generation_rejects:u64,peak_flat_bytes:usize,
}
#[derive(Default)]
struct SavedLists {
    generation_run:usize,words:usize,
    entries:HashMap<[u16;6],(usize,Rc<Vec<usize>>)>,
}
struct ShortIndex {
    occupied:[u64;16],
    saved:RefCell<SavedLists>,
}
impl ShortIndex {
    fn new(bins:&BTreeMap<u16,Vec<usize>>)->Self{
        let mut occupied=[0u64;16];
        for key in bins.keys(){occupied[*key as usize/64] |= 1<<(*key%64);}
        Self{occupied,saved:RefCell::new(SavedLists::default())}
    }
}
fn neighborhoods(rad:u32)->Vec<Vec<(usize,u64)>>{
    let mut out=Vec::with_capacity(1<<B);
    for query in 0..(1<<B){
        let mut words=[0u64;16];
        for key in 0..(1<<B){
            if ((key^query) as u16).count_ones()<=rad {words[key/64]|=1<<(key%64)}
        }
        out.push(words.into_iter().enumerate().filter(|(_,w)|*w!=0).collect());
    }
    out
}
impl Store {
    fn evict_memo(&mut self,s:&SavedLists){
        self.memo_counts.entries-=s.entries.len();
        self.memo_counts.stored_row_indexes-=s.words;
        self.memo_counts.released_entries+=s.entries.len() as u64;
    }
    fn shortlist(&mut self,frame:&Frame,idx:&Index,col:usize,q:Port)->Rc<Vec<usize>>{
        self.memo_counts.calls+=1;
        let kind=match self.mode.as_str(){"certified"=>1,"adaptive"=>2,_=>0};
        let span=|cert:u16,uncertain:u16|match kind{1=>cert,2=>uncertain,_=>0};
        let key=[q.query,span(q.certified,q.uncertain),q.extra[0][0],span(q.extra[0][2],q.extra[0][3]),
                 q.extra[1][0],span(q.extra[1][2],q.extra[1][3])];
        if self.accel>=2{
            let mut cache=idx.short.saved.borrow_mut();
            if self.accel==2 && cache.generation_run!=self.run{
                self.evict_memo(&cache);self.memo_counts.clears+=1;
                cache.entries.clear();cache.words=0;cache.generation_run=self.run;
            }
            if let Some((issued,list))=cache.entries.get(&key){
                self.memo_counts.hits+=1;
                self.memo_counts.hits_across_runs+=u64::from(*issued<self.run);
                return list.clone()
            }
        }
        let mut list=vec![];
        let mut append=|s:&mut Self,bucket:u16|{
            s.counts.score_bucket_reads+=1;s.memo_counts.header_probes+=1;
            if let Some(positions)=idx.bins.get(&bucket){
                s.memo_counts.nonempty_buckets+=1;
                for &i in positions{
                    s.memo_counts.build_row_visits+=1;
                    let key=s.code(&frame.rows[i].values[col]);
                    if s.compatible(q,key){list.push(i);}
                }
            }
        };
        match self.mode.as_str(){
            "adaptive"|"certified"=>{
                // Preserve the original descending submask traversal, including its tie order.
                let band=span(q.certified,q.uncertain);let mut mask=band;
                loop{append(self,q.query^mask);if mask==0{break}mask=(mask-1)&band;}
            },
            _ if self.radius<=1=>{
                append(self,q.query);
                if self.radius==1{for j in 0..B{append(self,q.query^(1<<j));}}
            },
            _=>{
                // Intersect a static Hamming-ball word with current occupied signatures.
                // The emitted order remains the BTreeMap's increasing signature order.
                for i in 0..self.neighbors[q.query as usize].len(){
                    let (word,compatible)=self.neighbors[q.query as usize][i];
                    self.memo_counts.directory_words+=1;
                    let mut set=compatible&idx.short.occupied[word];
                    while set!=0{
                        let bit=set.trailing_zeros() as usize;
                        append(self,(word*64+bit) as u16);set&=set-1;
                    }
                }
            }
        }
        let list=Rc::new(list);
        if self.accel>=2 {
            let mut cache=idx.short.saved.borrow_mut();
            cache.words+=list.len();cache.entries.insert(key,(self.run,list.clone()));
            let stats=&mut self.memo_counts;stats.entries+=1;stats.stored_row_indexes+=list.len();
            stats.peak_entries=stats.peak_entries.max(stats.entries);
            stats.peak_row_indexes=stats.peak_row_indexes.max(stats.stored_row_indexes);
        }
        list
    }
}

struct StackStep {
    atom:usize,table:usize,shared:Vec<(usize,usize)>,publish:Vec<(usize,usize)>,
    frame:Rc<Frame>,
}
impl Store {
    fn compile_stack(&mut self,c:&Context<'_>)->Result<(Vec<StackStep>,usize)>{
        let mut used=std::collections::BTreeSet::new();
        let mut descriptors=vec![];
        let mut slot_count=0;
        for (id,_,columns) in &c.inst[..c.pick_count]{
            let a=&c.rule.query[*id];
            let Call::Table(table)=a.call else{return Err("non-relation in pointer plan".into())};
            let mut shared=vec![];
            for &col in columns {
                let Arg::Slot(s)=a.args[col] else{return Err("static pointer column".into())};
                used.insert(s);slot_count=slot_count.max(s+1);shared.push((col,s))
            }
            descriptors.push(StackStep{atom:*id,table,shared,publish:vec![],frame:self.frame(c.graph,table)?});
        }
        // Each consumed neural slot is assigned once, by its first proposed parent.
        for d in &mut descriptors{
            for (col,a) in c.rule.query[d.atom].args.iter().enumerate(){
                if let Arg::Slot(s)=a && used.remove(s){d.publish.push((col,*s))}
            }
        }
        Ok((descriptors,slot_count))
    }
    fn emit_stack(&mut self,c:&Context<'_>,steps:&[StackStep],i:usize,epoch:u64,
                  path:&mut Vec<Dependency>,ports:&mut [Option<Port>],raw:&mut Vec<Vec<Dependency>>)->Result<()>{
        if i==steps.len(){
            self.counts.raw_tuples+=1;self.counts.raw_root_slots+=path.len() as u64;
            if self.detailed{
                self.raw_digest.update((self.run as u64).to_le_bytes());self.raw_digest.update((self.rule as u64).to_le_bytes());
                self.raw_digest.update((path.len() as u64).to_le_bytes());
                for (d,address) in steps.iter().zip(path.iter()){
                    self.raw_digest.update((d.atom as u64).to_le_bytes());
                    match address{
                        Dependency::Fact(f)=>{self.raw_digest.update([1]);self.raw_digest.update(f.cell.to_le_bytes());self.raw_digest.update(f.op.to_le_bytes());},
                        Dependency::Function(k)=>{self.raw_digest.update([2]);self.raw_digest.update((*k as u64).to_le_bytes());}
                    }
                }
            }
            if self.accel>=5{
                self.flat.extend(path.iter().copied().zip(self.flat_offsets.iter().copied()));
            }else{raw.push(path.clone());}
            return Ok(())
        }
        if self.trial_attempts>=self.cap{return Ok(())}
        if c.rule.seminaive && epoch.max(c.remaining[i])<c.watermark{self.counts.stale_candidates+=1;return Ok(())}
        let d=&steps[i];
        let list=if let Some(&(col,slot))=d.shared.first(){
            let idx=self.index(d.table,col,&d.frame);
            Some(self.shortlist(&d.frame,&idx,col,ports[slot].ok_or("missing parent token port")?))
        }else{None};
        let len=list.as_ref().map_or(d.frame.rows.len(),|v|v.len());
        for pos in 0..len{
            if self.trial_attempts>=self.cap{break}
            let j=list.as_ref().map_or(pos,|v|v[pos]);let row=&d.frame.rows[j];
            let now=epoch.max(row.epoch);
            if c.rule.seminaive && now.max(c.remaining[i+1])<c.watermark{continue}
            if i==0{self.counts.root_offers+=1;}else{
                self.counts.approximate_visits+=1;
                let mut hit=true;
                for &(col,slot) in d.shared.iter().skip(1){
                    let value=self.code(&row.values[col]);
                    if !self.compatible(ports[slot].ok_or("missing parent projection")?,value){hit=false;break}
                }
                if !hit{continue}
                self.counts.learned_pointers+=1;self.trial_attempts+=1;
            }
            for &(col,slot) in &d.publish{ports[slot]=Some(self.code(&row.values[col]));self.memo_counts.emitted_port_codes+=1;}
            path.push(row.witness);
            if self.accel>=5{self.flat_offsets.push(j as u32);}
            self.emit_stack(c,steps,i+1,now,path,ports,raw)?;
            path.pop();
            if self.accel>=5{self.flat_offsets.pop();}
        }
        Ok(())
    }
}

impl Store {
    fn verify_flat(&mut self,c:&Context<'_>,base:&Prefix,out:&mut Vec<Instance>)->Result<()>{
        let mut flat=std::mem::take(&mut self.flat);
        let mut frames=vec![];
        for (i,(id,_,_)) in c.inst[..c.pick_count].iter().enumerate(){
            let Call::Table(t)=c.rule.query[*id].call else{return Err("invalid sealed relation".into())};
            let f=self.frame(c.graph,t)?;
            let issued=if self.hint_fault==2 && i==0{self.issued_generations[i].wrapping_sub(1)}else{self.issued_generations[i]};
            if f.generation!=issued || f.generation!=c.graph.query_versions[t]{
                self.memo_counts.generation_rejects+=(flat.len()/c.pick_count) as u64;
                self.counts.raw_parent_rejects+=(flat.len()/c.pick_count) as u64;
                flat.clear();self.flat=flat;return Ok(())
            }
            frames.push(f);
        }
        let mut unused=vec![];
        for packet in flat.chunks_exact(c.pick_count){
            let mut exact=base.clone();let mut pass=true;
            for (i,&(address,pos)) in packet.iter().enumerate(){
                // The stable authority is the original typed dependency; an
                // untrusted offset from another row cannot substitute for it.
                let chosen=if self.hint_fault==1 && i==0{pos as usize+1}else{pos as usize};
                let Some(row)=frames[i].rows.get(chosen) else{self.memo_counts.offset_rejects+=1;pass=false;break};
                self.memo_counts.snapshot_row_reads+=1;
                if row.witness!=address{self.memo_counts.offset_rejects+=1;pass=false;break}
                if !extend(c.graph,c.rule,c.inst[i].0,row,&mut exact){pass=false;break}
            }
            if !pass{self.counts.raw_parent_rejects+=1;continue}
            self.counts.verified_parent_tuples+=1;exact.picks=c.pick_count;
            if self.detailed{exact.anchors=packet.iter().map(|r|r.0).collect();}
            self.descend(c,c.pick_count,exact,out,&mut unused)?;
        }
        flat.clear();self.flat=flat;
        Ok(())
    }
}
