// An independently sealed token can reuse a partial binding only after its source
// and the whole shared prefix are identified in the current graph.
use std::rc::Rc as FamilyRc;
const FAMILY_CAP: usize = 512;
#[derive(Default, serde::Serialize)]
struct FamilyStats {
    rules: usize,
    families: usize,
    prefix_rules: usize,
    full_slots: usize,
    stored_slots: usize,
    stored_values: u64,
    restored_values: u64,
    accesses: u64,
    misses: u64,
    hits: u64,
    negative: u64,
    sibling: u64,
    sibling_negative: u64,
    changed_epoch: u64,
    sibling_changed_epoch: u64,
    step_hits: u64, // counts the shared-step shape, including failures at the pivot
    audit_sibling_pairs: BTreeMap<usize, BTreeMap<usize, u64>>,
    audit_stamp_misses: u64,
    audit_collisions: u64,
    audit_checks: u64,
    replacements: u64,
    cold_entries: u64,
}
struct FamilyLayout {
    family: usize,
    depth: usize,
    anchor: usize,
    second: Option<usize>,
    slots: Vec<usize>,
}
#[derive(Clone, Copy, Eq, PartialEq)]
struct FamilyStamp {
    address: Dependency,
    token_version: u64,
    anchor_generation: u64,
    suffix_generation: u64,
    union_generation: u64,
}
#[derive(PartialEq, Debug)]
struct PartialBinding {
    values: Box<[Value]>,
    second: Option<Dependency>,
    epoch: u64,
}
struct FamilyEntry {
    stamp: FamilyStamp,
    writer: usize,
    observed_epoch: u64,
    binding: Option<PartialBinding>,
}
#[derive(Default)]
struct FamilyChecks {
    mode: u64,
    audit: bool,
    layout: Vec<Option<FamilyRc<FamilyLayout>>>,
    banks: Vec<Vec<Option<FamilyEntry>>>,
    stats: FamilyStats,
}
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
enum PrefixOperand {
    Slot(usize),
    Literal(Value),
}
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord)]
enum PrefixCall {
    Table(usize),
    Primitive(String, String),
}
type PrefixCode = Vec<(PrefixCall, Vec<PrefixOperand>)>;

fn family_code(r: &Rule, p: &Plan, depth: usize) -> Option<(PrefixCode, Vec<usize>)> {
    let mut names = Vec::new();
    let mut code = Vec::new();
    for ix in std::iter::once(p.pivot?).chain(p.order.iter().take(depth).copied()) {
        let a = &r.query[ix];
        // Float interning can have an observable side effect; unsupported literals
        // also stay on the original source path.
        if a.args
            .iter()
            .any(|arg| matches!(arg, Arg::Literal(Value::Float(_) | Value::Set(_))))
        {
            return None;
        }
        let op = match &a.call {
            Call::Table(t) => PrefixCall::Table(*t),
            Call::Primitive(name, ty)
                if matches!(ty.as_str(), "i64" | "Unit")
                    && matches!(
                        name.as_str(),
                        "+" | "-"
                            | "*"
                            | "/"
                            | "%"
                            | "<"
                            | ">"
                            | "<="
                            | ">="
                            | "!="
                            | "eq-id-!="
                            | "min"
                            | "max"
                    ) =>
            {
                PrefixCall::Primitive(name.clone(), ty.clone())
            }
            _ => return None,
        };
        let args = a
            .args
            .iter()
            .map(|a| match a {
                Arg::Literal(v) => PrefixOperand::Literal(v.clone()),
                Arg::Slot(s) => {
                    let i = names.iter().position(|v| v == s).unwrap_or_else(|| {
                        names.push(*s);
                        names.len() - 1
                    });
                    PrefixOperand::Slot(i)
                }
            })
            .collect();
        code.push((op, args));
    }
    Some((code, names))
}

