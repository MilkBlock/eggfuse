"""Record genuine verifier entry versus already sealed page offers and private reservations."""
from pathlib import Path


def rep(s,a,b):
    if s.count(a)!=1:raise ValueError(a)
    return s.replace(a,b)


def install(crate):
    src=crate/'src'
    if 'fn spec_verifier_entry(' in (src/'speculative_staging.rs').read_text():
        return
    p=src/'ordinary_witness.rs';s=p.read_text()
    a='                for page in pages{'
    p.write_text(rep(s,a,a+'\n                if page.count()>0 {g.spec_verifier_entry();}'))
    p=src/'single_witness.rs';s=p.read_text()
    a='        let verification_start=self.rows.profile.then(std::time::Instant::now);'
    p.write_text(rep(s,a,a+'\n        if !offers.is_empty(){g.spec_verifier_entry();}'))
    p=src/'speculative_staging.rs';s=p.read_text()
    a='struct Counts {'
    s=rep(s,a,a+'''
    nonempty_wave_runs:usize,
    complete_before_verify_runs:usize,
    offers_before_first_verify:usize,
    offers_after_first_verify:usize,
    slots_before_first_verify:usize,
    slots_after_first_verify:usize,
    max_before_first_verify:usize,''')
    s=rep(s,'    seen: usize,','    seen: usize,\n    issued_this_run:usize,\n    first_verify:Option<(usize,usize)>,')
    s=rep(s,'            seen: 0,','            seen: 0,issued_this_run:0,first_verify:None,')
    s=rep(s,'        self.stats.offers += n;','        self.stats.offers += n;self.issued_this_run+=n;')
    a='        self.stats.unused += self.used_budget - self.seen;'
    s=rep(s,a,'''        let (before,allocated)=self.first_verify.take().unwrap_or((self.issued_this_run,self.used_budget));
        self.stats.offers_before_first_verify+=before;
        self.stats.offers_after_first_verify+=self.issued_this_run-before;
        self.stats.slots_before_first_verify+=allocated;
        self.stats.slots_after_first_verify+=self.used_budget-allocated;
        if self.issued_this_run>0{
            self.stats.nonempty_wave_runs+=1;
            self.stats.complete_before_verify_runs+=usize::from(before==self.issued_this_run);
            self.stats.max_before_first_verify=self.stats.max_before_first_verify.max(before);
        }
        self.issued_this_run=0;
'''+a)
    p.write_text(s+'''
impl Graph {
    pub(crate) fn spec_verifier_entry(&self){
        if let Some(s)=&self.spec_cells{
            let mut state=s.borrow_mut();
            if state.first_verify.is_none(){state.first_verify=Some((state.issued_this_run,state.used_budget));}
        }
    }
}
''')
