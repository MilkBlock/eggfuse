// A diagnostic tape never contains query slots, point results, graph rows, RHS
// values or graph mutations. Only the accepted-only arm sees the outcome mask.
use crate::{graph::Dependency, joint_root::Ref, program::Result};
use serde_json::{Value, json};
use std::{cell::RefCell, rc::Rc};

type Site = (u64, usize, u64);
#[derive(Clone)]
pub(crate) struct SingleRef {
    pub id: u64,
    pub w: Option<Dependency>,
    pub epoch: u64,
    pub initial: bool,
    pub score: f32,
    pub guarded: bool,
    pub features: [u8; 14],
    pub send: bool,
}
#[derive(Default)]
pub(crate) struct Singles {
    site: Site,
    pub rows: Vec<SingleRef>,
    pub yes: rustc_hash::FxHashSet<u64>,
    pub emitted: usize,
    pub total: f32,
    pub n: usize,
}
#[derive(Default)]
pub(crate) struct Multis {
    site: Site,
    pub all: Vec<Vec<Ref>>,
    pub yes: Vec<Ref>,
}
#[derive(Default)]
struct Tape {
    mode: u8,
    single: Vec<Rc<Singles>>,
    multi: Vec<Rc<Multis>>,
    sc: usize,
    mc: usize,
    ready: bool,
}
thread_local! {static T:RefCell<Tape>=RefCell::default();}
pub fn begin(name: &str) -> Result<()> {
    T.with_borrow_mut(|t| {
        t.sc = 0;
        t.mc = 0;
        t.mode = match name {
            "live" => 0,
            "capture" => 1,
            "all" => 2,
            "positive" => 3,
            "single" => 4,
            "multi" => 5,
            "site-fault" => 6,
            "version-fault" => 7,
            _ => return Err("unknown oracle mode".into()),
        };
        if t.mode == 1 {
            t.single.clear();
            t.multi.clear();
            t.ready = false;
        }
        if t.mode > 1 && !t.ready {
            return Err("no completed donor capture".into());
        }
        Ok(())
    })
}
pub(crate) fn capturing() -> bool {
    T.with_borrow(|t| t.mode == 1)
}
pub(crate) fn singles(site: Site) -> Result<Option<(Rc<Singles>, bool)>> {
    T.with_borrow_mut(|t| {
        if !matches!(t.mode, 2 | 3 | 4 | 6 | 7) {
            return Ok(None);
        }
        let b = t.single.get(t.sc).ok_or("oracle single site missing")?;
        if b.site != site || (t.mode == 6 && t.sc == 0) {
            return Err("oracle single source site mismatch".into());
        }
        t.sc += 1;
        Ok(Some((b.clone(), t.mode != 2)))
    })
}
pub(crate) fn save_single(site: Site, rows: Vec<SingleRef>, emitted: usize, total: f32, n: usize) {
    T.with_borrow_mut(|t| {
        t.single.push(Rc::new(Singles {
            site,
            rows,
            emitted,
            total,
            n,
            yes: Default::default(),
        }))
    });
}
pub(crate) fn single_success(id: u64) {
    T.with_borrow_mut(|t| {
        if t.mode == 1 {
            Rc::get_mut(t.single.last_mut().unwrap())
                .unwrap()
                .yes
                .insert(id);
        }
    })
}
pub(crate) fn multis(site: Site) -> Result<Option<(Rc<Multis>, bool)>> {
    T.with_borrow_mut(|t| {
        if t.mode == 1 {
            t.multi.push(Rc::new(Multis {
                site,
                ..Default::default()
            }));
            return Ok(None);
        }
        if !matches!(t.mode, 2 | 3 | 5 | 6 | 7) {
            return Ok(None);
        }
        let b = t.multi.get(t.mc).ok_or("oracle multi site missing")?;
        if b.site != site {
            return Err("oracle multi source site mismatch".into());
        }
        t.mc += 1;
        Ok(Some((b.clone(), t.mode != 2)))
    })
}
pub(crate) fn multi_page(refs: &[Ref]) {
    T.with_borrow_mut(|t| {
        if t.mode == 1 {
            Rc::get_mut(t.multi.last_mut().unwrap())
                .unwrap()
                .all
                .push(refs.to_owned());
        }
    })
}
pub(crate) fn multi_success(refs: &[Ref]) {
    T.with_borrow_mut(|t| {
        if t.mode == 1 {
            Rc::get_mut(t.multi.last_mut().unwrap())
                .unwrap()
                .yes
                .extend_from_slice(refs);
        }
    })
}
pub fn finish() -> Result<Value> {
    T.with_borrow_mut(|t|{
        if t.mode==1 {t.ready=true;}
        let sr=matches!(t.mode,2|3|4|6);let mr=matches!(t.mode,2|3|5|6);
        if (sr && t.sc!=t.single.len()) || (mr && t.mc!=t.multi.len()){return Err("unconsumed oracle sites".into())}
        Ok(json!({"source":"retrospective issued parent addresses","single_replayed":sr,"multi_replayed":mr,
            "single_sites":t.sc,"multi_sites":t.mc,"captured_single_sites":t.single.len(),"captured_multi_sites":t.multi.len(),
            "single_sent":t.single.iter().map(|b|b.emitted).sum::<usize>(),
            "single_accepted":t.single.iter().map(|b|b.yes.len()).sum::<usize>(),
            "all_multi_refs":t.multi.iter().flat_map(|b|b.all.iter()).map(Vec::len).sum::<usize>(),
            "accepted_multi_refs":t.multi.iter().map(|b|b.yes.len()).sum::<usize>()}))
    })
}

pub(crate) fn version_fault() -> bool {
    T.with_borrow(|t| t.mode == 7)
}