impl Trial {
    pub(crate) fn install_family(&mut self, prog: &Program, mode: u64) -> Result<()> {
        if mode == 0 {
            return Ok(());
        }
        if !(1..=5).contains(&mode)
            || self.rows.verify.mode != 2
            || self.rows.verify.projected.mode != 0
        {
            return Err("sibling prefixes require the ordinary watermark verifier".into());
        }
        let state = &mut self.rows.verify.family;
        state.mode = mode;
        state.audit = self.rows.detailed;
        state.layout = (0..self.plans.len()).map(|_| None).collect();
        // Greedily group at depth one; group remaining plans by their pivot pattern.
        for depth in (0..=usize::from(mode >= 2)).rev() {
            let mut families: BTreeMap<PrefixCode, Vec<(usize, Vec<usize>)>> = BTreeMap::new();
            for (rid, p) in self.plans.iter().enumerate() {
                let Some(p) = p else { continue };
                if state.layout[rid].is_some() || p.order.len() < depth {
                    continue;
                }
                if let Some((code, slots)) = family_code(&prog.rules[rid], p, depth) {
                    families.entry(code).or_default().push((rid, slots));
                }
            }
            for (code, group) in families {
                if group.len() < 2 {
                    continue;
                }
                let family = state.banks.len();
                state.banks.push(Vec::new());
                let PrefixCall::Table(anchor) = code[0].0 else {
                    unreachable!()
                };
                let second = code.get(1).and_then(|(c, _)| {
                    if let PrefixCall::Table(t) = c {
                        Some(*t)
                    } else {
                        None
                    }
                });
                // Consumers may use different source slot numbers. Keep normalized
                // positions demanded by any consuming tail or RHS. A repeat in
                // a tail result is still an equality obligation and stays live.
                let mut live = vec![mode != 5; group[0].1.len()];
                if mode == 5 {
                    for (rid, slots) in &group {
                        let rule = &prog.rules[*rid];
                        let plan = self.plans[*rid].as_ref().unwrap();
                        let mut used: BTreeSet<_> = rule.inputs.iter().copied().collect();
                        for &i in &plan.order[depth..] {
                            for a in &rule.query[i].args {
                                if let Arg::Slot(s) = a {
                                    used.insert(*s);
                                }
                            }
                        }
                        for (k, slot) in slots.iter().enumerate() {
                            live[k] |= used.contains(slot);
                        }
                    }
                }
                for (rid, slots) in group {
                    state.stats.full_slots += slots.len();
                    let slots: Vec<_> = slots
                        .into_iter()
                        .zip(&live)
                        .filter_map(|(s, l)| l.then_some(s))
                        .collect();
                    state.stats.stored_slots += slots.len();
                    state.layout[rid] = Some(FamilyRc::new(FamilyLayout {
                        family,
                        depth,
                        anchor,
                        second,
                        slots,
                    }));
                    state.stats.rules += 1;
                    state.stats.prefix_rules += depth;
                }
            }
        }
        state.stats.families = state.banks.len();
        Ok(())
    }
}

