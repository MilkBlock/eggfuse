// Diagnostic only. This module cannot skip the native union or its subscribers.
use crate::{
    graph::{Dependency, Graph},
    joint_root::Ref,
    program::{Arg, Call, Op, Program, Result},
    value::{Value, root},
};
use rustc_hash::FxHashMap;
use serde::Serialize;
use serde_json::{Value as J, json};
use std::{
    cell::RefCell,
    collections::{BTreeMap, VecDeque},
};

#[derive(Clone, Serialize)]
struct Operand {
    slot: Option<usize>,
    local: Option<usize>,
    literal: Option<u64>,
    columns: Vec<(usize, usize)>,
}
#[derive(Clone, Serialize)]
struct Site {
    op: usize,
    sides: [Operand; 2],
}
fn operand(arg: &Arg, prior: &[Op], p: &Program, rid: usize) -> Operand {
    let rule = &p.rules[rid];
    let mut input = arg;
    for op in prior.iter().rev() {
        if let Arg::Slot(i) = input {
            match op {
                Op::Copy(dst, next) if i == dst => input = next,
                Op::Let(dst, ..) if i == dst => {
                    return Operand {
                        slot: None,
                        local: match op {
                            Op::Let(_, Call::Table(t), _) if p.tables[*t].constructor => Some(*dst),
                            _ => None,
                        },
                        literal: None,
                        columns: vec![],
                    };
                }
                _ => (),
            }
        }
    }
    let slot = match input {
        Arg::Slot(i) if rule.inputs.contains(i) => Some(*i),
        _ => None,
    };
    let literal = match input {
        Arg::Literal(Value::Eq(i)) => Some(*i),
        _ => None,
    };
    let mut columns = vec![];
    if let Some(s) = slot {
        for (a, atom) in rule
            .query
            .iter()
            .enumerate()
            .filter(|(_, a)| matches!(a.call, Call::Table(_)))
        {
            for (col, arg) in atom.args.iter().enumerate() {
                if matches!(arg,Arg::Slot(i) if *i==s) {
                    columns.push((a, col));
                }
            }
        }
    }
    Operand {
        slot,
        local: None,
        literal,
        columns,
    }
}
#[derive(Clone, Copy, Serialize)]
struct Word {
    role: usize,
    atom: usize,
    column: usize,
    address: Dependency,
    version: u64,
    id: u64,
}
#[derive(Clone)]
struct Claim {
    points: [Option<PointWord>; 2],
    local: [Option<usize>; 2],
    direct_side: usize,
    run: u64,
    rid: usize,
    serial: u64,
    op: usize,
    words: [Option<Word>; 2],
    value: [Option<u64>; 2],
    feature: [u8; 12],
    selected: bool,
    side: usize,
    tie: u64,
    score: f64,
}
#[derive(Clone)]
struct Cause {
    kind: &'static str,
    template: usize,
    cell: u32,
    op: usize,
}
struct Pending {
    raw: (u64, u64),
    cause: Cause,
    claim: Option<Claim>,
    inputs: [Option<u64>; 2],
    ordinal: usize,
}
#[derive(Default, Serialize)]
struct OriginStats {
    attempts: u64,
    effective: u64,
    reader_visits: u64,
}
#[derive(Default, Serialize)]
struct Bucket {
    either_valid: [u64; 2],
    either_readers: [u64; 2],
    parent_only_valid: u64,
    parent_only_readers: u64,
    local_pair_valid: u64,
    local_pair_known: u64,
    offers: u64,
    admissible: u64,
    selected: u64,
    reached: u64,
    effective: u64,
    readers: u64,
    both_effective: u64,
    pair_valid: u64,
    displaced_valid: u64,
    displaced_raw: u64,
    valid_readers: u64,
    selected_valid: u64,
    selected_readers: u64,
}
#[derive(Default, Serialize)]
struct Totals {
    point_rechecks: u64,
    point_recheck_ns: u64,
    point_stale: u64,
    point_requests: u64,
    point_results: u64,
    point_fields: u64,
    point_ns: u64,
    point_reuses: u64,
    point_key_extra_rows: u64,
    point_validated_sides: u64,
    union_hash: u64,
    proposed_roots: u64,
    choices: u64,
    source_reads: u64,
    committed_roots: u64,
    issued_sites: u64,
    matched_explicit: u64,
    committed_input_pair: u64,
    committed_pair_valid: u64,
    parent_pair_known: u64,
    parent_pair_valid: u64,
    parent_single_known: u64,
    no_parent_known: u64,
    attempts: u64,
    effective: u64,
    readers: u64,
    discarded_equal: u64,
}
struct State {
    use_points: bool,
    sample_by_site: BTreeMap<(usize, usize), J>,
    point_by_site: BTreeMap<(usize, usize), [u64; 8]>,
    plans: Vec<Vec<Site>>,
    templates: Vec<usize>,
    source_hash: String,
    mode: String,
    corrupt: bool,
    weights: Vec<f64>,
    percent: usize,
    global_cut: Option<(i64, f64)>,
    priors: BTreeMap<(usize, usize), f64>,
    fallback: f64,
    offers: FxHashMap<(u64, usize), Claim>,
    epoch: u64,
    candidates: Vec<Claim>,
    active: Option<(usize, u64, usize, BTreeMap<usize, [Option<u64>; 2]>)>,
    next: Option<Cause>,
    reader_stack: Vec<usize>,
    queue: VecDeque<Pending>,
    by: BTreeMap<&'static str, OriginStats>,
    buckets: BTreeMap<[u8; 12], Bucket>,
    counts: Totals,
    by_origin_example: BTreeMap<&'static str, J>,
    examples: Vec<J>,
    site_counts: BTreeMap<(usize, usize), [u64; 7]>,
}
thread_local! {static STATE:RefCell<Option<State>>=RefCell::new(None);}
pub fn configure(g: &Graph, v: &J) -> Result<()> {
    if v.is_null() {
        STATE.with_borrow_mut(|s| *s = None);
        return Ok(());
    }
    let mode = v["mode"].as_str().ok_or("missing union claim mode")?;
    if !matches!(
        mode,
        "all" | "uniform" | "static" | "model" | "local-first" | "baked-sites"
    ) {
        return Err("invalid union claim policy".into());
    }
    let percent = v["percent"].as_u64().unwrap_or(100);
    if percent == 0 || percent > 100 {
        return Err("invalid union claim budget".into());
    }
    let weights: Vec<f64> = serde_json::from_value(v["weights"].clone()).unwrap_or_default();
    if mode == "model" && (weights.len() != 26 || weights.iter().any(|x| !x.is_finite())) {
        return Err("invalid union gate weights".into());
    }
    let global_cut = if let Some(c) = v.get("global_cut") {
        let t = c["rank"].as_i64().ok_or("invalid rank threshold")?;
        let p = c["tie"]
            .as_f64()
            .filter(|v| (0.0..=1.0).contains(v))
            .ok_or("invalid tie probability")?;
        Some((t, p))
    } else {
        None
    };
    let mut priors = BTreeMap::new();
    if mode == "baked-sites" {
        let data: Vec<(usize, usize, f64)> =
            serde_json::from_value(v["sites"].clone()).map_err(|e| e.to_string())?;
        for (r, op, x) in data {
            if !x.is_finite() || priors.insert((r, op), x).is_some() {
                return Err("invalid frozen site rate".into());
            }
        }
    }
    let fallback = v["default_score"].as_f64().unwrap_or(0.);
    let plans = g
        .program
        .rules
        .iter()
        .enumerate()
        .map(|(rid, r)| {
            let ops = &g.program.templates[r.template].ops;
            ops.iter()
                .enumerate()
                .filter_map(|(op, i)| match i {
                    Op::Union(a, b) => Some(Site {
                        op,
                        sides: [
                            operand(a, &ops[..op], &g.program, rid),
                            operand(b, &ops[..op], &g.program, rid),
                        ],
                    }),
                    _ => None,
                })
                .collect()
        })
        .collect();
    let templates = g.program.rules.iter().map(|r| r.template).collect();
    let mut s = State {
        use_points: v["point"] == true,
        sample_by_site: BTreeMap::new(),
        point_by_site: BTreeMap::new(),
        source_hash: g.program.artifact["sha256"].as_str().unwrap_or("").into(),
        plans,
        templates,
        mode: mode.into(),
        corrupt: v["corrupt"] == true,
        weights,
        percent: percent as usize,
        global_cut,
        priors,
        fallback,
        offers: Default::default(),
        epoch: 0,
        candidates: vec![],
        active: None,
        next: None,
        reader_stack: vec![],
        queue: Default::default(),
        by: Default::default(),
        buckets: Default::default(),
        counts: Default::default(),
        by_origin_example: BTreeMap::new(),
        examples: vec![],
        site_counts: Default::default(),
    };
    for pair in &g.pending_unions {
        s.queue.push_back(Pending {
            raw: *pair,
            cause: generic("initial"),
            claim: None,
            inputs: [None, None],
            ordinal: 0,
        });
    }
    STATE.with_borrow_mut(|st| *st = Some(s));
    Ok(())
}
fn generic(kind: &'static str) -> Cause {
    Cause {
        kind,
        cell: 0,
        template: 0,
        op: 0,
    }
}
pub(crate) fn interested(rid: usize) -> bool {
    STATE.with_borrow(|s| {
        s.as_ref()
            .is_some_and(|s| s.plans.get(rid).is_some_and(|x| !x.is_empty()))
    })
}
fn mixed(mut x: u64) -> u64 {
    x ^= x >> 30;
    x = x.wrapping_mul(0xbf58476d1ce4e5b9);
    x ^= x >> 27;
    x.wrapping_mul(0x94d049bb133111eb) ^ (x >> 31)
}
fn group(value: usize) -> u8 {
    (value.saturating_add(1).ilog2()).min(15) as u8
}
pub(crate) fn offer(g: &Graph, rid: usize, serial: u64, refs: &[Ref]) -> Result<()> {
    STATE.with_borrow_mut(|state|{
        let Some(s)=state else{return Ok(())};
        if s.epoch!=g.epoch{s.offers.clear();s.epoch=g.epoch;}
        s.counts.proposed_roots+=1;
        let mut resolved=Vec::with_capacity(refs.len());resolved.resize_with(refs.len(),||None);
        let mut point_cache=Vec::new();
        for site in &s.plans[rid]{
            let mut words=[None;2];let mut value=[None;2];let mut points=[None;2];
            for (i,part) in site.sides.iter().enumerate(){
                value[i]=part.literal;
                for &(a,col) in &part.columns {
                    let Some(role)=refs.iter().position(|r|r.atom==a) else{continue};
                    let rf=&refs[role];
                    if resolved[role].is_none(){resolved[role]=Some(g.row(rf.row)?);s.counts.source_reads+=1;}
                    if let Some(row)=resolved[role].as_ref().unwrap() && row.epoch==rf.version && !row.hidden && row.witness==rf.row
                        && matches!(g.program.rules[rid].query[a].call,Call::Table(t) if row.table==t)
                        && let Some(Value::Eq(id))=row.values.get(col){
                        value[i]=Some(*id);words[i]=Some(Word{role,atom:a,column:col,address:rf.row,version:rf.version,id:*id});break;
                    }
                }
            }
            if s.use_points{
                let initial=[s.counts.point_requests,s.counts.point_results,s.counts.point_ns,s.counts.point_key_extra_rows];
                for (i,part) in site.sides.iter().enumerate(){
                    if value[i].is_none() && part.slot.is_some(){
                        points[i]=one_request(g,rid,refs,part,&mut resolved,&mut point_cache,&mut s.counts)?;
                    }
                }
                let current=[s.counts.point_requests,s.counts.point_results,s.counts.point_ns,s.counts.point_key_extra_rows];
                let costs=s.point_by_site.entry((rid,site.op)).or_default();
                for i in 0..4{costs[i]+=current[i]-initial[i];}
            }
            let cmp=|a:Option<u64>,b:Option<u64>|usize::from(match(a,b){
                (Some(x),Some(y))=>x<y,(None,Some(_))=>true,_=>false
            });
            let current=value.map(|x|x.map(|v|root(&g.parents,v)));
            let direct_side=cmp(current[0],current[1]);
            let known:[Option<u64>;2]=std::array::from_fn(|i|value[i].or_else(||points[i].map(|p|p.id)));
            let [l,r]=known;
            let left=l.map(|v|root(&g.parents,v));let right=r.map(|v|root(&g.parents,v));
            let local=[site.sides[0].local,site.sides[1].local];
            let cand=[l.is_some()||local[0].is_some(),r.is_some()||local[1].is_some()];
            let mut side=match(local[0],local[1]){
                (Some(a),Some(b))=>usize::from(a<b),(Some(_),None)=>0,(None,Some(_))=>1,(None,None)=>cmp(left,right)
            };
            let fresh=refs.iter().any(|v|v.version==g.epoch);
            let f=[u8::from(l.is_some()),u8::from(r.is_some()),u8::from(left.is_some()&&left==right),
                u8::from(left.zip(right).is_some_and(|(a,b)|a>b)),u8::from(fresh),group(g.program.rules[rid].query.len()),
                group(site.op),group(refs.len()),group(s.plans[rid].len()),u8::from(words[0].zip(words[1]).is_some_and(|(a,b)|a.role==b.role)),u8::from(local[0].is_some()),u8::from(local[1].is_some())];
            let tie=mixed(serial.wrapping_mul(37).wrapping_add(site.op as u64).wrapping_add(17));
            let score=match s.mode.as_str(){
                "static"=>f[0] as f64+f[1] as f64+0.5*f64::from(f[10]+f[11]),
                "local-first"=>2.*f64::from(u8::from(f[10]+f[11]>0))+0.5*f64::from(f[0]+f[1]),
                "baked-sites"=>s.priors.get(&(rid,site.op)).copied().unwrap_or(s.fallback),
                "model"=>{
                    let score=|i:usize|if !cand[i]{f64::NEG_INFINITY}else{
                        s.weights[i*13+12]+s.weights[i*13..i*13+12].iter().zip(&f).map(|(w,v)|w*f64::from(*v)).sum::<f64>()
                    };
                    let a=score(0);let b=score(1);side=if a==b {side}else{usize::from(b>a)};a.max(b)
                },_=>0.,
            };
            s.buckets.entry(f).or_default().offers+=1;s.counts.issued_sites+=1;
            s.site_counts.entry((rid,site.op)).or_default()[0]+=1;
            if s.corrupt {for side in 0..2{if cand[side]{value[side]=Some(u64::MAX-serial);}}}
            s.candidates.push(Claim{points,local,direct_side,run:g.epoch,rid,serial,op:site.op,words,value,feature:f,selected:false,side,tie,score});
        }
        Ok(())
    })
}
pub(crate) fn seal() {
    STATE.with_borrow_mut(|state| {
        let Some(s) = state else { return };
        let mut valid: Vec<usize> = s
            .candidates
            .iter()
            .enumerate()
            .filter_map(|(i, c)| {
                let f = c.feature;
                if f[2] != 0 {
                    s.counts.discarded_equal += 1;
                }
                ((c.value[c.side].is_some()
                    || c.local[c.side].is_some()
                    || c.points[c.side].is_some())
                    && f[2] == 0)
                    .then_some(i)
            })
            .collect();
        valid.sort_unstable_by(|&a, &b| {
            s.candidates[b]
                .score
                .total_cmp(&s.candidates[a].score)
                .then(s.candidates[a].tie.cmp(&s.candidates[b].tie))
                .then(a.cmp(&b))
        });
        let n = if s.mode == "all" {
            valid.len()
        } else {
            (valid.len() * s.percent).div_ceil(100)
        };
        for (rank, i) in valid.into_iter().enumerate() {
            let c = &mut s.candidates[i];
            s.buckets.entry(c.feature).or_default().admissible += 1;
            s.site_counts.entry((c.rid, c.op)).or_default()[5] += 1;
            c.selected = if let Some((threshold, tie)) = s.global_cut {
                let key = (c.score * 1e6 + 0.5).floor() as i64;
                key > threshold
                    || (key == threshold && (((c.tie >> 11) as f64) / (1u64 << 53) as f64) < tie)
            } else {
                rank < n
            };
            if c.selected {
                s.buckets.entry(c.feature).or_default().selected += 1;
                s.counts.choices += 1;
            }
        }
        for c in s.candidates.drain(..) {
            s.offers.insert((c.serial, c.op), c);
        }
    });
}
pub(crate) fn committed(rule: usize, serial: u64, ordinal: usize, inputs: &crate::slots::Slots) {
    STATE.with_borrow_mut(|st| {
        let Some(s) = st else { return };
        let mut f = BTreeMap::new();
        for p in &s.plans[rule] {
            let vals = p.sides.clone().map(|o| {
                o.literal.or_else(|| match inputs.get(&o.slot?) {
                    Some(Value::Eq(v)) => Some(*v),
                    _ => None,
                })
            });
            f.insert(p.op, vals);
        }
        s.active = Some((rule, serial, ordinal, f));
        s.counts.committed_roots += 1;
    })
}
pub(crate) fn end_root() {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.active = None;
        }
    });
}
pub(crate) fn explicit(cell: u32, template: usize, op: usize) {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.next = Some(Cause {
                kind: "explicit",
                template,
                cell,
                op,
            });
        }
    })
}
pub(crate) fn tag(kind: &'static str) {
    STATE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.next = Some(generic(kind));
        }
    });
}
pub(crate) fn queued(a: u64, b: u64) {
    STATE.with_borrow_mut(|st| {
        let Some(s) = st else { return };
        let cause = s.next.take().unwrap_or_else(|| generic("other"));
        let (mut claim, mut inputs, mut ordinal) = (None, [None, None], 0);
        if cause.kind == "explicit"
            && let Some((rid, serial, ord, by_op)) = &s.active
            && s.templates[*rid] == cause.template
        {
            claim = s.offers.get(&(*serial, cause.op)).cloned();
            inputs = by_op.get(&cause.op).copied().unwrap_or([None, None]);
            ordinal = *ord;
        }
        s.queue.push_back(Pending {
            raw: (a, b),
            cause,
            claim,
            inputs,
            ordinal,
        });
    })
}
pub(crate) fn before(g: &Graph, raw: (u64, u64), roots: (u64, u64), readers: usize) -> Result<()> {
    STATE.with_borrow_mut(|st|{let Some(s)=st else{return Ok(())};
        let p=s.queue.pop_front().ok_or("union commit lacks enqueue record")?;
        if p.raw!=raw{return Err("union queue order mismatch".into())}
        let (a,b)=roots;let effective=a!=b;let hi=a.max(b);let lo=a.min(b);
        if effective {
            s.reader_stack.push(readers);
            s.by_origin_example.entry(p.cause.kind).or_insert_with(||json!({"epoch":g.epoch,"raw":raw,"displaced":hi,"kept":lo,
                "reader_count":readers,"cell":p.cause.cell,"op":p.cause.op,"template":p.cause.template}));
        }
        let stats=s.by.entry(p.cause.kind).or_default();stats.attempts+=1;stats.effective+=u64::from(effective);
        stats.reader_visits+=readers as u64;
        s.counts.attempts+=1;s.counts.effective+=u64::from(effective);if effective {for v in [hi,lo]{s.counts.union_hash=(s.counts.union_hash^v).wrapping_mul(1099511628211);}}s.counts.readers+=readers as u64;
        let checked=p.inputs.map(|x|x.map(|v|root(&g.parents,v)));
        if effective && checked[0].is_some()&&checked[1].is_some(){s.counts.committed_input_pair+=1;s.counts.committed_pair_valid+=u64::from(checked==[Some(a),Some(b)]);}
        let Some(c)=p.claim else{return Ok(())};
        if p.cause.kind!="explicit" || c.op!=p.cause.op{return Err("wrong union claim origin".into())}
        s.counts.matched_explicit+=1;
        let count=s.buckets.entry(c.feature).or_default();count.reached+=1;s.site_counts.entry((c.rid,c.op)).or_default()[1]+=1;
        if !effective{return Ok(())}
        count.effective+=1;count.readers+=readers as u64;
        let got=c.value.map(|x|x.map(|v|root(&g.parents,v)));
        let known=usize::from(got[0].is_some())+usize::from(got[1].is_some());
        if known==2{s.counts.parent_pair_known+=1;count.both_effective+=1;if got==[Some(a),Some(b)]{count.pair_valid+=1;s.counts.parent_pair_valid+=1;}}
        else if known==1{s.counts.parent_single_known+=1}else{s.counts.no_parent_known+=1}
        let direct=c.feature[2]==0 && got[c.direct_side]==Some(hi)&&roots_array(roots)[c.direct_side]==hi;
        if direct{count.parent_only_valid+=1;count.parent_only_readers+=readers as u64;}
        let expanded=std::array::from_fn::<_,2,_>(|i|c.value[i].or_else(||c.points[i].map(|p|p.id)).or_else(|| c.local[i].and_then(|slot|{
            let suffix=u32::try_from(slot).ok()?.checked_add(1)?;
            Some((u64::from(p.cause.cell)<<32)|u64::from(suffix))
        })));
        let resolved=expanded.map(|v|v.map(|x|root(&g.parents,x)));
        let mut point_ok=[true;2];
        let initial=[s.counts.point_rechecks,s.counts.point_stale,s.counts.point_recheck_ns];
        for (i,w) in c.points.iter().enumerate(){
            if let Some(w)=w {
                let timer=std::time::Instant::now();
                let Call::Table(t)=g.program.rules[c.rid].query[w.atom].call else{return Err("invalid union request atom".into())};
                let keys=w.keys.iter().flatten().map(|x|match x{ScalarKey::Eq(v)=>Value::Eq(*v),ScalarKey::Int(v)=>Value::Int(*v)}).collect::<Vec<_>>();
                let found=g.lookup(t,&keys)?.filter(|r|!r.hidden && r.table==t && r.witness==w.address && r.epoch==w.version);
                point_ok[i]=found.is_some_and(|r|matches!(r.values.get(w.column),Some(Value::Eq(v)) if root(&g.parents,*v)==root(&g.parents,w.id)));
                s.counts.point_rechecks+=1;
                s.counts.point_stale+=u64::from(!point_ok[i]);s.counts.point_recheck_ns+=timer.elapsed().as_nanos()as u64;
            }
        }
        if s.use_points{
            let current=[s.counts.point_rechecks,s.counts.point_stale,s.counts.point_recheck_ns];
            let costs=s.point_by_site.entry((c.rid,c.op)).or_default();
            for i in 0..3{costs[i+4]+=current[i]-initial[i];}
        }
        if resolved[0].is_some() && resolved[1].is_some(){
            count.local_pair_known+=1;count.local_pair_valid+=u64::from(resolved==[Some(a),Some(b)] && point_ok==[true,true]);
        }
        let valid=[0,1].map(|i|point_ok[i] && c.feature[2]==0 && resolved[i]==Some(hi) && roots_array(roots)[i]==hi);
        for i in 0..2{if valid[i]{count.either_valid[i]+=1;count.either_readers[i]+=readers as u64;}}
        let ok=valid[c.side];
        let raw_ok=ok && expanded[c.side]==Some(hi);
        if ok && c.points[c.side].is_some(){s.counts.point_validated_sides+=1;s.point_by_site.entry((c.rid,c.op)).or_default()[7]+=1;}
        if ok{count.displaced_valid+=1;count.valid_readers+=readers as u64;}
        if raw_ok{count.displaced_raw+=1;}
        if c.selected && ok {count.selected_valid+=1;count.selected_readers+=readers as u64;}
        s.sample_by_site.entry((c.rid,c.op)).or_insert_with(||json!({"run":c.run,"rule":c.rid,"op":c.op,"cell":p.cause.cell,
            "serial":c.serial,"ordinal":p.ordinal,"words":c.words,"local_slots":c.local,"requested":c.points,"queued":raw,
            "current":[a,b],"displaced":hi,"survivor":lo,"selected_side":c.side,"correct_displaced":ok,"readers":readers}));
        let q=s.site_counts.entry((c.rid,c.op)).or_default();q[2]+=1;q[3]+=u64::from(ok);q[4]+=readers as u64;if ok{q[6]+=readers as u64;}
        let typ=(known,usize::from(c.local[0].is_some())+usize::from(c.local[1].is_some()),ok);
        let category=((typ.0*3+typ.1)*2+usize::from(typ.2)) as u64;
        if s.examples.iter().all(|e|e["category"].as_u64()!=Some(category)) {
            s.examples.push(json!({"category":category,"run":c.run,"rule":c.rid,"template":p.cause.template,"cell":p.cause.cell,"op":c.op,"serial":c.serial,
                "ordinal":p.ordinal,"words":c.words,"issued":c.value,"local_slots":c.local,"requested":c.points,"resolved":resolved,"selected_side":c.side,"verified_inputs":p.inputs,"queued":raw,"current":[a,b],
                "displaced":hi,"survivor":lo,"correct_displaced":ok,"selected":c.selected,"reverse_readers":readers}));
        }
        Ok(())
    })
}
fn roots_array(v: (u64, u64)) -> [u64; 2] {
    [v.0, v.1]
}
pub fn finish() -> Result<J> {
    STATE.with_borrow(|st|{let Some(s)=st else{return Ok(J::Null)};if !s.queue.is_empty()||!s.reader_stack.is_empty(){return Err("uncommitted union diagnostic queue".into())}
        Ok(json!({"sources":s.source_hash,"mode":s.mode,"totals":s.counts,"origins":s.by,
            "features":s.buckets.iter().collect::<Vec<_>>(),"sites":s.site_counts.iter().collect::<Vec<_>>(),
            "examples":s.examples,"point_by_site":s.point_by_site.iter().collect::<Vec<_>>(),"origin_examples":s.by_origin_example,"site_examples":s.sample_by_site.iter().collect::<Vec<_>>(),"static_rules":s.plans.len(),"static_sites":s.plans.iter().enumerate().filter(|(_,p)|!p.is_empty()).map(|(i,p)|(i,s.templates[i],p)).collect::<Vec<_>>()}))
    })
}

