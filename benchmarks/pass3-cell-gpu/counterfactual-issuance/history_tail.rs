// The issuer signs an optional, point-determined successor with its root.
// The successor may read only its returned HasArgType and a fully keyed Single.
struct HistoryTail {
    rule: usize,
    effects: [usize; 2],
    depth: usize,
    consult_context: bool,
    own_misses: bool,
    omitted: Vec<(u64, VersionedPort, usize)>,
    get: usize,
    single: usize,
    projections: Vec<Vec<Option<(bool, usize)>>>,
    get_results: BTreeMap<VersionedPort, u64>,
    single_subjects: std::collections::BTreeSet<u64>,
    scale: [usize; 3],
    inherited: BTreeMap<u64, usize>,
    signed: std::collections::BTreeSet<(u64, [VersionedPort; 2])>,
    active: Option<(usize, usize, usize)>,
    pending: BTreeMap<VersionedPort, (usize, u64, usize)>,
    attempts: usize,
    children: Vec<(u64, usize)>,
}

impl HistoryTail {
    fn compile(program: &Program, root: usize, table: usize, spec: &J) -> Result<Option<Self>> {
        if spec.is_null() {
            return Ok(None);
        }
        let depth = spec["depth"].as_u64().ok_or("missing signed depth")? as usize;
        if depth == 0 {
            return Err("empty successor".into());
        }
        let rid = spec["rule"].as_u64().ok_or("missing history successor")? as usize;
        let r = program.rules.get(rid).ok_or("unknown history successor")?;
        let [single, pivot] = r.query.as_slice() else {
            return Err("invalid history tail arity".into());
        };
        let (Call::Table(a), Call::Table(b)) = (&single.call, &pivot.call) else {
            return Err("invalid history tail tables".into());
        };
        let all: Vec<_> = single
            .args
            .iter()
            .chain(&pivot.args)
            .filter_map(|a| match a {
                Arg::Slot(i) => Some(i),
                _ => None,
            })
            .collect();
        if !r.seminaive
            || program.tables[*a].name != "Single"
            || *b != table
            || all.len() != 5
            || single.args.len() != 2
            || pivot.args.len() != 3
            || all[0] != all[2]
            || all.iter().collect::<std::collections::BTreeSet<_>>().len() != 4
        {
            return Err("successor needs exactly one determined constructor key".into());
        }
        let effect = |rid: usize| -> Result<usize> {
            let template = &program.templates[program.rules[rid].template];
            let mut matches = template.ops.iter().enumerate().filter(
                |(_, op)| matches!(op,crate::program::Op::Let(_,Call::Table(id),_) if *id==table),
            );
            let (op, _) = matches.next().ok_or("missing return effect")?;
            if matches.next().is_some() {
                return Err("ambiguous result operation".into());
            }
            Ok(op)
        };
        let get = program
            .tables
            .iter()
            .position(|t| t.name == "Get")
            .ok_or("missing Get")?;
        let single = *a;
        let projections = program
            .rules
            .iter()
            .map(|r| {
                r.query
                    .iter()
                    .map(|atom| {
                        let Call::Table(t) = atom.call else {
                            return None;
                        };
                        let col = if t == get {
                            atom.args.last()
                        } else if t == single {
                            atom.args.first()
                        } else {
                            None
                        };
                        let Some(Arg::Slot(slot)) = col else {
                            return None;
                        };
                        Some((t == get, *slot))
                    })
                    .collect()
            })
            .collect();
        Ok(Some(Self {
            rule: rid,
            effects: [effect(root)?, effect(rid)?],
            depth,
            own_misses: spec["own_misses"].as_bool().unwrap_or(false),
            omitted: Vec::new(),
            consult_context: spec["context"].as_bool().unwrap_or(false),
            get,
            single,
            projections,
            get_results: Default::default(),
            single_subjects: Default::default(),
            scale: [0; 3],
            inherited: Default::default(),
            signed: Default::default(),
            active: None,
            pending: Default::default(),
            attempts: 0,
            children: vec![],
        }))
    }

    fn inputs(&mut self, rule: usize, refs: &[Ref], slots: &Slots) {
        if !self.consult_context {
            return;
        }
        for r in refs {
            let Some((get, slot)) = self.projections[rule][r.atom] else {
                continue;
            };
            let (Some(Value::Eq(key)), Dependency::Fact(f)) = (slots.get(&slot), r.row) else {
                continue;
            };
            if get {
                self.get_results
                    .insert([u64::from(f.cell), u64::from(f.op), r.version], *key);
            } else {
                self.single_subjects.insert(*key);
            }
        }
    }

