// Per-source-rule snapshot cache for proof-equivalent neural prefixes and complementary guards.
#[derive(Clone, Copy, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
enum Sharing {
    Independent,
    Raw,
    Verified,
    Stale,
}
#[derive(Deserialize)]
struct PairConfig {
    pairs: Vec<[usize; 2]>,
    sharing: Sharing,
}
#[derive(Clone)]
struct Sibling {
    left: usize,
    right: usize,
    guard: usize,
    tables: Vec<usize>,
    args: [usize; 3],
}
impl Sibling {
    fn other(&self, r: usize) -> usize {
        if r == self.left {
            self.right
        } else {
            self.left
        }
    }
}
#[derive(PartialEq, Eq)]
struct Snapshot {
    run: usize,
    watermark: u64,
    versions: Vec<u64>,
}
enum Waiting {
    Raw(Vec<Vec<Dependency>>, Vec<Option<crate::joint_root::Recipe>>),
    Verified(Vec<Prefix>, usize),
}
struct PairState {
    siblings: Vec<Option<Sibling>>,
    tracked: Vec<bool>,
    mode: Sharing,
    waiting: HashMap<usize, (Snapshot, Waiting)>,
    evidence: HashMap<usize, Vec<(Dependency, (usize, u64, usize, usize, u64))>>,
    outputs: HashMap<Dependency, (usize, u64, usize, usize, u64)>,
    detailed: bool,
    examples: Vec<Json>,
    original_runs: u64,
    reused_runs: u64,
    version_misses: u64,
    raw_received: u64,
    checked_once: u64,
    comparisons: u64,
    first: u64,
    second: u64,
    neither: u64,
    published: u64,
    source_reads: u64,
    hit_tickets: u64,
    committed: u64,
    cross_stage: u64,
    per_rule: BTreeMap<usize, [u64; 2]>,
}
thread_local! {static PAIRS: RefCell<Option<PairState>>=const{RefCell::new(None)};}
pub fn configure_pairs(program: &Program, config: Option<&[u8]>, detail: bool) -> Result<()> {
    let Some(cfg) = config else {
        PAIRS.with_borrow_mut(|s| *s = None);
        return Ok(());
    };
    let cfg: PairConfig = serde_json::from_slice(cfg).map_err(|e| e.to_string())?;
    let mut siblings = vec![None; program.rules.len()];
    let mut tracked = vec![false; program.tables.len()];
    STORE.with_borrow(|store|->Result<()>{
        let s=store.as_ref().ok_or("pair study requires a loaded policy")?;
        if s.accel!=4 || !s.seal{return Err("pair study requires stack sealing".into());}
        for [left,right] in cfg.pairs{
            let a=program.rules.get(left).ok_or("invalid pair rule")?;
            let b=program.rules.get(right).ok_or("invalid pair rule")?;
            let pa=s.plans[left].as_ref().ok_or("missing left neural plan")?;
            let pb=s.plans[right].as_ref().ok_or("missing right neural plan")?;
            if pa.ins!=pb.ins || pa.width!=pb.width || !a.seminaive || !b.seminaive || a.inputs!=b.inputs || a.query.len()!=b.query.len() ||
                program.sets.values().any(|rs|rs.contains(&left)!=rs.contains(&right)){return Err("pair signatures differ".into());}
            let mut tables=vec![];let mut guard=None;
            for (k,(i,pick,_)) in pa.ins.iter().enumerate(){
                let aa=&a.query[*i];let bb=&b.query[*i];
                if aa.args!=bb.args{return Err("pair wiring differs".into());}
                match (&aa.call,&bb.call){
                    (Call::Table(t),Call::Table(u)) if t==u && *pick==1=>{tables.push(*t);tracked[*t]=true;}
                    (Call::Primitive(o,ot),Call::Primitive(q,qt)) if k+1==pa.ins.len() && *pick==0 && o=="<" && q==">" && ot=="Unit" && qt==ot=>{
                        let [Arg::Slot(x),Arg::Slot(y),Arg::Slot(z)]=aa.args.as_slice()else{return Err("unsupported branch operands".into());};
                        // Both table fields are signed i64, and the fresh Unit result is unique.
                        for source_slot in [x,y]{
                            if !a.query.iter().any(|atom|matches!(atom.call,Call::Table(t) if atom.args.iter().enumerate().any(|(col,v)|matches!(v,Arg::Slot(s) if s==source_slot) && program.tables[t].schema[col]["name"]=="i64"))){return Err("non-i64 comparator".into());}
                        }
                        if a.query.iter().any(|atom|matches!(atom.call,Call::Table(_))&&atom.args.contains(&Arg::Slot(*z))){return Err("guard binds existing slot".into());}
                        guard=Some((*i,[*x,*y,*z]));
                    }
                    _=>return Err("unproved sibling guard".into())
                }
            }
            let (guard,args)=guard.ok_or("missing opposite conditions")?;
            if siblings[left].is_some()||siblings[right].is_some(){return Err("duplicate sibling".into());}
            let family=Sibling{left,right,guard,args,tables};siblings[left]=Some(family.clone());siblings[right]=Some(family);
        }Ok(())
    })?;
    PAIRS.with_borrow_mut(|s| {
        *s = Some(PairState {
            siblings,
            tracked,
            mode: cfg.sharing,
            waiting: HashMap::new(),
            evidence: HashMap::new(),
            outputs: HashMap::new(),
            detailed: detail,
            examples: vec![],
            original_runs: 0,
            reused_runs: 0,
            version_misses: 0,
            raw_received: 0,
            checked_once: 0,
            comparisons: 0,
            first: 0,
            second: 0,
            neither: 0,
            published: 0,
            source_reads: 0,
            hit_tickets: 0,
            committed: 0,
            cross_stage: 0,
            per_rule: BTreeMap::new(),
        })
    });
    Ok(())
}
pub(crate) fn publish_pair(g: &Graph, table: usize, effect: usize, address: Dependency) {
    PAIRS.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else { return };
        if !s.detailed || !s.tracked[table] {
            return;
        }
        s.outputs.remove(&address);
        if let Some((ordinal, rid)) = crate::joint_root::current_parent() {
            if let Some(epoch) = g.visible_epoch(address) {
                s.outputs
                    .insert(address, (ordinal, g.epoch, rid, effect, epoch));
                s.published += 1;
            }
        }
    })
}
fn pair_start(
    g: &Graph,
    rule: usize,
    run: usize,
    wm: u64,
) -> Option<(Sibling, Sharing, Snapshot, Option<Waiting>)> {
    PAIRS.with_borrow_mut(|state| {
        let s = state.as_mut()?;
        let fam = s.siblings[rule].clone()?;
        let stamp = Snapshot {
            run,
            watermark: wm,
            versions: fam.tables.iter().map(|t| g.query_versions[*t]).collect(),
        };
        let saved = s.waiting.remove(&rule).and_then(|(old, pending)| {
            if old == stamp && s.mode != Sharing::Stale {
                s.reused_runs += 1;
                match &pending {
                    Waiting::Verified(rows, raw) => {
                        s.raw_received += *raw as u64;
                        s.checked_once += rows.len() as u64;
                    }
                    Waiting::Raw(rows, _) => s.raw_received += rows.len() as u64,
                };
                Some(pending)
            } else {
                s.version_misses += 1;
                None
            }
        });
        if saved.is_none() {
            s.original_runs += 1;
        }
        Some((fam, s.mode, stamp, saved))
    })
}
fn pair_store(rid: usize, stamp: Snapshot, value: Waiting) {
    PAIRS.with_borrow_mut(|s| {
        s.as_mut().unwrap().waiting.insert(rid, (stamp, value));
    });
}
fn pair_project(f: &Sibling, p: &mut Prefix) -> Result<Option<usize>> {
    let (Some(Value::Int(x)), Some(Value::Int(y))) =
        (p.slots.get(&f.args[0]), p.slots.get(&f.args[1]))
    else {
        return Err("missing branch inputs".into());
    };
    let arm = if x < y {
        Some(f.left)
    } else if x > y {
        Some(f.right)
    } else {
        None
    };
    PAIRS.with_borrow_mut(|s| {
        let s = s.as_mut().unwrap();
        s.comparisons += 1;
        match arm {
            Some(n) if n == f.left => s.first += 1,
            Some(_) => s.second += 1,
            None => s.neither += 1,
        };
    });
    if arm.is_some() {
        p.slots.insert(f.args[2], Value::Int(0));
    }
    Ok(arm)
}
fn pair_origins(g: &Graph, rule: usize, id: usize, witness: &[Dependency]) {
    PAIRS.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else { return };
        if !s.detailed || s.siblings[rule].is_none() {
            return;
        }
        let parents = witness
            .iter()
            .filter_map(|w| {
                s.outputs
                    .get(w)
                    .filter(|v| v.1 < g.epoch && g.visible_epoch(*w) == Some(v.4))
                    .map(|p| (*w, *p))
            })
            .collect();
        s.evidence.insert(id, parents);
    })
}
fn pair_confirm(id: usize, ordinal: usize, t: &Ticket) {
    PAIRS.with_borrow_mut(|state| {
        let Some(s) = state.as_mut() else { return };
        if s.siblings[t.rule].is_none() {
            return;
        }
        s.committed += 1;
        let parent = s.evidence.remove(&id).unwrap_or_default();
        let cross = !parent.is_empty();
        if cross {
            s.cross_stage += 1;
        }
        let count = s.per_rule.entry(t.rule).or_default();
        count[0] += 1;
        count[1] += u64::from(cross);
        if s.detailed {
            s.examples
                .push(json!([t.run, t.rule, ordinal, id, t.anchors, parent]));
        }
    })
}
pub fn pairs_report() -> Json {
    PAIRS.with_borrow(|s|s.as_ref().map_or(Json::Null,|s|json!({
    "first_visits":s.original_runs,"reused_sibling_runs":s.reused_runs,"snapshot_misses":s.version_misses,
    "shared_raw_tuples":s.raw_received,"shared_verified_tuples":s.checked_once,"published_source_ports":s.published,
    "comparisons":s.comparisons,"lt":s.first,"gt":s.second,"eq":s.neither,"committed":s.committed,"cross_stage":s.cross_stage,
    "per_rule":s.per_rule,"commits":s.examples})))
}
