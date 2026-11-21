"""Apply certified negative masks before assigning Run lanes to private or external packets."""
from pathlib import Path

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';pk=src/'integral_packets.rs';row=src/'adaptive_rows.rs';single=src/'single_witness.rs'
    s=pk.read_text();i=s.index('pub(crate) fn certify(');j=s.index('pub(crate) fn take(',i)
    pk.write_text(s[:i]+(Path(__file__).parent/'seal.rs').read_text()+'\n'+s[j:])
    edit(pk,'    pub first_model: u64,\n    pub first_root: u64,','    pub model_ids:Vec<u64>,pub wire_ids:Vec<u64>,')
    edit(pk,'    closed_banks: u64,','    mixed_lanes:u64,mixed_banks:u64,external_in_mixed:u64,external_spans:u64,ordered_merges:u64,\n    closed_banks: u64,')
    edit(pk,'    fault: bool,','    fault: bool,partial:bool,wrong_order:bool,')
    edit(pk,'        let Some(c) = s.ready.remove(&rid) else {','        let Some(mut c) = s.ready.remove(&rid) else {')
    edit(pk,'        if c.ep != epoch || c.wm != wm || s.fault {','''        if s.wrong_order && c.wire_ids.len()>=2 {c.wire_ids.swap(0,1)}
        if c.lanes.len()!=c.wire_ids.len()||c.lanes.len()!=c.model_ids.len()||c.wire_ids.windows(2).any(|a|a[0]>=a[1])||c.model_ids.windows(2).any(|a|a[0]>=a[1]){
            return Err("integral packet lanes lost their committed source order".into())
        }
        if c.ep != epoch || c.wm != wm || s.fault {''')
    with pk.open('a') as f:f.write('''
pub fn ordering_fault(active:bool){S.with_borrow_mut(|s|{if let Some(s)=s{s.wrong_order=active}})}
pub(crate) fn merged(){S.with_borrow_mut(|s|if let Some(s)=s{s.counts.ordered_merges+=1})}
''')
    ex=crate/'examples/joint_witness_session.rs'
    edit(ex,'        eggfuse_cell_runtime::integral_wave::configure','''        eggfuse_cell_runtime::integral_packets::set_partial(req["integral_mixed"]==true);
        eggfuse_cell_runtime::integral_packets::ordering_fault(req["mixed_order_fault"]==true);
        eggfuse_cell_runtime::integral_wave::configure''')
    edit(row,'''        let closed=model.certified_inputs && self.rows.batch && !self.residual &&
            crate::integral_packets::certify(g.epoch,rid,p.pivot,sources,&scores,wm,self.serial+1,self.floors[rid])?;''','''        let mut dead=Vec::new();
        if self.rows.scalar.enabled && self.rows.batch{
            dead.reserve(sources.len());
            for (h,&score) in sources.iter().zip(&scores){
                dead.push(score>=self.floors[rid] && self.rows.scalar.rejects(g,rid,h,wm)?);
            }
        }
        let selection=if model.certified_inputs && self.rows.batch && !self.residual && width(action)==1 && g.spec_cells.is_none(){
            crate::integral_packets::certify(g.epoch,rid,p.pivot,sources,&scores,&dead,wm,self.serial+1,self.floors[rid])?
        }else{None};
        let mut internal_count=0;''')
    edit(row,'        for (h, score) in sources.iter().zip(scores) {','        for (index,(h, score)) in sources.iter().zip(scores).enumerate() {')
    edit(row,'if send && self.rows.batch && self.rows.scalar.enabled && self.rows.scalar.rejects(g,rid,h,wm)? {','if dead.get(index)==Some(&true) {')
    edit(row,'            if closed{emitted+=usize::from(send);continue}','''            if selection.as_ref().is_some_and(|s|s.internal[index]){emitted+=1;internal_count+=1;continue}''')
    edit(row,'        if self.rows.batch && !result.is_empty() {','''        if let Some(selection)=selection{
            let mut ext=0usize;
            for (internal,n) in selection.spans{
                if internal{crate::integral_packets::reserve_span(rid,n)?;continue}
                let shard=&mut result[ext..ext+n];ext+=n;
                let frozen:Vec<_>=shard.iter().map(|(t,_,_)|(t.w,t.version)).collect();
                let page=crate::joint_root::single_page(g.epoch,rid,p.pivot,&frozen).ok_or("mixed release lacked external root page")?;
                for (i,(t,_,send)) in shard.iter_mut().enumerate(){assert!(*send);t.recipe=Some(page.at(i));}
            }
            if ext!=result.len(){return Err("mixed external source span coverage".into())}
        }else if self.rows.batch && !result.is_empty() {''')
    edit(row,'        if !closed{self.rows.stats.emitted += emitted as u64;}','        self.rows.stats.emitted += (emitted-internal_count) as u64;')
    edit(single,'        if let Some((closed,audit))=crate::integral_packets::take','        let mut mixed=false;\n        if let Some((closed,audit))=crate::integral_packets::take')
    edit(single,'            if !offers.is_empty(){return Err("closed source occurrence also received external packets".into())}','            mixed=!offers.is_empty();')
    edit(single,'let local_id=closed.first_model+i as u64;','let local_id=closed.model_ids[i];')
    edit(single,'let wire_id=closed.first_root+i as u64;','let wire_id=closed.wire_ids[i];')
    edit(single,'        if let Some(t)=verification_start {','''        if mixed{
            answers.sort_unstable_by_key(|b|b.known.neural().unwrap().token.id);
            if !answers.windows(2).all(|s|s[0].known.neural().unwrap().token.id<s[1].known.neural().unwrap().token.id){
                return Err("duplicate virtual source ordinal in mixed integral release".into())
            }
            crate::integral_packets::merged();
        }
        if let Some(t)=verification_start {''')
