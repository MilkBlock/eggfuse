#[derive(Default, Serialize)]
struct AtomStats {
    tests: u64,
    reuses: u64,
    rejected_literals: u64,
    rejected_repeats: u64,
    failure_cross: u64,
    failure_literal: u64,
    failure_local: u64,
    failure_header: u64,
    failure_feature_alias: u64,
    failure_signature_collision: u64,
}
enum AtomTest {
    Literal(usize, u16),
    Equal(usize, usize),
}
struct AtomStage {
    tests: Vec<AtomTest>,
    seen: Vec<u8>,
}
#[derive(Default)]
struct AtomChecks {
    mode: u64,
    stages: Vec<AtomStage>,
    stats: AtomStats,
}
pub fn enable_atom_checks(mode: u64) -> Result<()> {
    if mode > 2 {
        return Err("unknown local atom check".into());
    }
    STORE.with_borrow_mut(|cell| {
        let s = cell.as_mut().ok_or("missing port proposer")?;
        if !s.seal || s.accel != 4 || s.raw_cache.enabled {
            return Err("local checks require uncached sealed parent pages".into());
        }
        s.atoms.mode = mode;
        Ok(())
    })
}
impl Store {
    fn prepare_atom_checks(&mut self, c: &Context<'_>, steps: &[StackStep]) {
        self.atoms.stages.clear();
        for d in steps {
            let mut first = BTreeMap::new();
            let mut tests = vec![];
            for (col, arg) in c.rule.query[d.atom].args.iter().enumerate() {
                match arg {
                    Arg::Literal(v) => tests.push(AtomTest::Literal(
                        col,
                        self.code(&canon(v, &c.graph.parents)).key,
                    )),
                    Arg::Slot(slot) => {
                        if let Some(&old) = first.get(slot) {
                            tests.push(AtomTest::Equal(col, old))
                        } else {
                            first.insert(*slot, col);
                        }
                    }
                }
            }
            let seen = if self.atoms.mode == 2 && !tests.is_empty() {
                vec![0; d.frame.rows.len()]
            } else {
                vec![]
            };
            self.atoms.stages.push(AtomStage { tests, seen });
        }
    }
    fn local_codes_permit(&mut self, step: usize, idx: usize, row: &Row) -> bool {
        let stage = &self.atoms.stages[step];
        if stage.tests.is_empty() {
            return true;
        }
        if !stage.seen.is_empty() {
            let state = stage.seen[idx];
            if state != 0 {
                self.atoms.stats.reuses += 1;
                return state == 1;
            }
        }
        self.atoms.stats.tests += 1;
        let mut passed = true;
        for i in 0..stage.tests.len() {
            match self.atoms.stages[step].tests[i] {
                AtomTest::Literal(col, k) => {
                    if self.code(&row.values[col]).key != k {
                        self.atoms.stats.rejected_literals += 1;
                        passed = false;
                        break;
                    }
                }
                AtomTest::Equal(a, b) => {
                    if self.code(&row.values[a]).key != self.code(&row.values[b]).key {
                        self.atoms.stats.rejected_repeats += 1;
                        passed = false;
                        break;
                    }
                }
            }
        }
        let seen = &mut self.atoms.stages[step].seen;
        if !seen.is_empty() {
            seen[idx] = if passed { 1 } else { 2 };
        }
        passed
    }
    fn classify_parent_failure(&mut self, g: &Graph, r: &Rule, atom: usize, row: &Row, p: &Prefix) {
        let a = &r.query[atom];
        if row.hidden
            || !matches!(a.call,Call::Table(t) if t==row.table)
            || a.args.len() != row.values.len()
        {
            self.atoms.stats.failure_header += 1;
            return;
        }
        for (i, (op, v)) in a.args.iter().zip(row.values.iter()).enumerate() {
            match op {
                Arg::Literal(l) if canon(l, &g.parents) != *v => {
                    self.atoms.stats.failure_literal += 1;
                    return;
                }
                Arg::Slot(s) if p.slots.get(s).is_some_and(|old| old != v) => {
                    let repeated = a.args[..i]
                        .iter()
                        .any(|o| matches!(o,Arg::Slot(prior) if prior==s));
                    if repeated {
                        self.atoms.stats.failure_local += 1;
                    } else {
                        self.atoms.stats.failure_cross += 1;
                        let expected = p.slots.get(s).unwrap();
                        if mix(code_seed(expected)) & 65535 == mix(code_seed(v)) & 65535 {
                            self.atoms.stats.failure_feature_alias += 1;
                        } else if self.code(expected).key == self.code(v).key {
                            self.atoms.stats.failure_signature_collision += 1;
                        }
                    }
                    return;
                }
                _ => {}
            }
        }
        self.atoms.stats.failure_header += 1;
    }
}
