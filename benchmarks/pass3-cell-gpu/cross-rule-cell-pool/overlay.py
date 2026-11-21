from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent

def change(source, old, new):
    if source.count(old)!=1:raise ValueError(old)
    return source.replace(old,new)

def install(crate):
    src=crate/'src'
    p=src/'joint_root.rs'
    p.write_text(p.read_text()+'\npub(crate) fn seals_required()->bool{STATE.with_borrow(|c|c.as_ref().is_some_and(|s|s.redemption!=0))}\n')
    p=src/'speculative_staging.rs';s=p.read_text()
    s=change(s,'struct RuleRecord {','struct RuleRecord {\n    pool_id:usize,')
    s=change(s,'pub(crate) struct Staging {','pub(crate) struct Staging {\n    pool:Pool,')
    s=change(s,'        Ok(Self {\n            timing,','''        if storage!=Storage::Group || !matches!(timing,Timing::Run){return Err("cross-pool benchmark needs Run/group".into())}
        let (shared,layout_fault)=match cfg["cross_pool"].as_str(){
            Some("shared")=>(true,false),Some("per-rule")=>(false,false),Some("bad-layout")=>(true,true),
            _=>return Err("select cross_pool mode".into())};
        Ok(Self { pool:Pool{shared,fault:layout_fault,..Default::default()},
            timing,''')
    s=change(s,'                RuleRecord {','                RuleRecord {pool_id:self.order.len(),')
    s=change(s,'                start += n;','''                let rec=&self.rules[&rid];
                self.pool.add(rid,rec,g.program.templates[rec.template].ops.len().clamp(1,4));
                start += n;''')
    s=change(s,'let watch=self.storage==Storage::Group && r.span.len>0 && self.fault!=1;',
             '''self.pool.records[r.pool_id].issued+=n;
        let class=self.pool.records[r.pool_id].class;
        let watch=self.storage==Storage::Group && !self.pool.buckets[class].is_empty() && self.fault!=1;''')
    s=change(s,'''            if r.span.taken>=r.span.len {
                self.stats.underforecast+=1;self.stats.fallback+=1;return None
            }''','''            let Some(donor)=self.pool.available(r.pool_id) else{
                self.stats.underforecast+=1;self.stats.fallback+=1;return None
            };
            let from=&self.pool.records[donor];let to=&self.pool.records[r.pool_id];
            let offset=from.start+from.taken;
            let frame=self.slabs[r.span.slab][offset].frame.as_ref().expect("unclaimed donor");
            let expected=if self.pool.fault && donor!=r.pool_id {(to.class+1)%4}else{to.class};
            if !pristine(frame,from,expected,self.epoch) {
                self.pool.counts.rejected_layout+=1;self.stats.fallback+=1;return None
            }
            assert!(crate::joint_root::seals_required(),"cross-pool requires original sealed parent");''')
    s=change(s,'let i=r.span.start+r.span.taken;r.span.taken+=1;', 'let i=self.pool.reserve(r.pool_id,donor);')
    s=change(s,'            assert!(s.frame.is_some(),"a group voucher cannot claim a consumed private record");','''            // Only the authenticated consumer above can bind the pristine private header.
            s.frame.as_mut().unwrap().template=template;''')
    s=change(s,"let capture = matches!(policy, Policy::Capture)","let capture = audit || matches!(policy, Policy::Capture)")
    s=change(s,'Some("duplicate") if storage==Storage::Group=>4,','Some("duplicate") if storage==Storage::Group=>4, Some("other-rule") if storage==Storage::Group=>5,')
    s=change(s,'p.redeem(self.epoch,rid,template,serial,self.fault==3)', 'p.redeem(self.epoch,if self.fault==5{rid.wrapping_add(1)}else{rid},template,serial,self.fault==3)')
    s=change(s,'        let history = self','        self.pool.finish(&self.rules);\n        let history = self')
    s=change(s,'json!({"counts":self.stats,"samples":','json!({"pool":self.pool.counts,"counts":self.stats,"samples":')
    p.write_text(s+'\ninclude!("cross_pool.rs");\n');copyfile(HERE/'pool.rs',src/'cross_pool.rs')
