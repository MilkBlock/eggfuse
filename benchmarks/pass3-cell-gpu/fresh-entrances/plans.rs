// Compiler-extracted source instructions only: no table rows or recorded outcomes.
type Ops = Vec<(usize, usize, Vec<usize>)>;
struct StaticEntrance {
    default: Rc<Ops>,
    by_atom: Vec<Option<Rc<Ops>>>,
}
#[derive(Default, Serialize)]
struct PlanCounts {
    inspected: u64,
    no_fresh_relation: u64,
    single_fresh_relation: u64,
    switched: u64,
    extra_parent_switches: u64,
}
fn slot_ids(args: &[Arg]) -> impl Iterator<Item = usize> + '_ {
    args.iter().filter_map(|arg| {
        if let Arg::Slot(id) = arg {
            Some(*id)
        } else {
            None
        }
    })
}

fn from_anchor(rule: &Rule, base: &Plan, first: usize, extra: usize) -> Option<Ops> {
    let n = rule.query.len();
    let num_slots = rule
        .query
        .iter()
        .flat_map(|atom| slot_ids(&atom.args))
        .max()
        .map_or(0, |x| x + 1);
    let mut bound = vec![false; num_slots];
    let mut picked = vec![false; n];
    let mut pointers = Vec::new();
    let mut pivot = first;
    let original: Vec<_> = base.ins.iter().filter(|x| x.1 == 1).map(|x| x.0).collect();
    loop {
        let atom = &rule.query[pivot];
        let shared = atom
            .args
            .iter()
            .enumerate()
            .filter_map(|(col, arg)| match arg {
                Arg::Slot(id) if bound[*id] => Some(col),
                _ => None,
            })
            .collect::<Vec<_>>();
        if !pointers.is_empty() && shared.is_empty() {
            return None;
        }
        pointers.push((pivot, 1, shared));
        picked[pivot] = true;
        for id in slot_ids(&atom.args) {
            bound[id] = true;
        }
        // Every remaining unique table lookup or primitive can run only AFTER sealing.
        let mut closed = bound.clone();
        let mut done = picked.clone();
        let mut suffix = Vec::new();
        loop {
            let before = suffix.len();
            for (i, a) in rule.query.iter().enumerate() {
                if done[i] || !slot_ids(&a.args[..a.args.len() - 1]).all(|id| closed[id]) {
                    continue;
                }
                done[i] = true;
                suffix.push((i, 0, vec![]));
                for id in slot_ids(&a.args) {
                    closed[id] = true;
                }
            }
            if before == suffix.len() {
                break;
            }
        }
        if done.iter().all(|v| *v) {
            if pointers.len() < base.width {
                return None;
            }
            pointers.extend(suffix);
            return Some(pointers);
        }
        if pointers.len() >= original.len() + extra {
            return None;
        }
        pivot = rule
            .query
            .iter()
            .enumerate()
            .filter_map(|(i, a)| {
                if picked[i] || !matches!(a.call, Call::Table(_)) {
                    return None;
                }
                let shared = slot_ids(&a.args).filter(|&id| bound[id]).count();
                if shared == 0 || !slot_ids(&a.args).any(|id| !bound[id]) {
                    return None;
                }
                Some(((original.contains(&i), shared, std::cmp::Reverse(i)), i))
            })
            .max_by_key(|x| x.0)?
            .1;
    }
}

pub fn configure_fresh_entrances(program: &Program, mode: &str) -> Result<()> {
    let (enabled, extra) = match mode {
        "shared" => (false, 0),
        "same_width" => (true, 0),
        "plus_one" => (true, 1),
        _ => return Err("unsupported entrance mode".into()),
    };
    STORE.with_borrow_mut(|cell| {
        let store = cell.as_mut().ok_or("no active pointer policy")?;
        if !store.seal || store.accel < 4 {
            return Err("freshness variants require sealed stack plans".into());
        }
        let mut plans = Vec::with_capacity(store.plans.len());
        for (r, base) in program.rules.iter().zip(&store.plans) {
            let Some(base) = base else {
                plans.push(None);
                continue;
            };
            let default = Rc::new(base.ins.clone());
            let by_atom = r
                .query
                .iter()
                .enumerate()
                .map(|(i, a)| {
                    if !enabled
                        || !r.seminaive
                        || !matches!(a.call, Call::Table(_))
                        || default[0].0 == i
                    {
                        return None;
                    }
                    from_anchor(r, base, i, extra).map(Rc::new)
                })
                .collect();
            plans.push(Some(StaticEntrance { default, by_atom }));
        }
        store.fresh_mode = enabled;
        store.static_entrances = plans;
        Ok(())
    })
}

impl Store {
    fn select_entrance(
        &mut self,
        g: &Graph,
        r: &Rule,
        rid: usize,
        mark: u64,
    ) -> Result<Option<Rc<Ops>>> {
        if self.static_entrances.is_empty() {
            return Ok(Some(Rc::new(self.plans[rid].as_ref().unwrap().ins.clone())));
        }
        let plan = self.static_entrances[rid]
            .as_ref()
            .expect("validated static entrance");
        let default = plan.default.clone();
        if !self.fresh_mode || !r.seminaive || mark == 0 {
            return Ok(Some(default));
        }
        self.plan_counts.inspected += 1;
        let mut fresh = None;
        for (i, atom) in r.query.iter().enumerate() {
            let Call::Table(t) = atom.call else {
                continue;
            };
            if self.frame(g, t)?.max_epoch >= mark {
                if fresh.is_some() {
                    return Ok(Some(default));
                }
                fresh = Some(i);
            }
        }
        let Some(first) = fresh else {
            self.plan_counts.no_fresh_relation += 1;
            return Ok(None);
        };
        self.plan_counts.single_fresh_relation += 1;
        let variants = &self.static_entrances[rid].as_ref().unwrap().by_atom;
        if let Some(plan) = &variants[first] {
            self.plan_counts.switched += 1;
            self.plan_counts.extra_parent_switches += u64::from(
                plan.iter().take_while(|x| x.1 == 1).count()
                    > default.iter().take_while(|x| x.1 == 1).count(),
            );
            Ok(Some(plan.clone()))
        } else {
            Ok(Some(default))
        }
    }
}
