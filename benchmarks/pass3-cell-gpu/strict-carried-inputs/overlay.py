from pathlib import Path
from runpy import run_path
from shutil import copyfile
HERE=Path(__file__).resolve().parent
previous=run_path(str(HERE.parent/'strict-dual-return/overlay.py'))
edit=previous['edit']

def install(crate):
    src=crate/'src'
    old_pair=(src/'incremental_raw.rs').read_bytes()
    previous['install'](crate)
    # Reuse previous issuance tag/actual fresh activation/union/ordered external-page hooks.
    # The two-parent sender is unaffected; the five-input cut lives in the general stack.
    (src/'incremental_raw.rs').write_bytes(old_pair)
    copyfile(HERE/'carried.rs',src/'dual_return.rs')
    p=crate/'examples/joint_witness_session.rs'
    edit(p,'&req["strict_dual"],&program','&req["strict_carry"],&program')
    edit(p,'report["strict_dual"]','report["strict_carry"]')
    p=src/'graph.rs'
    edit(p,'crate::dual_return::birth(self,f,t,&v);','crate::dual_return::birth(self,f,t,key);')
    p=src/'multi_root_pages.rs'
    edit(p,'p:&crate::dual_return::Pair','p:&crate::dual_return::Child')
    edit(p,'first_serial,width:2,count:1,template:layout.template','first_serial,width:p.refs.len(),count:1,template:layout.template')
    edit(p,'refs:vec![p.left.clone(),p.right.clone()]','refs:p.refs.clone()')
    p=src/'ordinary_witness.rs'
    edit(p,'dual_queue:Vec<(usize,crate::dual_return::Pair)>','carried_incoming:std::collections::VecDeque<crate::dual_return::Child>,dual_queue:Vec<(usize,crate::dual_return::Child)>')
    edit(p,'let s=Store{dual_queue:', 'let s=Store{carried_incoming:Default::default(),dual_queue:')
    a='            let (mut steps,mut slots)=s.compile_stack(&c)?;'
    edit(p,a,'''            if s.wave.preparing {
                assert!(s.carried_incoming.is_empty());
                s.carried_incoming=crate::dual_return::release(g,rid,if rule.seminaive{mark}else{0},&ins)?.into();
            }
'''+a)
    a='            let mut groups=std::mem::take(&mut s.pending_pages);'
    edit(p,a,'            s.splice_carried(None);\n'+a)
    edit(p,'crate::dual_return::minted(bank.stage_serial(),p,g.epoch);','crate::dual_return::placed(bank.stage_serial(),p,g.epoch);')
    s=src/'ordinary_shortlist.rs'
    a='        let d=&steps[i];\n        let list='
    edit(s,a,'''        if crate::dual_return::excluded(self.rule,c.graph.epoch,path){return Ok(())}
'''+a)
    a='            self.counts.raw_tuples+=1;self.counts.raw_root_slots+=path.len() as u64;'
    edit(s,a,'            if !self.carried_incoming.is_empty(){self.splice_carried(Some(path));}\n'+a)
    with s.open('a') as f:f.write('''
impl Store{
    // The child already exists before the residual matcher starts. Compare only
    // for ordering; drain even if the residual issuer produced absolutely nothing.
    fn splice_carried(&mut self, next:Option<&[Dependency]>){
        while let Some(first)=self.carried_incoming.front(){
            if let Some(next)=next{
                match first.path.as_slice().cmp(next){
                    std::cmp::Ordering::Equal=>panic!("duplicate ordinary child on protected carried prefix"),
                    std::cmp::Ordering::Greater=>break,
                    std::cmp::Ordering::Less=>{}
                }
            }
            if !self.page_refs.is_empty(){self.pending_pages.push(std::mem::take(&mut self.page_refs));}
            self.dual_queue.push((self.pending_pages.len(),self.carried_incoming.pop_front().unwrap()));
        }
    }
}
''')

    with (src/'ordinary_witness.rs').open('a') as f:f.write("""
pub fn validate_carried_profile()->Result<()>{
    STORE.with_borrow(|v|{
        let s=v.as_ref().ok_or("missing carried external issuer")?;
        if !s.packed_lookup||s.mode!="learned"||s.radius!=0||!s.seal||!s.page||s.cap!=usize::MAX||
            !s.model.q.iter().flatten().zip(s.model.k.iter().flatten()).all(|(a,b)|a.to_bits()==b.to_bits()){
            return Err("carried exclusion requires complete radius-zero source-order tied predictions".into())
        }Ok(())
    })
}
""")
    ex=crate/'examples/joint_witness_session.rs'
    anchor='        let initial_cells = runtime.graph.stats.cells_created;'
    edit(ex,anchor,'        if !req["strict_carry"].is_null(){ordinary_witness::validate_carried_profile()?;}\n'+anchor)