fn family_index(w: Dependency) -> usize {
    let id = match w {
        Dependency::Fact(f) => u64::from(f.cell).wrapping_mul(0x9e3779b185ebca87) ^ u64::from(f.op),
        Dependency::Function(i) => i as u64,
    };
    ((id ^ (id >> 32)) as usize) & (FAMILY_CAP - 1)
}
impl VerifiedRows {
    fn check_family(
        &mut self,
        g: &Graph,
        r: &Rule,
        p: &Plan,
        tok: &Token,
        work: &mut [u64; 8],
        reg: &mut [Option<Value>],
        witnesses: &mut [Option<Dependency>],
        l: &FamilyLayout,
    ) -> Result<Option<u64>> {
        let w = tok.w.ok_or("missing sibling root")?;
        let stamp = FamilyStamp {
            address: w,
            token_version: tok.version,
            anchor_generation: g.query_versions[l.anchor],
            suffix_generation: l.second.map_or(0, |t| g.query_versions[t]),
            union_generation: g.stats.unions,
        };
        let pos = family_index(w);
        self.family.stats.accesses += 1;
        let hit = self.family.banks[l.family]
            .get(pos)
            .and_then(Option::as_ref)
            .is_some_and(|e| e.stamp == stamp && (self.family.mode != 3 || e.writer != tok.rid));
        if hit {
            if self.family.audit {
                let mut scratch = vec![None; reg.len()];
                let mut refs = vec![None; witnesses.len()];
                let mut work = [0; 8];
                let exact = self.evaluate_prefix(
                    g,
                    r,
                    p,
                    tok,
                    &mut work,
                    &mut scratch,
                    &mut refs,
                    l.depth,
                )?;
                let expected = exact.map(|epoch| PartialBinding {
                    epoch,
                    values: l
                        .slots
                        .iter()
                        .map(|&i| scratch[i].clone().expect("bound prefix slot"))
                        .collect(),
                    second: if l.depth == 1 { refs[p.order[0]] } else { None },
                });
                let cached = self.family.banks[l.family][pos].as_ref().unwrap();
                if cached.binding != expected {
                    return Err("sibling prefix disagrees with source verification".into());
                }
                self.family.stats.audit_checks += 1;
                if cached.writer != tok.rid {
                    *self
                        .family
                        .stats
                        .audit_sibling_pairs
                        .entry(cached.writer)
                        .or_default()
                        .entry(tok.rid)
                        .or_default() += 1;
                }
            }
            let entry = self.family.banks[l.family][pos].as_ref().unwrap();
            let sibling = entry.writer != tok.rid;
            self.family.stats.hits += 1;
            self.family.stats.sibling += u64::from(sibling);
            self.family.stats.changed_epoch += u64::from(entry.observed_epoch != g.epoch);
            self.family.stats.sibling_changed_epoch +=
                u64::from(sibling && entry.observed_epoch != g.epoch);
            self.family.stats.step_hits += l.depth as u64;
            if let Some(proof) = &entry.binding {
                self.family.stats.restored_values += l.slots.len() as u64;
                for (&slot, value) in l.slots.iter().zip(proof.values.iter()) {
                    reg[slot] = Some(value.clone());
                }
                witnesses[p.pivot.unwrap()] = Some(w);
                if l.depth != 0 {
                    witnesses[p.order[0]] = proof.second;
                }
                return Ok(Some(proof.epoch));
            }
            self.family.stats.negative += 1;
            self.family.stats.sibling_negative += u64::from(sibling);
            return Ok(None);
        }
        self.family.stats.misses += 1;
        if self.family.audit
            && let Some(e) = self.family.banks[l.family]
                .get(pos)
                .and_then(Option::as_ref)
        {
            if e.stamp.address != w {
                self.family.stats.audit_collisions += 1;
            } else if e.stamp != stamp {
                self.family.stats.audit_stamp_misses += 1;
            }
        }
        let epoch = self.evaluate_prefix(g, r, p, tok, work, reg, witnesses, l.depth)?;
        if self.family.mode == 4 && epoch.is_some() {
            return Ok(epoch);
        }
        self.family.stats.stored_values += if epoch.is_some() {
            l.slots.len() as u64
        } else {
            0
        };
        let binding = epoch.map(|epoch| PartialBinding {
            epoch,
            values: l
                .slots
                .iter()
                .map(|&i| reg[i].clone().expect("bound prefix slot"))
                .collect(),
            second: if l.depth == 1 {
                witnesses[p.order[0]]
            } else {
                None
            },
        });
        let bank = &mut self.family.banks[l.family];
        if bank.is_empty() {
            bank.resize_with(FAMILY_CAP, || None);
        }
        if bank[pos].is_some() {
            self.family.stats.replacements += 1
        } else {
            self.family.stats.cold_entries += 1
        }
        bank[pos] = Some(FamilyEntry {
            stamp,
            writer: tok.rid,
            observed_epoch: g.epoch,
            binding,
        });
        Ok(epoch)
    }
}
