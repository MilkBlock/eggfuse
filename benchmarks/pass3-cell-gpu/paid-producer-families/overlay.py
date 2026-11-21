from pathlib import Path

def edit(p,a,b):
    s=p.read_text()
    if s.count(a)!=1:raise ValueError(a)
    p.write_text(s.replace(a,b))
def install(crate):
    src=crate/'src';rt=src/'runtime.rs';st=src/'stage_spine.rs';rw=src/'joint_root.rs';pa=src/'integral_packets.rs';sg=src/'single_witness.rs'
    (src/'paid_family.rs').write_bytes((Path(__file__).parent/'grant.rs').read_bytes())
    with (src/'lib.rs').open('a') as f:f.write('\npub mod paid_family;\n')
    edit(rw,"struct Decoded{serial:u64,","struct Decoded{family:bool,serial:u64,")
    for marker in ('Some(Decoded{serial,origin,run,','Decoded{serial:state.serial,','Decoded{serial,origin:"single",run,'):
        edit(rw,marker,marker.replace('Decoded{','Decoded{family:false,'))
    edit(rw,'        if state.mode=="shadow"{return Ok(source_template);}','''        if state.mode=="shadow"{return Ok(source_template);}
        crate::paid_family::accept(r.serial,rid,r.family)?;''')
    fixed=src/'adaptive_root_page.rs'
    edit(fixed,'        Some(Decoded {','        Some(Decoded {family:w[4] as usize&crate::paid_family::FLAG!=0,')
    edit(fixed,'template: usize::try_from(w[4]).ok()?,','template: usize::try_from(w[4]).ok()? & !crate::paid_family::FLAG,')
    edit(fixed,'        let mut words = Vec::with_capacity(8 + 3 * inputs.len());','''        let template=crate::paid_family::encode(rid,template,inputs.len());
        let mut words = Vec::with_capacity(8 + 3 * inputs.len());''')
    multi=src/'multi_root_pages.rs'
    edit(multi,'        Some(Decoded {','        Some(Decoded {family:p.template&crate::paid_family::FLAG!=0,')
    edit(multi,'            template: p.template,','            template:p.template & !crate::paid_family::FLAG,')
    edit(multi,'        let invalid_version = st.mode','        let template=crate::paid_family::encode(rid,template,count);\n        let invalid_version = st.mode')
    edit(st,'    integral_anchor:Option','    paid_right:Option<crate::paid_family::Right>,\n    integral_anchor:Option')
    edit(st,'Self {integral_anchor:None,','Self {integral_anchor:None,paid_right:None,')
    edit(st,'Self::Live(Cursor {integral_anchor:None,','Self::Live(Cursor {integral_anchor:None,paid_right:None,')
    with st.open('a') as f:f.write('''
impl Started{
 pub(crate) fn paid_right_at_commit(&mut self,serial:u64,rid:usize,run:usize){
    if let Self::Live(c)=self{c.paid_right=crate::paid_family::install(serial,rid,run,c.root.id);}
 }
}
''')
    edit(rt,'        let stage_cursor = self.stage_spine.begin_step(','        let mut stage_cursor = self.stage_spine.begin_step(')
    edit(rt,'rid,serial,&mut b.values,&b.known)?;}','''rid,serial,&mut b.values,&b.known)?;
            if let Some(step)=stage_cursor.as_mut(){step.paid_right_at_commit(serial,rid,self.steps.len()+1);}
            crate::paid_family::committed(serial);}''')
    a='''                    #[cfg(feature="sparse-cells")]
                    let (root,producer,output)=match &p.base{'''
    b='''                    #[cfg(feature="sparse-cells")]
                    let deep=match &p.base{PublishedBase::Active(c)=>Some((c.root.id,c.producer,p.output,c.paid_right)),_=>None};
                    #[cfg(not(feature="sparse-cells"))]
                    let deep=(p.depth>1).then_some((p.root.id,p.producer,p.state.output,p.paid_right));
                    if let Some((root,producer,_output,right))=deep{
                        s.m.deep_ports+=1;
                        let Some(right)=crate::paid_family::route(right,root,producer,run)?else{continue};
                        if !s.roots.contains_key(&root){return Err("paid anchor lacks an original owner".into())}
                        let Some(order)=&gram else{continue};
                        let Some(row)=g.row(w)?else{continue};
                        if row.witness!=w||row.epoch!=entry.row.epoch||row.values!=entry.row.values||row.table!=entry.row.table{return Err("paid release source discrepancy".into())}
                        let before=s.m.point_reads;
                        if let Some(candidate)=crate::integral_wave::execute(g,rule,pivot,order,&row,wm,&mut s.m)?{
                            crate::paid_family::offer(producer,s.m.point_reads-before);
                            crate::integral_packets::paid_release(run,rid,pivot,w,row.epoch,candidate.epoch,&candidate.values,&candidate.refs,root,right);
                        }
                        continue;
                    }
'''+a
    edit(st,a,b)
    edit(pa,'    pub root: u64,','    pub root: u64,\n    pub right:Option<crate::paid_family::Right>,')
    edit(pa,'        let lane = Lane {','        let lane = Lane {right:None,')
    with pa.open('a') as f:f.write('''
pub(crate) fn paid_release(run:usize,rid:usize,pivot:usize,w:Dependency,version:u64,epoch:u64,values:&Slots,refs:&[(usize,Dependency)],root:u64,right:crate::paid_family::Right){
    release(run,rid,pivot,w,version,epoch,values,refs,root);
    S.with_borrow_mut(|s|{if let Some(s)=s && let Some(Some(lane))=s.collect.get_mut(&(rid,pivot)).and_then(|b|b.get_mut(&w)){lane.right=Some(right)}});
}
''')
    edit(sg,'                crate::integral_packets::issued(wire_id);','''                if let Some(right)=lane.right{
                    if right.root!=lane.root{return Err("unbound paid internal family".into())}
                    crate::paid_family::issued(wire_id,right.rule);
                }
                crate::integral_packets::issued(wire_id);''')
    ex=crate/'examples/joint_witness_session.rs'
    edit(ex,'        eggfuse_cell_runtime::integral_packets::set_partial','''        eggfuse_cell_runtime::paid_family::configure(&req["paid_families"])?;
        eggfuse_cell_runtime::integral_packets::set_partial''')
    edit(ex,'        report["integral_packets"]=','        report["paid_families"]=eggfuse_cell_runtime::paid_family::report();\n        report["integral_packets"]=')
