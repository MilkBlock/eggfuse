"""Coalesce pre-verified multi-root parent references by source rule and occurrence."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent


def rep(path,old,new):
    s=path.read_text()
    if s.count(old)!=1:raise ValueError(f'unsupported {path.name} near {old[:40]}')
    path.write_text(s.replace(old,new))


def install(crate):
    src=Path(crate)/'src'
    root=src/'joint_root.rs'
    shutil.copy2(HERE/'page.rs',src/'multi_root_pages.rs')
    with root.open('a') as f:f.write('\ninclude!("multi_root_pages.rs");\n')
    rep(root,'    Resident(Rc<Decoded>),','    Resident(Rc<Decoded>),\n    MultiPage(MultiPage,usize),')
    rep(root,'        Body::Resident(decoded)=>','        Body::MultiPage(page,slot)=>return page.decode(*slot),\n        Body::Resident(decoded)=>')
    # A page carries the same immutable, compiler-certified resident Layout identity.
    s=root.read_text();key='matches!(packet.0,Body::Resident(_))'
    if s.count(key)!=1:raise ValueError('resident layout identity check is required')
    root.write_text(s.replace(key,'matches!(packet.0,Body::Resident(_)|Body::MultiPage(..))'))
    multi=src/'ordinary_witness.rs'
    rep(multi,'struct Store {','struct Store {page:bool,page_fault:u8,page_refs:Vec<crate::joint_root::Ref>,pages:u64,paged_tuples:u64,')
    rep(multi,'let s=Store{','let s=Store{page:false,page_fault:0,page_refs:vec![],pages:0,paged_tuples:0,')
    rep(multi,'json!({"signature_stats":','json!({"pages":s.pages,"paged_tuples":s.paged_tuples,"signature_stats":')
    with multi.open('a') as f:f.write("""
pub fn set_multi_pages(fault:u8)->Result<()> {
    STORE.with_borrow_mut(|s|{
        let st=s.as_mut().ok_or("missing multi-parent provider")?;
        if st.accel!=4||!st.seal||fault>3{return Err("multi-root page requires a sealed stack".into());}
        st.page=true;st.page_fault=fault;Ok(())
    })
}
""")
    rep(src/'ordinary_shortlist.rs','            self.root_offers.push(crate::joint_root::issue("multi",c.graph.epoch,self.rule,refs));','''            if self.page{
                self.page_refs.extend(refs);
                return;
            }
            self.root_offers.push(crate::joint_root::issue("multi",c.graph.epoch,self.rule,refs));''')
    rep(multi,'            let mut no_more=vec![];', '''            let mut no_more=vec![];
            if s.page && !s.page_refs.is_empty(){
                // Publish one immutable envelope before the first exact source read.
                let page=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,
                    std::mem::take(&mut s.page_refs),s.page_fault)?;
                s.pages+=1;s.paged_tuples+=page.count() as u64;
                s.counts.peak_rule_tuples=s.counts.peak_rule_tuples.max(page.count());
                for i in 0..page.count(){
                    let parents=page.parents(i);
                    let mut exact=p.clone();
                    let mut ok=true;
                    for (j,parent) in parents.iter().enumerate(){
                        let id=c.inst[j].0;
                        let Some(row)=g.row(parent.row)? else{ok=false;break;};
                        if !extend(g,rule,id,&row,&mut exact){ok=false;break;}
                    }
                    if !ok{s.counts.raw_parent_rejects+=1;continue;}
                    s.counts.verified_parent_tuples+=1;
                    exact.picks=parents.len();
                    exact.anchors=parents.iter().map(|parent|parent.row).collect();
                    exact.root_recipe=page.recipe(i);
                    s.descend(&c,c.pick_count,exact,&mut out,&mut no_more)?;
                }
            }''')
    driver=Path(crate)/'examples/joint_witness_session.rs'
    rep(driver,'        let initial_cells =','''        if req["multi_root_pages"]==true {
            let fault=u8::try_from(req["multi_root_fault"].as_u64().unwrap_or(0))?;
            ordinary_witness::set_multi_pages(fault)?;
        }
        let initial_cells =''')