pub(crate) fn original_reader_count(actual: usize) -> Result<()> {
    STATE.with_borrow_mut(|st| {
        let Some(s) = st else { return Ok(()) };
        if s.reader_stack.pop() != Some(actual) {
            return Err("original displaced reader count changed".into());
        }
        Ok(())
    })
}

pub(crate) fn enabled() -> bool {
    STATE.with_borrow(|s| s.is_some())
}

#[derive(Clone, Copy, Serialize)]
enum ScalarKey {
    Eq(u64),
    Int(i64),
}

#[derive(Clone, Copy, Serialize)]
struct PointWord {
    keys: [Option<ScalarKey>; 4],
    atom: usize,
    column: usize,
    address: Dependency,
    version: u64,
    id: u64,
}

fn one_request(
    g: &Graph,
    rid: usize,
    refs: &[Ref],
    part: &Operand,
    rows: &mut [Option<Option<crate::graph::Row>>],
    cache: &mut Vec<(usize, Option<PointWord>)>,
    counts: &mut Totals,
) -> Result<Option<PointWord>> {
    let query = &g.program.rules[rid].query;
    for &(atom, col) in &part.columns {
        let target = &query[atom];
        let Call::Table(table) = target.call else {
            continue;
        };
        if col > 4 || col + 1 != target.args.len() {
            continue;
        }
        if let Some((_, answer)) = cache.iter().find(|(a, _)| *a == atom) {
            counts.point_reuses += 1;
            return Ok(*answer);
        }
        let start = std::time::Instant::now();
        let mut args = Vec::new();
        for key in &target.args[..col] {
            let value = match key {
                Arg::Literal(v) => Some(crate::value::canon(v, &g.parents)),
                Arg::Slot(s) => {
                    let mut value = None;
                    for (role, rf) in refs.iter().enumerate() {
                        let Some(source) = query.get(rf.atom) else {
                            continue;
                        };
                        let Call::Table(t) = source.call else {
                            continue;
                        };
                        let Some(field) = source
                            .args
                            .iter()
                            .position(|a| matches!(a,Arg::Slot(k) if k==s))
                        else {
                            continue;
                        };
                        if rows[role].is_none() {
                            rows[role] = Some(g.row(rf.row)?);
                            counts.source_reads += 1;
                            counts.point_key_extra_rows += 1;
                        }
                        if let Some(r) = rows[role].as_ref().unwrap()
                            && r.table == t
                            && !r.hidden
                            && r.witness == rf.row
                            && r.epoch == rf.version
                        {
                            value = r.values.get(field).cloned();
                            if value.is_some() {
                                break;
                            }
                        }
                    }
                    value
                }
            };
            let Some(v) = value else { break };
            args.push(v);
        }
        if args.len() != col {
            counts.point_ns += start.elapsed().as_nanos() as u64;
            continue;
        }
        let mut key_words = [None; 4];
        let mut scalar = true;
        for (i, v) in args.iter().enumerate() {
            key_words[i] = match v {
                Value::Eq(v) => Some(ScalarKey::Eq(*v)),
                Value::Int(v) => Some(ScalarKey::Int(*v)),
                _ => {
                    scalar = false;
                    None
                }
            };
        }
        if !scalar {
            counts.point_ns += start.elapsed().as_nanos() as u64;
            continue;
        }
        counts.point_requests += 1;
        counts.point_fields += args.len() as u64;
        let answer = g.lookup(table, &args)?.and_then(|r| {
            if r.hidden || r.table != table {
                return None;
            }
            let Value::Eq(id) = r.values.get(col)? else {
                return None;
            };
            Some(PointWord {
                keys: key_words,
                atom,
                column: col,
                address: r.witness,
                version: r.epoch,
                id: *id,
            })
        });
        counts.point_ns += start.elapsed().as_nanos() as u64;
        counts.point_results += u64::from(answer.is_some());
        cache.push((atom, answer));
        return Ok(answer);
    }
    Ok(None)
}
