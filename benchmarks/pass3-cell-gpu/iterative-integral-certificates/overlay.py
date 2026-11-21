from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent


def edit(s,old,new):
    if s.count(old)!=1:
        raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    src=crate/"src"
    p=src/"integral_wave.rs"
    s=p.read_text()
    s=edit(s,"struct Offer {","struct Offer {\n    prior:Option<Link>,")
    s=edit(s,"pub(crate) struct State {","pub(crate) struct State {\n    pub(crate) chain:Chain,")
    s=edit(s,".then(|| State {",".then(|| State {chain:Default::default(),")
    s=edit(s,"        answer: Candidate,","        answer: Candidate,\n        prior:Option<Link>,")
    s=edit(s,"        self.m.offers += 1;","""        self.m.offers += 1;
        self.chain.offers_by_depth[usize::from(prior.is_some())]+=1;
        let route=Chain::key(prior,[producer,op,rid,pivot]);
        self.chain.evidence.get_mut(&route).unwrap()[1]+=1;""")
    s=edit(s,"push(Offer {","push(Offer {prior,")
    s=edit(s,"Live(u64, u32, Option<(usize, Dependency, u64, usize)>),","Live(u64, u32, Option<(usize, Dependency, u64, usize)>,Option<Link>),")
    s=edit(s,"        s.m.baseline_commits += 1;","        s.m.baseline_commits += 1;s.chain.current=None;s.chain.last_route=None;")
    s=edit(s,"            Apply::Live(root, depth, anchor) =>","            Apply::Live(root, depth, anchor, prior) =>")
    s=edit(s,"                if depth != 2 {","""                if depth!=2 && !(depth==3 && s.chain.depth>=2 && prior.is_some()) {""")
    s=edit(s,"&& o.owner == root\n", "&& o.owner == root && o.prior==prior\n")
    s=edit(s,"                if o.owner != root || owner.rule != o.producer || owner.run >= run || o.inputs != *v","""                let bad=match prior {
                    None=>owner.rule!=o.producer || depth!=2,
                    Some(mut parent)=>{
                        if s.chain.bad_parent{parent.serial^=1;}
                        Some(parent)!=o.prior || !parent.authorizes(root,o.producer,depth-1,run)
                    },
                };
                if o.owner != root || bad || owner.run >= run || o.inputs != *v""")
    s=edit(s,"                owner.children += 1;", """                let edge=[o.producer,o.op,rid,o.pivot];
                let key=Chain::key(prior,edge);
                s.chain.evidence.get_mut(&key).unwrap()[2]+=1;
                s.chain.last_route=Some((root,prior.map(|p|p.serial),key.clone()));
                s.chain.winners_by_depth[usize::from(prior.is_some())]+=1;
                s.chain.current=Some(Link{root,serial,rule:rid,run,depth,first:key[0]});
                owner.children += 1;""")
    s=edit(s,'json!({"counts":s.m,"fanout":fanout','json!({"chain":s.chain.report(),"counts":s.m,"fanout":fanout')
    p.write_text(s+'\ninclude!("integral_chain.rs");\n')
    copyfile(HERE/'chain.rs',src/'integral_chain.rs')
    p=src/"integral_packets.rs";ps=p.read_text()
    ps=edit(ps,"    pub root: u64,","    pub root:u64, pub owner_proof:Option<(u64,Option<u64>,Vec<crate::integral_wave::Edge>)>,")
    ps=edit(ps,"        let lane = Lane {","        let lane = Lane {owner_proof:None,")
    ps=edit(ps,"    active: BTreeSet<u64>,","    active:BTreeSet<u64>, issued_proofs:BTreeMap<u64,(u64,Option<u64>,Vec<crate::integral_wave::Edge>)>,")
    ps=edit(ps,"            s.counts.confirmed += 1;","            s.counts.confirmed += 1; crate::integral_wave::confirmed_suppression(serial,s.issued_proofs.remove(&serial).expect(\"missing issued route proof\"));")
    ps+='\npub(crate) fn mark_offer(rid:usize,pivot:usize,w:Dependency,proof:(u64,Option<u64>,Vec<crate::integral_wave::Edge>)){S.with_borrow_mut(|s|{if let Some(s)=s && let Some(Some(lane))=s.collect.get_mut(&(rid,pivot)).and_then(|v|v.get_mut(&w)){lane.owner_proof=Some(proof)}})}\npub(crate) fn receipt(serial:u64,proof:(u64,Option<u64>,Vec<crate::integral_wave::Edge>)){S.with_borrow_mut(|s|assert!(s.as_mut().unwrap().issued_proofs.insert(serial,proof).is_none()))}\n'
    native=src/'single_witness.rs'
    native.write_text(edit(native.read_text(),"crate::integral_packets::issued(wire_id);","crate::integral_packets::receipt(wire_id,lane.owner_proof.ok_or(\"missing integral issuance path\")?);crate::integral_packets::issued(wire_id);"))
    native=src/'integral_wave.rs';native.write_text(edit(native.read_text(),"        let inputs = answer.values;","        crate::integral_packets::mark_offer(rid,pivot,answer.refs[0].1,(root,prior.map(|p|p.serial),route));\n        let inputs = answer.values;"))
    p.write_text(ps)
    p=src/'stage_spine.rs';s=p.read_text()
    s=edit(s,"    integral_anchor:Option<","    integral_proof:Option<crate::integral_wave::Link>,\n    integral_anchor:Option<")
    s=s.replace("{integral_anchor:None,","{integral_proof:None,integral_anchor:None,")
    s=edit(s,"Apply::Live(c.root.id,c.depth,c.integral_anchor)","Apply::Live(c.root.id,c.depth,c.integral_anchor,c.integral_proof)")
    start=s.index("                    #[cfg(feature=\"sparse-cells\")]\n                    let (root,producer,output)=match")
    stop=s.index("                    let Some(row)=g.row(w)?",start)
    s=s[:start]+'''                    #[cfg(feature="sparse-cells")]
                    let (root,producer,output,depth,prior)=match &p.base{
                        PublishedBase::Root(r,rid)=>(r.id,*rid,p.output,1,None),
                        PublishedBase::Solo{id,producer,..}=>(*id,*producer,p.output,1,None),
                        PublishedBase::Active(c)=>(c.root.id,c.producer,p.output,c.depth,c.integral_proof),
                    };
                    #[cfg(not(feature="sparse-cells"))]
                    let (root,producer,output,depth,prior)=(p.root.id,p.producer,p.state.output,p.depth,p.integral_proof);
                    let Some(owner)=s.roots.get(&root) else{s.m.owner_missing+=1;continue};
                    if depth==1 {
                        if owner.rule!=producer || owner.run>=run || prior.is_some(){s.m.stage_guard+=1;continue}
                    }else{
                        s.m.deep_ports+=1;
                        if depth!=2 || s.chain.depth<depth {continue;}
                        if !prior.is_some_and(|proof|proof.authorizes(root,producer,depth,run)) {
                            s.chain.missing_parent+=1;continue;
                        }
                    }
                    let Some(order)=&gram else{s.m.unsupported+=1;continue};
                    if !s.chain.admits(prior,[producer,output,rid,pivot]) {continue;}
                    s.m.anchor_reads+=1;
'''+s[stop:]
    s=edit(s,"s.offer(rid,pivot,root,producer,output,row.epoch,candidate);","s.offer(rid,pivot,root,producer,output,row.epoch,candidate,prior);")
    p.write_text(s+'''
impl Started{
    pub(crate) fn install_integral_link(&mut self, link:Option<crate::integral_wave::Link>){
        if let Self::Live(c)=self {c.integral_proof=link;}
    }
}
''')
    p=src/'runtime.rs';s=p.read_text()
    s=edit(s,"        let stage_cursor = self.stage_spine.begin_step(","        let mut stage_cursor = self.stage_spine.begin_step(")
    s=edit(s,"rid,serial,&mut b.values,&b.known)?;}","""rid,serial,&mut b.values,&b.known)?;
            if let Some(s)=stage_cursor.as_mut(){s.install_integral_link(crate::integral_wave::take_link());}
        }""")
    p.write_text(s)
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    anchor='        eggfuse_cell_runtime::integral_wave::configure(req["integral_root"].as_str().unwrap_or("off"))?;'
    p.write_text(edit(s,anchor,anchor+'\n        eggfuse_cell_runtime::integral_wave::configure_chain(&req["chain"])?;'))
