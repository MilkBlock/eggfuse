"""Close independent immutable pages without introducing a source-check feedback edge."""
from pathlib import Path

def change(s,old,new):
    if s.count(old)!=1:raise ValueError(old)
    return s.replace(old,new)


def install(crate):
    p=crate/'src/ordinary_witness.rs';s=p.read_text()
    s=change(s,'struct Store {','struct Store {page_tuples:usize,pending_pages:Vec<Vec<crate::joint_root::Ref>>,max_sealed_page:usize,')
    s=change(s,'let s=Store{','let s=Store{page_tuples:0,pending_pages:Vec::new(),max_sealed_page:0,')
    s=change(s,'"tier":s.tier.stats,','"max_sealed_page":s.max_sealed_page,"tier":s.tier.stats,')
    begin=s.index('            if s.page && !s.page_refs.is_empty(){')
    loop=s.index('                for i in 0..page.count(){',begin)
    end=s.index('            }\n            let stack_recipes=',loop)
    verify=s[loop:end]
    s=s[:begin]+'''            if s.page && (!s.pending_pages.is_empty() || !s.page_refs.is_empty()){
                if !s.page_refs.is_empty(){let tail=std::mem::take(&mut s.page_refs);s.pending_pages.push(tail);}
                // All physical source addresses are sealed before any exact parent check.
                let mut pages=Vec::with_capacity(s.pending_pages.len());
                let mut total=0;
                for refs in std::mem::take(&mut s.pending_pages){
                    let page=crate::joint_root::multi_page(g.epoch,rid,c.pick_count,refs,s.page_fault)?;
                    total+=page.count();s.max_sealed_page=s.max_sealed_page.max(page.count());
                    pages.push(page);
                }
                s.pages+=pages.len() as u64;s.paged_tuples+=total as u64;
                s.counts.peak_rule_tuples=s.counts.peak_rule_tuples.max(total);
                for page in pages{
'''+verify+'                }\n'+s[end:]
    s+='''
pub fn configure_generation_pages(n:usize)->Result<()>{
    STORE.with_borrow_mut(|state|{
        let s=state.as_mut().ok_or("generation pages need an active proposer")?;
        if !s.page || !s.seal || s.accel!=4 || n==0{return Err("invalid multi-parent generation page size".into());}
        s.page_tuples=n;Ok(())
    })
}
'''
    p.write_text(s)
    p=crate/'src/ordinary_shortlist.rs';s=p.read_text()
    anchor='                self.page_refs.extend(refs);'
    p.write_text(change(s,anchor,anchor+'''
                if self.page_tuples>0 && self.page_refs.len()/steps.len()>=self.page_tuples{
                    self.pending_pages.push(std::mem::take(&mut self.page_refs));
                }'''))
    p=crate/'examples/joint_witness_session.rs';s=p.read_text()
    marker='        let initial_cells = runtime.graph.stats.cells_created;'
    p.write_text(change(s,marker,'''        if let Some(n)=req["multi_page_tuples"].as_u64(){
            ordinary_witness::configure_generation_pages(usize::try_from(n)?)?;
        }
'''+marker))
