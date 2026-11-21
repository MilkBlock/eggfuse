"""Compile exact unary-function freshness/absence checks into the live singleton issuer."""
from pathlib import Path

def edit(path,a,b):
    s=path.read_text()
    if s.count(a)!=1:raise ValueError(a)
    path.write_text(s.replace(a,b))

def install(crate):
    src=crate/'src'
    (src/'scalar_certificates.rs').write_bytes((Path(__file__).parent/'certificate.rs').read_bytes())
    row=src/'adaptive_rows.rs';single=src/'single_witness.rs'
    edit(row,'struct RowEngine {','struct RowEngine {\n    scalar:ScalarProofs,')
    edit(row,'        self.rows.active = true;', '''        self.rows.scalar.enabled=spec["scalar_certificates"]==true;
        self.rows.scalar.audit=audit;
        self.rows.active = true;''')
    edit(row,'        let base=if g.header_mode','''        if self.rows.scalar.enabled && self.rows.scalar.plans.is_empty(){
            self.rows.scalar.plans=self.plans.iter().enumerate().map(|(id,p)|p.as_ref().and_then(|p|ScalarPlan::compile(g,&g.program.rules[id],p))).collect();
            self.rows.scalar.counts.resize_with(self.plans.len(),Default::default);
        }
        let base=if g.header_mode''')
    edit(row,'        let mut emitted = 0;', '        let mut emitted = 0;\n        let mut omitted=0usize;')
    edit(row,'            let recipe = if send && !self.rows.batch {','''            if send && self.rows.batch && self.rows.scalar.enabled && self.rows.scalar.rejects(g,rid,h,wm)? {
                omitted+=1;
                if self.rows.scalar.audit{self.rows.scalar.skipped.entry(rid).or_default().push(Token {
                    recipe:None,id:self.serial,rid,w:h.source,version:h.version,initial:h.initial,score,guarded:false
                });}
                continue
            }
            let recipe = if send && !self.rows.batch {''')
    edit(row,'Ok((result, emitted, fresh_total, n))','Ok((result, emitted+omitted, fresh_total, n))')
    edit(row,'json!({"stats":self.stats,','json!({"scalar_certificates":self.scalar.counts,"stats":self.stats,')
    edit(single,'        let verification_start=self.rows.profile', '''        if let Some(omitted)=self.rows.scalar.skipped.remove(&rid){
            let saved=self.work;
            for token in omitted{
                if self.check(g,r,&p,&token,wm)?.is_some(){return Err(format!("valid single token omitted by scalar key proof: rule {rid}"))}
                self.rows.scalar.counts[rid].audited+=1;
            }
            self.work=saved;
        }
        let verification_start=self.rows.profile''')
    with single.open('a') as out:out.write('\ninclude!("scalar_certificates.rs");\n')
    with (src/'graph.rs').open('a') as out:out.write('''
impl Graph{
    pub(crate) fn single_scalar_epoch(&self,t:usize,value:&Value)->Result<Option<u64>>{
        debug_assert!(!self.program.tables[t].virtual_fact);
        let key=[crate::value::canon(value,&self.parents)];
        if self.port_keys_enabled(t){
            return Ok(self.lookup_canonical(t,&key)?.filter(|r|!r.hidden).map(|r|r.epoch))
        }
        Ok(self.function_index(t,&key).and_then(|i|self.functions.get(i)).filter(|f|f.live).map(|f|f.epoch))
    }
}
''')
