// The unresolved directory owns a single allocation until one authentic CPU
// reply can move it to the concrete publication directory or retire it.
use std::time::Instant;
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
struct HigherHandle {
    root: u64,
    generation: u64,
}
#[derive(Clone)]
enum FieldInput {
    Column(usize),
    Constant(SetValue),
}
struct HigherOwner {
    handle: HigherHandle,
    address: usize,
    issue_run: usize,
    source_epoch: u64,
    inputs: Vec<(Dependency, u64)>,
    first: Option<(FactRef, u64)>,
    first_result: Option<SetValue>,
    invalid_operands: bool,
    fields: Vec<SetValue>,
    middle: Option<(u64, usize)>,
    result: Option<PublishedSet>,
    inbox: bool,
    expected_reply_run: Option<usize>,
    existing: bool,
}
#[derive(Clone)]
enum Reply {
    StaleInput,
    Fresh(PublishedSet),
    NoFirst,
    Existing,
    NoSet,
    Aborted,
    Expired,
}
#[derive(Default, Serialize)]
struct HigherCounts {
    encoded: u64,
    requests: u64,
    queued_requests: u64,
    request_batches: u64,
    request_reads: u64,
    peak_requests: usize,
    request_ns: u64,
    named_inputs: u64,
    prepared: u64,
    middles: u64,
    operand_transfers: u64,
    operand_fields: u64,
    operand_guard_reads: u64,
    operand_fallbacks: u64,
    direct_operand_ns: u64,
    fresh_replies: u64,
    existing_replies: u64,
    no_first_replies: u64,
    no_set_replies: u64,
    expired: u64,
    aborted: u64,
    batches: u64,
    replies: u64,
    transferred: u64,
    stable_address: u64,
    retired_no_result: u64,
    retired_stale: u64,
    retired_fresh: u64,
    stale_replies: u64,
    duplicate_replies: u64,
    lookup_checks: u64,
    terminal_commits: u64,
    peak_pending: usize,
    peak_specialized: usize,
    peak_batch: usize,
    peak_capacity_bytes: usize,
    capture_ns: u64,
    setup_ns: u64,
    response_ns: u64,
    validation_ns: u64,
    direct_publication_ns: u64,
    teardown_ns: u64,
}
#[derive(Default)]
struct HigherState {
    enabled: bool,
    profile: bool,
    fault: String,
    generation: u64,
    alias_slot: usize,
    projection: Vec<FieldInput>,
    pending: BTreeMap<u64, Box<HigherOwner>>,
    specialized: BTreeMap<u64, Box<HigherOwner>>,
    retired: BTreeMap<u64, u64>,
    inbox: Vec<(HigherHandle, usize, Reply)>,
    request_queue: Vec<HigherHandle>,
    stats: HigherCounts,
    events: Vec<J>,
}
pub fn higher_capabilities() -> J {
    json!({"schema":"eggfuse-ripsat-higher-cell/v1","request":"resolve-constructor-set","branches":["fresh","no-new-fact","stale"],"batch":"post-run"})
}
fn configure_higher(spec: &J, g: &Graph, s: &mut State) -> Result<()> {
    s.higher.profile = spec["higher_profile"] == true;
    let cfg = &spec["higher_cell"];
    if cfg.is_null() {
        return Ok(());
    }
    for (key, val) in higher_capabilities().as_object().unwrap() {
        if &cfg[key] != val {
            return Err("incorrect higher Cell protocol".into());
        }
    }
    let p = s
        .set_plan
        .as_ref()
        .ok_or("higher Cell requires an authorized Set publication")?;
    if cfg["target_sha256"].as_str().is_none()
        || cfg["target_sha256"] != spec["set_publication"]["target_sha256"]
    {
        return Err("incorrect higher Cell target".into());
    }
    let rule = &g.program.rules[p.second[0]];
    let pivot = &rule.query[0];
    let mut slots = BTreeMap::new();
    for (col, arg) in pivot.args.iter().enumerate() {
        let Arg::Slot(x) = arg else {
            return Err("higher pivot must have fixed slots".into());
        };
        slots.insert(*x, col);
    }
    let template = &g.program.templates[rule.template];
    let [
        crate::program::Op::Let(dst, Call::Table(t), args),
        crate::program::Op::Set(_, keys, val),
    ] = &template.ops[..=p.second[1]]
    else {
        return Err("unsupported higher Set operand program".into());
    };
    if !matches!(pivot.call,Call::Table(q) if q==*t)
        || args.len() + 1 != pivot.args.len()
        || !args
            .iter()
            .zip(&pivot.args)
            .all(|(a, b)| matches!((a,b),(Arg::Slot(i),Arg::Slot(j))if i==j))
    {
        return Err("unproved middle constructor alias".into());
    }
    slots.insert(*dst, pivot.args.len() - 1);
    s.higher.alias_slot = *dst;
    for arg in keys.iter().chain([val]) {
        s.higher.projection.push(match arg {
            Arg::Slot(i) => FieldInput::Column(
                *slots
                    .get(i)
                    .ok_or("higher Set requires an independent value")?,
            ),
            Arg::Literal(v) => FieldInput::Constant(v.clone()),
        })
    }
    s.higher.enabled = true;
    s.higher.fault = spec["higher_fault"].as_str().unwrap_or("").to_owned();
    if ![
        "",
        "stale-generation",
        "duplicate",
        "only-stale",
        "alias-mismatch",
        "stale-epoch",
    ]
    .contains(&s.higher.fault.as_str())
    {
        return Err("unknown higher transaction fault".into());
    }
    Ok(())
}
impl HigherState {
    fn queue(&mut self, h: HigherHandle, run: usize, reply: Reply) -> Result<()> {
        let c = self
            .pending
            .get_mut(&h.root)
            .ok_or("request is no longer pending")?;
        if c.handle != h || c.inbox {
            return Err("reused or stale CPU transaction".into());
        }
        c.inbox = true;
        c.expected_reply_run = Some(run);
        self.inbox.push((h, run, reply));
        self.stats.peak_batch = self.stats.peak_batch.max(self.inbox.len());
        Ok(())
    }
    fn branch(&self, h: HigherHandle) -> Result<&PublishedSet> {
        let b = self
            .specialized
            .get(&h.root)
            .ok_or("unknown specialized owner")?;
        if b.handle != h
            || b.address != &**b as *const HigherOwner as usize
            || self.pending.contains_key(&h.root)
        {
            return Err("stale or multiply owned specialized context".into());
        }
        b.result
            .as_ref()
            .ok_or("missing specialized publication".into())
    }
    fn report(&self) -> J {
        json!({"enabled":self.enabled,"requests":self.stats.requests,"transferred":self.stats.transferred,"retired_no_result":self.stats.retired_no_result,
        "stale_replies":self.stats.stale_replies,"duplicate_replies":self.stats.duplicate_replies,"terminal_commits":self.stats.terminal_commits,
        "counts":self.stats,"pending":self.pending.len(),"specialized":self.specialized.len(),"audit_examples":self.events})
    }
}
pub(crate) fn higher_begin(
    serial: u64,
    rid: usize,
    ep: u64,
    refs: &[crate::joint_root::Ref],
) -> Result<()> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(()) };
        if !s.higher.enabled {
            return Ok(());
        }
        let Some(a) = &s.active else { return Ok(()) };
        let p = s.set_plan.as_ref().unwrap();
        if a.prior.is_empty() && rid == p.first[0] && serial == a.root {
            let h = &mut s.higher;
            let t = h.profile.then(Instant::now);
            h.generation = h
                .generation
                .checked_add(1)
                .ok_or("higher generation overflow")?;
            let key = HigherHandle {
                root: serial,
                generation: h.generation,
            };
            let mut ctx = Box::new(HigherOwner {
                handle: key,
                address: 0,
                issue_run: s.run,
                source_epoch: ep,
                inputs: refs.iter().map(|r| (r.row, r.version)).collect(),
                first: None,
                first_result: None,
                invalid_operands: false,
                fields: vec![],
                middle: None,
                result: None,
                inbox: false,
                expected_reply_run: None,
                existing: false,
            });
            if ctx.inputs.is_empty() {
                return Err("higher request lacks explicit inputs".into());
            }
            ctx.address = &*ctx as *const HigherOwner as usize;
            h.stats.named_inputs += ctx.inputs.len() as u64;
            if h.pending.insert(serial, ctx).is_some() {
                return Err("duplicate conservative owner".into());
            }
            h.stats.peak_capacity_bytes = h
                .stats
                .peak_capacity_bytes
                .max((h.pending.len() + h.specialized.len()) * std::mem::size_of::<HigherOwner>());
            h.request_queue.push(key);
            h.stats.queued_requests += 1;
            h.stats.peak_requests = h.stats.peak_requests.max(h.request_queue.len());
            h.stats.requests += 1;
            h.stats.peak_pending = h.stats.peak_pending.max(h.pending.len());
            if let Some(t) = t {
                h.stats.setup_ns += t.elapsed().as_nanos() as u64
            }
        } else if a.prior.as_slice() == [p.first] && rid == p.second[0] {
            let h = &mut s.higher;
            let c = h
                .pending
                .get_mut(&a.root)
                .ok_or("middle cannot claim missing prior request")?;
            let (f, e) = c.first.ok_or("missing first signed output")?;
            if c.issue_run >= s.run
                || c.source_epoch >= ep
                || refs.len() != 1
                || refs[0].row != Dependency::Fact(f)
                || refs[0].version != e
                || c.inbox
                || c.middle.is_some()
            {
                return Err("middle named input does not own this request".into());
            }
            c.middle = Some((serial, s.run));
            h.stats.middles += 1;
        }
        Ok(())
    })
}
pub(crate) fn higher_first(f: FactRef, t: usize, ep: u64) {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return };
        if !s.higher.enabled {
            return;
        }
        let Some(a) = &s.active else { return };
        let p = s.set_plan.as_ref().unwrap();
        if !a.prior.is_empty()
            || a.rule != p.first[0]
            || s.physical != Some(f.cell)
            || f.op as usize != p.first[1]
            || s.child_table.get(&p.first[2]) != Some(&t)
        {
            return;
        }
        let c = s
            .higher
            .pending
            .get_mut(&a.root)
            .expect("higher first output lost owner");
        assert!(c.first.replace((f, ep)).is_none());
    })
}
fn execute_request_batch(s: &mut State, g: &Graph) -> Result<()> {
    let h = &mut s.higher;
    if h.request_queue.is_empty() {
        return Ok(());
    }
    let clock = h.profile.then(Instant::now);
    h.stats.request_batches += 1;
    let mut requests = std::mem::take(&mut h.request_queue);
    for key in requests.drain(..) {
        let c = h
            .pending
            .get_mut(&key.root)
            .ok_or("queued request lacks its owner")?;
        if c.handle != key || c.issue_run != s.run {
            return Err("CPU request generation or source Run mismatch".into());
        }
        if c.inbox {
            continue;
        } // An aborted source RHS already supplied its cancellation.
        let Some((f, e)) = c.first else {
            h.queue(key, s.run, Reply::NoFirst)?;
            continue;
        };
        h.stats.request_reads += 1;
        let w = Dependency::Fact(f);
        let Some(row) = g
            .row(w)?
            .filter(|r| !r.hidden && r.epoch == e && r.witness == w && g.strict_member(r.table, w))
        else {
            h.queue(key, s.run, Reply::StaleInput)?;
            continue;
        };
        c.first_result = row.values.last().cloned();
        c.fields = h
            .projection
            .iter()
            .map(|expr| match expr {
                FieldInput::Column(i) => row
                    .values
                    .get(*i)
                    .cloned()
                    .ok_or_else(|| "CPU request missing named column".to_string()),
                FieldInput::Constant(v) => Ok(v.clone()),
            })
            .collect::<Result<Vec<_>>>()?;
        h.stats.prepared += 1;
    }
    h.request_queue = requests;
    if let Some(t) = clock {
        h.stats.request_ns += t.elapsed().as_nanos() as u64
    }
    Ok(())
}
pub(crate) fn higher_set_inputs(
    g: &Graph,
    cell: u32,
    op: usize,
    t: usize,
) -> Result<Option<(smallvec::SmallVec<[SetValue; 4]>, SetValue)>> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(None) };
        if !s.higher.enabled {
            return Ok(None);
        }
        let Some(a) = &s.active else { return Ok(None) };
        let p = s.set_plan.as_ref().unwrap();
        if a.prior.as_slice() != [p.first]
            || s.physical != Some(cell)
            || t != p.table
            || op != p.second[1]
        {
            return Ok(None);
        }
        let h = &mut s.higher;
        let clock = h.profile.then(Instant::now);
        let c = h
            .pending
            .get_mut(&a.root)
            .ok_or("Set request owner missing")?;
        if c.middle != Some((a.immediate_serial, s.run)) || c.inbox {
            return Err("Set operand request has wrong generation or Run".into());
        }
        let (fact, version) = c.first.ok_or("missing signed middle operand")?;
        let origin = c
            .first_result
            .as_ref()
            .ok_or("missing request alias operand")?;
        h.stats.operand_guard_reads += 1;
        if h.fault == "alias-mismatch"
            || g.visible_epoch(Dependency::Fact(fact)) != Some(version)
            || g.argument(cell, &Arg::Slot(h.alias_slot))?
                != crate::value::canon(origin, &g.parents)
        {
            c.invalid_operands = true;
            h.stats.operand_fallbacks += 1;
            if let Some(t) = clock {
                h.stats.setup_ns += t.elapsed().as_nanos() as u64
            };
            return Ok(None);
        }
        let (last, key) = c
            .fields
            .split_last()
            .ok_or("no named Set operand projection")?;
        let args = key
            .iter()
            .map(|v| crate::value::canon(v, &g.parents))
            .collect();
        let value = crate::value::canon(last, &g.parents);
        h.stats.operand_transfers += 1;
        h.stats.operand_fields += c.fields.len() as u64;
        if let Some(k) = clock {
            h.stats.setup_ns += k.elapsed().as_nanos() as u64
        }
        Ok(Some((args, value)))
    })
}
pub(crate) fn higher_after(success: bool) -> Result<bool> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(false) };
        if !s.higher.enabled {
            return Ok(false);
        }
        let h = &mut s.higher;
        let Some(a) = &s.active else { return Ok(true) };
        let Some(c) = h.pending.get(&a.root) else {
            return Ok(true);
        };
        let key = c.handle;
        let response = if !success {
            Some(Reply::Aborted)
        } else if a.prior.is_empty() {
            None
        } else if c.middle == Some((a.immediate_serial, s.run)) {
            if c.invalid_operands {
                s.pending_set.take();
                Some(Reply::StaleInput)
            } else if let Some(r) = s.pending_set.take() {
                Some(Reply::Fresh(r))
            } else if c.existing {
                Some(Reply::Existing)
            } else {
                Some(Reply::NoSet)
            }
        } else {
            None
        };
        if let Some(reply) = response {
            h.queue(key, s.run, reply)?;
        }
        Ok(true)
    })
}
fn deliver_higher(
    s: &mut State,
    g: &Graph,
    h: HigherHandle,
    at: usize,
    reply: Reply,
) -> Result<()> {
    let z = &mut s.higher;
    z.stats.replies += 1;
    let Some(owner) = z.pending.get(&h.root) else {
        if z.retired.get(&h.root) == Some(&h.generation)
            || z.specialized.get(&h.root).is_some_and(|b| b.handle == h)
        {
            z.stats.duplicate_replies += 1;
            return Ok(());
        }
        z.stats.stale_replies += 1;
        return Ok(());
    };
    if owner.handle != h
        || !owner.inbox
        || owner.expected_reply_run != Some(at)
        || at < owner.issue_run
        || owner.address != &**owner as *const HigherOwner as usize
    {
        z.stats.stale_replies += 1;
        return Ok(());
    }
    let mut b = z.pending.remove(&h.root).unwrap();
    let original = b.address;
    let mut retired = false;
    match reply {
        Reply::Fresh(record) => {
            z.stats.fresh_replies += 1;
            if b.middle != Some((record.middle, at))
                || record.root != h.root
                || record.run != at
                || record.fields.len() != b.fields.len()
            {
                return Err("invalid higher fresh reply provenance".into());
            }
            let w = Dependency::Fact(record.fact);
            let plan = s.set_plan.as_ref().ok_or("missing concrete Set plan")?;
            if !g.strict_member(record.table, w)
                || g.visible_epoch(w) != Some(record.generation)
                || record.fields.iter().zip(&b.fields).any(|(a, b)| {
                    crate::value::canon(a, &g.parents) != crate::value::canon(b, &g.parents)
                })
            {
                z.stats.retired_stale += 1;
                retired = true;
            } else {
                let path = record.path.clone();
                let endpoint = Owner {
                    higher_handle: Some(h),
                    set_data: None,
                    audit_ports: record.trail.clone(),
                    path: path.clone(),
                    root: h.root,
                    born: record.run,
                    version: record.generation,
                };
                b.result = Some(record);
                if z.specialized.insert(h.root, b).is_some() {
                    return Err("duplicate higher ownership transfer".into());
                }
                if z.specialized[&h.root].address != original
                    || original != &*z.specialized[&h.root] as *const HigherOwner as usize
                    || z.pending.contains_key(&h.root)
                {
                    return Err("higher owner allocation moved or aliased".into());
                }
                if s.ports
                    .entry(plan.second[2])
                    .or_default()
                    .insert(w, endpoint)
                    .is_some()
                {
                    return Err("duplicate higher output port".into());
                }
                *s.routes.entry(path).or_default().get_mut(0).unwrap() += 1;
                s.stats.named_ports += 1;
                s.set_counts.published += 1;
                z.stats.transferred += 1;
                z.stats.stable_address += 1;
                z.stats.peak_specialized = z.stats.peak_specialized.max(z.specialized.len());
                if s.record_links && z.events.len() < 8 {
                    z.events.push(json!([h.root, h.generation, at, "fresh"]));
                }
            }
        }
        Reply::NoFirst => {
            if b.first.is_some() || b.middle.is_some() || at != b.issue_run {
                return Err("invalid no-first reply".into());
            }
            z.stats.no_first_replies += 1;
            z.stats.retired_no_result += 1;
            retired = true;
        }
        Reply::Existing => {
            if !b.existing || b.middle.is_none_or(|(_, run)| run != at) {
                return Err("invalid existing Set reply".into());
            }
            z.stats.existing_replies += 1;
            z.stats.retired_no_result += 1;
            retired = true;
        }
        Reply::NoSet => {
            if b.middle.is_none_or(|(_, run)| run != at) {
                return Err("invalid no-Set reply".into());
            }
            z.stats.no_set_replies += 1;
            z.stats.retired_no_result += 1;
            retired = true;
        }
        Reply::Aborted => {
            z.stats.aborted += 1;
            z.stats.retired_no_result += 1;
            retired = true;
        }
        Reply::StaleInput => {
            z.stats.retired_stale += 1;
            retired = true;
        }
        Reply::Expired => {
            z.stats.expired += 1;
            z.stats.retired_no_result += 1;
            retired = true;
        }
    }
    if retired && z.retired.insert(h.root, h.generation).is_some() {
        return Err("double retirement of conservative instance".into());
    }
    Ok(())
}
pub(crate) fn higher_flush(g: &Graph) -> Result<()> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(()) };
        if !s.higher.enabled {
            return Ok(());
        }
        execute_request_batch(s, g)?;
        if s.higher.inbox.is_empty() {
            return Ok(());
        }
        let c = s.higher.profile.then(Instant::now);
        let mut queue = std::mem::take(&mut s.higher.inbox);
        s.higher.stats.batches += 1;
        for (id, at, reply) in queue.drain(..) {
            if s.higher.fault == "stale-generation" || s.higher.fault == "only-stale" {
                deliver_higher(
                    s,
                    g,
                    HigherHandle {
                        root: id.root,
                        generation: id.generation ^ 1,
                    },
                    at,
                    reply.clone(),
                )?;
                if s.higher.fault == "only-stale" {
                    continue;
                }
            }
            if s.higher.fault == "stale-epoch" {
                deliver_higher(
                    s,
                    g,
                    id,
                    at.checked_add(1).ok_or("bad response epoch")?,
                    reply.clone(),
                )?;
            }
            let duplicate = (s.higher.fault == "duplicate").then(|| reply.clone());
            deliver_higher(s, g, id, at, reply)?;
            if let Some(replay) = duplicate {
                deliver_higher(s, g, id, at, replay)?;
            }
        }
        s.higher.inbox = queue;
        if let Some(c) = c {
            s.higher.stats.response_ns += c.elapsed().as_nanos() as u64
        };
        Ok(())
    })
}
pub fn higher_close(g: &Graph) -> Result<()> {
    higher_flush(g)?;
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(()) };
        let h = &mut s.higher;
        if !h.enabled {
            return Ok(());
        }
        let clock = h.profile.then(Instant::now);
        // Outstanding requests at the end of the whole schedule are explicitly
        // expired. They establish no fresh port or source fact.
        let ids: Vec<_> = h.pending.values().map(|c| c.handle).collect();
        for id in ids {
            let b = h.pending.remove(&id.root).unwrap();
            if b.first
                .is_some_and(|(f, e)| g.visible_epoch(Dependency::Fact(f)) != Some(e))
            {
                h.stats.retired_stale += 1
            } else {
                h.stats.expired += 1;
                h.stats.retired_no_result += 1
            }
            if h.retired.insert(id.root, id.generation).is_some() {
                return Err("pending cleanup double retirement".into());
            }
        }
        let p = s.set_plan.as_ref().unwrap();
        for (id, b) in std::mem::take(&mut h.specialized) {
            let record = b.result.as_ref().unwrap();
            let o = s
                .ports
                .get_mut(&p.second[2])
                .and_then(|bank| bank.remove(&Dependency::Fact(record.fact)))
                .ok_or("missing higher slot on retirement")?;
            if o.higher_handle != Some(b.handle)
                || b.handle.root != id
                || h.retired.insert(id, b.handle.generation).is_some()
            {
                return Err("specialized owner retirement mismatch".into());
            }
            h.stats.retired_fresh += 1;
        }
        if h.stats.requests != h.retired.len() as u64
            || h.stats.retired_fresh != h.stats.transferred
            || h.stats.requests
                != h.stats.retired_fresh + h.stats.retired_no_result + h.stats.retired_stale
        {
            return Err("unbalanced higher owners at end".into());
        }
        h.retired.clear();
        if let Some(c) = clock {
            h.stats.teardown_ns += c.elapsed().as_nanos() as u64
        };
        Ok(())
    })
}

pub(crate) fn direct_operand_clock(eligible: bool) -> Option<Instant> {
    if !eligible {
        return None;
    };
    S.with_borrow(|v| {
        v.as_ref()
            .and_then(|s| (s.higher.profile && !s.higher.enabled).then(Instant::now))
    })
}
pub(crate) fn direct_operands_done(clock: Option<Instant>) {
    if let Some(t) = clock {
        let elapsed = t.elapsed().as_nanos() as u64;
        S.with_borrow_mut(|s| s.as_mut().unwrap().higher.stats.direct_operand_ns += elapsed);
    }
}
