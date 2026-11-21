// A fresh Set publication is a distinct capability from a constructor return.
// This module runs inside strict_named so the actual first-hop permit is checked.
use crate::value::Value as SetValue;

#[derive(Clone)]
struct SetPlan {
    first: E,
    second: E,
    table: usize,
}
#[derive(Clone)]
struct PublishedSet {
    fact: FactRef,
    table: usize,
    generation: u64,
    run: usize,
    root: u64,
    middle: u64,
    fields: Vec<SetValue>,
    path: Vec<E>,
    trail: Option<std::rc::Rc<Vec<[u64; 4]>>>,
}
#[derive(Default, Serialize)]
struct PublicationCounts {
    encoded: u64,
    active_middles: u64,
    set_attempts: u64,
    existing_key: u64,
    fresh_activations: u64,
    published: u64,
    withheld: u64,
    cleared_on_error: u64,
    opened: u64,
    invalidated: u64,
    excluded_generation: u64,
    confirmed: u64,
}
fn plan_set(spec: &J, g: &Graph, s: &State) -> Result<Option<SetPlan>> {
    let v = &spec["set_publication"];
    if v.is_null() {
        return Ok(None);
    }
    if v["schema"] != "eggfuse-set-publication-program/v1"
        || v["kinds"] != json!(["fresh_constructor_let", "fresh_constructor_set"])
        || v["pivot"] != 0
        || s.depth != 2
        || !s.partial
    {
        return Err("incorrect typed Set-publication ABI".into());
    }
    let path: Vec<E> = serde_json::from_value(v["path"].clone()).map_err(|e| e.to_string())?;
    if path.len() != 2
        || path[0][2] != path[1][0]
        || s.library
            .as_ref()
            .is_none_or(|lib| !lib.contains(&vec![path[0]]) || lib.contains(&path))
    {
        return Err("Set publication requires a signed Let prefix and separate Set kind".into());
    }
    let get = |id: usize| g.program.rules.get(id).ok_or("unknown publication rule");
    let first = get(path[0][0])?;
    let mid = get(path[1][0])?;
    get(path[1][2])?;
    let p = &g.program.templates[first.template];
    let Some(crate::program::Op::Let(_, Call::Table(t), _)) = p.ops.get(path[0][1]) else {
        return Err("first publication edge is not a constructor Let".into());
    };
    if s.child_table.get(&path[0][2]) != Some(t) {
        return Err("wrong signed first pivot".into());
    }
    let p = &g.program.templates[mid.template];
    let Some(crate::program::Op::Set(t, keys, out)) = p.ops.get(path[1][1]) else {
        return Err("second publication edge is not a Set".into());
    };
    let decl = &g.program.tables[*t];
    if !decl.constructor
        || !decl.virtual_fact
        || v["table"] != decl.name.as_str()
        || s.child_table.get(&path[1][2]) != Some(t)
        || keys.len() + 1 != decl.schema.len()
    {
        return Err("unproved constructor Set table, key or consumer".into());
    }
    let mut bound: BTreeSet<usize> = mid.inputs.iter().copied().collect();
    let named = |a: &Arg, b: &BTreeSet<usize>| {
        matches!(a, Arg::Literal(_)) || matches!(a,Arg::Slot(i)if b.contains(i))
    };
    for ins in p.ops.iter().take(path[1][1]) {
        match ins {
            crate::program::Op::Copy(dst, a) if named(a, &bound) => {
                bound.insert(*dst);
            }
            crate::program::Op::Let(dst, Call::Table(t), args)
                if g.program.tables[*t].constructor && args.iter().all(|a| named(a, &bound)) =>
            {
                bound.insert(*dst);
            }
            _ => return Err("Set source depends on an unproved instruction".into()),
        }
    }
    if !keys.iter().chain([out]).all(|a| named(a, &bound)) {
        return Err("unbound Set input".into());
    }
    for (arg, sort) in keys.iter().chain([out]).zip(&decl.schema) {
        let valid = match arg {
            Arg::Slot(i) => p
                .sorts
                .get(*i)
                .is_some_and(|s| s["name"] == sort["name"] && s["kind"] == sort["kind"]),
            Arg::Literal(SetValue::Int(_)) => sort["kind"] == "i64",
            _ => false,
        };
        if !valid {
            return Err("Set key/value slot sort does not match constructor".into());
        }
    }
    Ok(Some(SetPlan {
        first: path[0],
        second: path[1],
        table: *t,
    }))
}
fn selection(s: &State, rid: usize) -> usize {
    (rid + 1)
        | if s.set_plan.as_ref().is_some_and(|p| p.first[0] == rid) {
            1usize << 31
        } else {
            0
        }
}
pub(crate) fn set_attempt(cell: u32, op: usize, t: usize) -> bool {
    S.with_borrow_mut(|s| {
        let Some(s) = s else { return false };
        let (Some(a), Some(p)) = (&s.active, &s.set_plan) else {
            return false;
        };
        if s.physical != Some(cell)
            || a.rule != p.second[0]
            || a.prior.as_slice() != [p.first]
            || p.second[1] != op
            || p.table != t
        {
            return false;
        }
        s.set_counts.set_attempts += 1;
        true
    })
}
pub(crate) fn set_existing() {
    S.with_borrow_mut(|s| s.as_mut().unwrap().set_counts.existing_key += 1)
}
pub(crate) fn capture_set(g: &Graph, f: FactRef, t: usize, fields: Vec<SetValue>) -> Result<()> {
    S.with_borrow_mut(|s|{
        let s=s.as_mut().ok_or("orphan Set activation")?;let a=s.active.as_ref().ok_or("missing internally committed middle")?;
        let p=s.set_plan.as_ref().ok_or("no authorized Set publication")?;
        if s.pending_set.is_some()||s.physical!=Some(f.cell)||!s.known.contains(&a.root)||a.prior.as_slice()!=[p.first]||a.rule!=p.second[0]||f.op as usize!=p.second[1]||t!=p.table
            ||crate::joint_root::consumed_serial()!=Some(a.immediate_serial){return Err("wrong physical producer of Set publication".into())}
        let c=g.cells.get(&f.cell).ok_or("missing Set frame")?;
        if c.template!=g.program.rules[a.rule].template||!matches!(g.program.templates[c.template].ops.get(f.op as usize),Some(crate::program::Op::Set(n,_,_)) if *n==t)
            || c.facts.get(&f.op).is_none_or(|v|v.born!=g.epoch||v.epoch!=g.epoch||v.hidden){return Err("Set publication has no fresh live operation".into())}
        let crate::program::Op::Set(_,args,assigned)=&g.program.templates[c.template].ops[f.op as usize]else{unreachable!()};
        let mut rederived=g.inline_arguments(f.cell,args)?.into_vec();rederived.push(g.argument(f.cell,assigned)?);
        if rederived!=fields{return Err("Set operand packet disagrees with current named frame".into())}
        let mut fields=fields;
        if s.set_fault=="wrong_fields"{*fields.last_mut().unwrap()=SetValue::Int(99);}
        let w=Dependency::Fact(f);let row=g.row(w)?.ok_or("Set primary activation missing")?;
        if row.table!=t||row.witness!=w||row.epoch!=g.epoch||row.hidden||!g.strict_member(t,w)||row.values.as_slice()!=fields.as_slice(){return Err("Set activation key/value or version differs".into())}
        let path=vec![p.first,p.second];let trail=if s.record_links{
            let mut trail=a.audit_ports.as_ref().ok_or("missing first receipt trail")?.as_ref().clone();
            trail.push([u64::from(f.cell),u64::from(f.op),g.epoch,a.run as u64]);Some(std::rc::Rc::new(trail))
        }else{None};
        s.set_counts.fresh_activations+=1;s.pending_set=Some(PublishedSet{fact:f,table:t,generation:g.epoch,run:a.run,root:a.root,middle:a.immediate_serial,fields,path,trail});Ok(())
    })
}
pub(crate) fn finish_set(success: bool) -> Result<()> {
    S.with_borrow_mut(|v| {
        let Some(s) = v else { return Ok(()) };
        let Some(record) = s.pending_set.take() else {
            return Ok(());
        };
        if !success {
            s.set_counts.cleared_on_error += 1;
            return Ok(());
        }
        if s.set_fault == "missing" {
            s.set_counts.withheld += 1;
            return Ok(());
        }
        let p = s.set_plan.as_ref().ok_or("unconfigured Set release")?;
        let w = Dependency::Fact(record.fact);
        let o = Owner {
            audit_ports: record.trail.clone(),
            set_data: Some(std::rc::Rc::new(record.clone())),
            path: record.path.clone(),
            root: record.root,
            born: record.run,
            version: record.generation,
        };
        if s.ports
            .entry(p.second[2])
            .or_default()
            .insert(w, o)
            .is_some()
        {
            return Err("duplicate fresh Set registration".into());
        }
        s.routes.entry(record.path).or_default()[0] += 1;
        s.stats.named_ports += 1;
        s.set_counts.published += 1;
        Ok(())
    })
}