    fn returned(&mut self, table: usize, args: &[Value], result: &Value, port: VersionedPort) {
        if !self.consult_context {
            return;
        }
        if table == self.get
            && let Value::Eq(key) = result
        {
            self.get_results.insert(port, *key);
        }
        if table == self.single
            && let Some(Value::Eq(key)) = args.first()
        {
            self.single_subjects.insert(*key);
        }
    }

    fn select(&mut self, epoch: u64, pair: [VersionedPort; 2], weight: f32, bias: f32) {
        self.scale[0] += 1;
        if self.consult_context {
            let Some(&subject) = self.get_results.get(&pair[0]) else {
                return;
            };
            self.scale[1] += 1;
            if !self
                .single_subjects
                .iter()
                .any(|&key| ((subject ^ key).count_ones() as f32) * weight + bias >= 0.)
            {
                return;
            }
        }
        self.scale[2] += 1;
        self.signed.insert((epoch, pair));
    }

    fn enter(
        &mut self,
        epoch: u64,
        owner: usize,
        serial: u64,
        rule: usize,
        is_root: bool,
        refs: &[Ref],
    ) {
        self.active = None;
        if rule == self.rule
            && let Some(remaining) = self.inherited.remove(&serial)
        {
            self.active = Some((owner, self.effects[1], remaining));
            return;
        }
        if !is_root || refs.len() != 2 {
            return;
        }
        let mut pair = [[0; 3]; 2];
        for r in refs {
            let Dependency::Fact(f) = r.row else { return };
            if r.atom >= 2 {
                return;
            }
            pair[r.atom] = [u64::from(f.cell), u64::from(f.op), r.version];
        }
        if self.signed.remove(&(epoch, pair)) {
            self.active = Some((owner, self.effects[0], self.depth))
        }
    }
}

pub(crate) fn history_tail_claims(rule: usize, epoch: u64) -> Vec<(Dependency, u64, usize, usize)> {
    STATE.with_borrow_mut(|s| {
        let Some(t) = s
            .as_mut()
            .and_then(|s| s.history_issuer.as_mut())
            .and_then(|h| h.tail.as_mut())
        else {
            return vec![];
        };
        if rule != t.rule {
            return vec![];
        }
        let mut claims = Vec::new();
        t.pending
            .retain(|&[cell, op, version], (owner, birth, depth)| {
                if *birth >= epoch {
                    return true;
                }
                claims.push((
                    Dependency::Fact(crate::graph::FactRef {
                        cell: cell as u32,
                        op: op as u32,
                    }),
                    version,
                    *owner,
                    *depth,
                ));
                false
            });
        t.attempts += claims.len();
        claims
    })
}

pub(crate) fn history_tail_recipe(
    epoch: u64,
    rid: usize,
    row: Dependency,
    version: u64,
    owner: usize,
    depth: usize,
) -> Result<Recipe> {
    let serial = STATE.with_borrow_mut(|s| -> Result<u64> {
        let s = s.as_mut().ok_or("missing history issuer")?;
        let tail = s
            .history_issuer
            .as_mut()
            .and_then(|h| h.tail.as_mut())
            .ok_or("missing signed history tail")?;
        if tail.rule != rid {
            return Err("wrong signed history child".into());
        }
        s.serial += 1;
        if depth > 1 {
            tail.inherited.insert(s.serial, depth - 1);
        }
        tail.children.push((s.serial, owner));
        Ok(s.serial)
    })?;
    internal_point(epoch, rid, 1, row, version, serial)
}

pub(crate) fn history_tail_miss(epoch: u64, row: Dependency, version: u64, owner: usize) -> bool {
    STATE.with_borrow_mut(|s| {
        let Some(t) = s
            .as_mut()
            .and_then(|s| s.history_issuer.as_mut())
            .and_then(|h| h.tail.as_mut())
        else {
            return false;
        };
        if !t.own_misses {
            return false;
        }
        let Dependency::Fact(f) = row else {
            return false;
        };
        t.omitted
            .push((epoch, [u64::from(f.cell), u64::from(f.op), version], owner));
        true
    })
}
