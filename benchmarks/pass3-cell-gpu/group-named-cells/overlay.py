from pathlib import Path
from shutil import copyfile
HERE=Path(__file__).resolve().parent


def change(source,a,b):
    if source.count(a)!=1:raise ValueError(a)
    return source.replace(a,b)


def install(crate):
    path=crate/'src/speculative_staging.rs'
    s=change(path.read_text(),'    Pooled,\n    Named,','    Pooled,\n    Named,\n    Group,')
    s=change(s,'            Some("named") => Storage::Named,','            Some("named") => Storage::Named,\n            Some("group") => Storage::Group,')
    s=change(s,'        let fault = match cfg["fault"].as_str() {','''        if self::Storage::Group==storage && !matches!(timing,Timing::Run){return Err("group vouchers require a full Run grant".into())}
        let fault = match cfg["fault"].as_str() {''')
    s=change(s,'            Some("stale") => 2,','''            Some("stale") => 2,
            Some("foreign") if storage==Storage::Group=>3,
            Some("duplicate") if storage==Storage::Group=>4,''')
    s=change(s,'fault != 0 && storage != Storage::Named','fault != 0 && !matches!(storage,Storage::Named|Storage::Group)')
    s=change(s,'staging.storage == Storage::Named','matches!(staging.storage,Storage::Named|Storage::Group)')
    a='struct Page {'
    s=change(s,a,a+'''
    voucher_epoch:u64, voucher_rule:usize, voucher_template:usize,
    offer_offset:usize, claimed: Vec<u64>,''')
    s=change(s,'struct Counts {','''struct Counts {
    group_pages:usize, authorized_lanes:usize, bitmap_bytes:usize, peak_bitmap_bytes:usize,
    redeemed:usize, redeemed_beyond_named:usize, duplicate_denials:usize, foreign_denials:usize,''')
    s=change(s,'    used_budget: usize,','    used_budget: usize,\n    bitmap_live:usize,')
    s=change(s,'            used_budget: 0,','            used_budget: 0,bitmap_live:0,')
    a='        r.pages.push(Page {'
    s=change(s,a,'''        let watch=self.storage==Storage::Group && r.span.len>0 && self.fault!=1;
        let bits=if watch{vec![0u64;n.div_ceil(64)]}else{Vec::new()};
        if watch{self.stats.group_pages+=1;self.stats.authorized_lanes+=n;}
        let bytes=bits.capacity()*std::mem::size_of::<u64>();self.bitmap_live+=bytes;
        self.stats.bitmap_bytes+=bytes;self.stats.peak_bitmap_bytes=self.stats.peak_bitmap_bytes.max(self.bitmap_live);
        r.pages.push(Page {voucher_epoch:if self.storage==Storage::Group && self.fault==2{self.epoch.wrapping_sub(1)}else{self.epoch},
            voucher_rule:rid,voucher_template:r.template,offer_offset:r.now.offers,claimed:bits,''')
    a='(granted > 0 && self.storage == Storage::Named).then_some(handle)'
    s=change(s,a,'(watch || (granted>0 && self.storage==Storage::Named)).then_some(handle)')
    a='        let slot = if self.storage == Storage::Named {'
    s=change(s,a,'''        let slot=if self.storage==Storage::Group{
            if r.span.taken>=r.span.len {
                self.stats.underforecast+=1;self.stats.fallback+=1;return None
            }
            let Some(p)=page.and_then(|i|r.pages.get_mut(i))else{
                self.stats.foreign_denials+=1;self.stats.fallback+=1;return None
            };
            let lane=match p.redeem(self.epoch,rid,template,serial,self.fault==3) {
                Ok(lane)=>lane,
                Err(failure)=>{
                    match failure {
                        GroupError::Withheld=>self.stats.missing_named+=1,
                        GroupError::Stale=>self.stats.stale_named+=1,
                        GroupError::Foreign=>self.stats.foreign_denials+=1,
                        GroupError::Duplicate=>self.stats.duplicate_denials+=1,
                    }
                    self.stats.fallback+=1;return None
                }
            };
            self.stats.redeemed+=1;
            self.stats.redeemed_beyond_named+=usize::from(p.offer_offset+lane>=r.span.len);
            if self.fault==4 {
                assert_eq!(p.redeem(self.epoch,rid,template,serial,false),Err(GroupError::Duplicate));
                self.stats.duplicate_denials+=1;
            }
            let i=r.span.start+r.span.taken;r.span.taken+=1;
            let s=&mut self.slabs[r.span.slab][i];
            assert!(s.frame.is_some(),"a group voucher cannot claim a consumed private record");
            s
        }else if self.storage == Storage::Named {''')
    s=change(s,'        self.used_budget = 0;','        self.used_budget=0;self.bitmap_live=0;')
    path.write_text(s+'\ninclude!("group_voucher.rs");\n');copyfile(HERE/'group.rs',path.with_name('group_voucher.rs'))
