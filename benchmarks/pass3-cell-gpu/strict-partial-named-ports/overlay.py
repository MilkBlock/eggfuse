from pathlib import Path
from shutil import copyfile
def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src';state=src/'strict_named.rs';ad=src/'adaptive_rows.rs';single=src/'single_witness.rs';pack=src/'integral_packets.rs'
    copyfile(Path(__file__).parent/'partial.rs',src/'strict_partial.rs')
    with single.open('a') as f:f.write('\ninclude!("strict_partial.rs");\n')
    edit(state,'struct State {','''struct State {partial:bool,stale_versions:bool,
        partitions:BTreeMap<usize,BTreeSet<Dependency>>, cost:PartitionCost,''')
    edit(state,'State {record_links:spec["record_links"]==true,','''State {record_links:spec["record_links"]==true,partial:spec["partial"]==true,stale_versions:spec["stale_versions"]==true,''')
    edit(state,'                s.closed_rules.clear();','                s.closed_rules.clear();s.partitions.clear();')
    edit(state,'        if n == 0 || ports.len() < n {','        if n == 0 || (!s.partial && ports.len() < n) {')
    edit(state,'            if row.epoch < wm {','''            if s.stale_versions && row.epoch!=(o.version^1){s.cost.stale_refs+=1;continue}
            if row.epoch < wm {''')
    edit(state,'        if live != n || ready.is_empty() {','        if (!s.partial && live!=n) || ready.is_empty() {')
    edit(state,'        s.stats.complete_banks += 1;\n        s.closed_rules.insert(rid);','''        if live==n{s.stats.complete_banks+=1;s.closed_rules.insert(rid);}
        else{
            assert!(s.partial);s.partitions.insert(rid,headers.iter().map(|&(w,_)|w).collect());
        }''')
    edit(state,'json!({"links":s.links,','json!({"partition":s.cost,"links":s.links,')
    with state.open('a') as f:f.write('''
#[derive(Default,serde::Serialize)]
struct PartitionCost{mixed_calls:u64,mixed_with_external:u64,residual_bank_rows:u64,excluded_metadata_rows:u64,
    signed_children:u64,residual_scored:u64,child_logits_for_audit:u64,production_virtual:u64,external_spans:u64,
    mixed_internal_spine_checks:u64,mixed_external_spine_checks:u64,stale_refs:u64}
pub(crate) fn partitioned(rid:usize)->bool{S.with_borrow(|v|v.as_ref().is_some_and(|s|s.partitions.contains_key(&rid)))}
pub(crate) fn spine_partition_point(rid:usize,w:Dependency){
 S.with_borrow_mut(|v|if let Some(s)=v{if let Some(part)=s.partitions.get(&rid){
    if part.contains(&w){s.cost.mixed_internal_spine_checks+=1}else{s.cost.mixed_external_spine_checks+=1}
 }else{s.stats.direct_spine_lookups+=1}})
}
pub(crate) fn record_partition(bank:usize,excluded:usize,signed:usize,ext:usize,blocks:usize,trace:bool){
 S.with_borrow_mut(|v|{let c=&mut v.as_mut().unwrap().cost;c.mixed_calls+=1;c.mixed_with_external+=u64::from(ext!=0);
    c.residual_bank_rows+=bank as u64;c.excluded_metadata_rows+=excluded as u64;c.signed_children+=signed as u64;
    c.residual_scored+=ext as u64;c.external_spans+=blocks as u64;
    if trace{c.child_logits_for_audit+=signed as u64}else{c.production_virtual+=signed as u64}
 })
}
''')
    edit(ad,'        if let Some(h)=&signed{','''        let mixed=signed.is_some() && crate::strict_named::partitioned(rid);
        if let Some(h)=signed.as_ref().filter(|_|!mixed){''')
    edit(ad,'let sources:&[SourceHeader]=if let Some(h)=&signed{','let sources:&[SourceHeader]=if let Some(h)=signed.as_ref().filter(|_|!mixed){')
    edit(ad,'let can_prefilter = signed.is_none() &&','let can_prefilter = (mixed||signed.is_none()) &&')
    edit(ad,'if signed.is_none() && self.rows.signature_budget','if (mixed||signed.is_none()) && self.rows.signature_budget')
    edit(ad,'        let n = sources.len();\n        let input = RowInput {','''        if mixed{return self.emit_strict_partial(g,rid,wm,p,base,sources,signed.as_ref().unwrap())}
        let n = sources.len();
        let input = RowInput {''')
    edit(pack,'pub(crate) struct Closed {','pub(crate) struct Closed {\n    pub positions:Option<(Vec<u64>,Vec<u64>)>,')
    edit(pack,'                    Closed {','                    Closed {positions:None,')
    edit(pack,'Closed{pivot:0,first_model,first_root','Closed{positions:None,pivot:0,first_model,first_root')
    edit(pack,'struct Counts {','struct Counts {\n    mixed_banks:u64,mixed_lanes:u64,')
    with pack.open('a') as f:f.write('''
pub(crate) fn strict_mixed_seal(epoch:u64,rid:usize,wm:u64,ids:Vec<u64>,wire:Vec<u64>,audit_score:f32)->Result<()>{
 S.with_borrow_mut(|v|{let s=v.as_mut().ok_or("missing strict partial receiver")?;
    let bank=s.collect.remove(&(rid,0)).ok_or("no independently signed partial inputs")?;
    if bank.len()!=ids.len()||wire.len()!=ids.len()||ids.windows(2).any(|x|x[0]>=x[1])||wire.windows(2).any(|x|x[0]>=x[1]){
        return Err("strict partial release order or cardinality".into())
    }
    let lanes=bank.into_values().collect::<Option<Vec<_>>>().ok_or("ambiguous strict owner")?;
    s.counts.mixed_banks+=1;s.counts.mixed_lanes+=lanes.len() as u64;s.counts.peak_bank=s.counts.peak_bank.max(lanes.len());
    *s.closed_rules.entry(rid).or_default()+=lanes.len() as u64;
    assert!(s.ready.insert(rid,Closed{positions:Some((ids,wire)),pivot:0,first_model:0,first_root:0,scores:[0.,audit_score],lanes,ep:epoch,wm}).is_none());Ok(())
 })
}
''')
    edit(single,'        if let Some((closed,audit))=crate::integral_packets::take','        let mut mixed=false;\n        if let Some((closed,audit))=crate::integral_packets::take')
    edit(single,'            if !offers.is_empty(){return Err("closed source occurrence also received external packets".into())}','''            mixed=closed.positions.is_some();
            if !mixed && !offers.is_empty(){return Err("closed source occurrence also received external packets".into())}''')
    edit(single,'let local_id=closed.first_model+i as u64;','let local_id=closed.positions.as_ref().map_or(closed.first_model+i as u64,|x|x.0[i]);')
    edit(single,'let wire_id=closed.first_root+i as u64;','let wire_id=closed.positions.as_ref().map_or(closed.first_root+i as u64,|x|x.1[i]);')
    edit(single,'        if let Some(t)=verification_start {','''        if mixed{
            answers.sort_unstable_by_key(|b|b.known.neural().expect("strict mixed origin").token.id);
            if !answers.windows(2).all(|b| b[0].known.neural().unwrap().token.id<b[1].known.neural().unwrap().token.id){
                return Err("duplicate strict partial binding".into())
            }
        }
        if let Some(t)=verification_start {''')
    stage=src/'stage_spine.rs'
    edit(stage,'        if crate::strict_named::closed(rid){','        if crate::strict_named::closed(rid)||crate::strict_named::partitioned(rid){')
    edit(stage,'                    crate::strict_named::spine_point();','                    crate::strict_named::spine_partition_point(rid,w);')
    edit(single,'crate::strict_named::link(closed.first_root+i as u64,lane.root,rid,lane.w)?;', '''crate::strict_named::link(closed.positions.as_ref().map_or(closed.first_root+i as u64,|x|x.1[i]),lane.root,rid,lane.w)?;''')
    edit(state,'struct Owner {','struct Owner {audit_ports:Option<std::rc::Rc<Vec<[u64;4]>>>,')
    edit(state,'struct Permit {','struct Permit {audit_ports:Option<std::rc::Rc<Vec<[u64;4]>>>,')
    edit(state,'    record_links:bool, links:Vec<[u64;3]>,','    record_links:bool, links:Vec<[u64;3]>,path_links:Vec<J>,')
    edit(state,'                prior: internal.path,','                prior: internal.path,audit_ports:internal.audit_ports,')
    edit(state,'                prior: vec![],','                prior: vec![],audit_ports:None,')
    edit(state,'            let owner = Owner {','''            let audit_ports=if s.record_links{
                let mut trail=a.audit_ports.as_ref().map_or_else(Vec::new,|v|v.as_ref().clone());
                trail.push([f.cell as u64,f.op as u64,epoch,a.run as u64]);Some(std::rc::Rc::new(trail))
            }else{None};
            let owner = Owner {audit_ports,''')
    edit(state,'s.links.push([serial,internal.root,internal.path.len() as u64]);','''s.links.push([serial,internal.root,internal.path.len() as u64]);
                let trace=internal.audit_ports.as_ref().ok_or("missing signed audit coordinates")?;
                s.path_links.push(json!([serial,internal.root,internal.path,trace.as_slice(),s.run]));''')
    edit(state,'json!({"partition":s.cost,','json!({"signed_commits":s.path_links,"partition":s.cost,')
