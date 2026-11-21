use smallvec::SmallVec;

enum WriteOperand {
    Input(usize),
    Result(usize),
    Literal(Value),
}
impl WriteOperand {
    fn read(&self, values: &crate::slots::Slots, results: &[Value], parents: &Parents) -> Value {
        let value = match self {
            Self::Input(i) => &values[i],
            Self::Result(i) => &results[*i],
            Self::Literal(v) => v,
        };
        canon(value, parents)
    }
}
struct ScalarStep {
    dst: usize,
    name: String,
    sort: String,
    args: Vec<WriteOperand>,
}
pub(crate) struct CompiledWrite {
    inputs: Vec<usize>,
    shadow_slots: Vec<usize>,
    ops: Vec<ScalarStep>,
    key: Vec<WriteOperand>,
    value: WriteOperand,
}
impl CompiledWrite {
    pub(crate) fn lower(program: &Program, rule: usize) -> Option<Self> {
        let r = &program.rules[rule];
        let t = &program.templates[r.template];
        let w = program.writes[rule].as_ref()?;
        let mut defs = std::collections::BTreeMap::new();
        let mut shadows = std::collections::BTreeSet::new();
        let mut lower =
            |a: &Arg, defs: &std::collections::BTreeMap<usize, usize>| -> Option<WriteOperand> {
                let mut a = a.clone();
                let mut path = std::collections::BTreeSet::new();
                loop {
                    match a {
                        Arg::Literal(v) => return Some(WriteOperand::Literal(v)),
                        Arg::Slot(s) => {
                            if let Some(&i) = defs.get(&s) {
                                return Some(WriteOperand::Result(i));
                            }
                            if r.inputs.contains(&s) {
                                return Some(WriteOperand::Input(s));
                            }
                            if !path.insert(s) {
                                return None;
                            }
                            shadows.insert(s);
                            if let Some(Some(alias)) = program
                                .known_results
                                .static_slots
                                .get(r.template)
                                .and_then(|slots| slots.get(s))
                            {
                                a = alias.clone();
                            } else if let Some(Op::Copy(_, src)) =
                                t.defs.get(&s).and_then(|i| t.ops.get(*i))
                            {
                                a = src.clone();
                            } else {
                                return None;
                            }
                        }
                    }
                }
            };
        // The source write compiler already proved that no table or visibility
        // effects precede this write. Restrict repeated audit evaluation to pure arithmetic.
        let mut ops = Vec::new();
        for &i in &w.prefix {
            let Op::Let(dst, Call::Primitive(name, sort), args) = &t.ops[i] else {
                return None;
            };
            if sort != "i64"
                || !matches!(name.as_str(), "+" | "-" | "*" | "min" | "max" | "/" | "%")
            {
                return None;
            }
            let args = args
                .iter()
                .map(|a| lower(a, &defs))
                .collect::<Option<_>>()?;
            defs.insert(*dst, ops.len());
            ops.push(ScalarStep {
                dst: *dst,
                name: name.clone(),
                sort: sort.clone(),
                args,
            });
        }
        let key = w
            .key
            .iter()
            .map(|a| lower(a, &defs))
            .collect::<Option<Vec<_>>>()?;
        let value = lower(&w.value, &defs)?;
        if key.len() > 16 || ops.len() > 8 {
            return None;
        }
        let mut inputs = std::collections::BTreeSet::new();
        for a in ops
            .iter()
            .flat_map(|op| &op.args)
            .chain(&key)
            .chain(std::iter::once(&value))
        {
            if let WriteOperand::Input(s) = a {
                inputs.insert(*s);
            }
        }
        Some(Self {
            inputs: inputs.into_iter().collect(),
            shadow_slots: shadows.into_iter().collect(),
            ops,
            key,
            value,
        })
    }
}

#[derive(Default, serde::Serialize)]
pub(crate) struct OrderedWriteStats {
    pub(crate) calls: u64,
    by_table: std::collections::BTreeMap<usize, [u64; 4]>,
    prefix_ops: u64,
    changed: u64,
    unchanged: u64,
    key_fields: u64,
    multi_key: u64,
    key_receipts: u64,
    full_key_probes: u64,
    reused_key: u64,
    audited: u64,
    proved_absorbed: u64,
}
#[derive(Default)]
pub(crate) struct OrderedWrites {
    last: Option<(usize, u64, u64, u64, Vec<Value>, usize)>,
    pub(crate) stats: OrderedWriteStats,
}
impl OrderedWrites {
    pub(crate) fn reset(&mut self) {
        self.last = None;
    }
}
impl Graph {
    pub(crate) fn apply_compiled_write(
        &mut self,
        template: usize,
        values: crate::slots::Slots,
        parent: Option<FactRef>,
        write: &crate::row_kernel::Write,
        keep_key: bool,
        plan: &CompiledWrite,
        remember: bool,
        guard: bool,
    ) -> Result<(u32, usize, Option<Vec<Value>>, bool)> {
        if parent.is_some()
            || !plan.inputs.iter().all(|s| values.contains_key(s))
            || plan.shadow_slots.iter().any(|s| values.contains_key(s))
        {
            return self.apply_write(template, values, parent, write, keep_key);
        }
        self.ordered_writes.stats.calls += 1;
        let id = self.reserve_cell_id()?;
        self.stats.single_writes += 1;
        let mut results = SmallVec::<[Value; 2]>::new();
        for op in &plan.ops {
            let args = op
                .args
                .iter()
                .map(|a| a.read(&values, &results, &self.parents))
                .collect::<SmallVec<[Value; 3]>>();
            let v = self
                .primitive(&op.name, &args, &op.sort)?
                .ok_or_else(|| format!("RHS primitive failed: {}", op.name))?;
            results.push(v);
            self.ordered_writes.stats.prefix_ops += 1;
        }
        let key = plan
            .key
            .iter()
            .map(|a| a.read(&values, &results, &self.parents))
            .collect::<SmallVec<[Value; 4]>>();
        let value = plan.value.read(&values, &results, &self.parents);
        if self.effect_operand_audit {
            let mut source = self.new_cell(template, values.clone(), None);
            let ops = self.program.templates[template].ops.clone();
            for &i in &write.prefix {
                let Op::Let(dst, call, args) = &ops[i] else {
                    return Err("invalid source write".into());
                };
                crate::cell::evaluate_call(
                    self,
                    &mut crate::cell::LocalCall {
                        cell: id,
                        frame: &mut source,
                    },
                    i,
                    *dst,
                    call,
                    args,
                )?;
            }
            for (op, v) in plan.ops.iter().zip(&results) {
                if source.values.get(&op.dst) != Some(v) {
                    return Err("effect block changed a scalar intermediate".into());
                }
            }
            let expected = self.frame_arguments::<Vec<_>>(id, &source, None, &write.key)?;
            if expected.as_slice() != key.as_slice()
                || self.argument_in(id, &source, None, &write.value)? != value
            {
                return Err("effect block changed the source function or key".into());
            }
            self.ordered_writes.stats.audited += 1;
        }
        let t = write.table;
        let hint = if remember {
            self.ordered_writes
                .last
                .as_ref()
                .and_then(|(table, e, u, version, prior, i)| {
                    (*table == t
                        && *e == self.epoch
                        && *u == self.stats.unions
                        && *version == self.query_versions[t]
                        && prior.as_slice() == key.as_slice())
                    .then_some(*i)
                })
        } else {
            None
        };
        let index = if let Some(i) = hint {
            if self.effect_operand_audit && self.function_index(t, &key) != Some(i) {
                return Err("stale ordered function receipt".into());
            }
            self.ordered_writes.stats.reused_key += 1;
            Some(i)
        } else {
            self.ordered_writes.stats.full_key_probes += 1;
            self.function_index(t, &key)
        };
        self.ordered_writes.stats.key_fields += key.len() as u64;
        self.ordered_writes.stats.multi_key += u64::from(key.len() > 1);
        let before = self.stats.function_updates;
        let absorbed = index.filter(|&i| {
            if !guard {
                return false;
            }
            use crate::physical_plan::ScalarMerge;
            match (
                self.program.physical.merges[t],
                &self.functions[i].value,
                &value,
            ) {
                (Some(ScalarMerge::Old), _, _) => true,
                (Some(ScalarMerge::Min), Value::Int(old), Value::Int(new)) => old <= new,
                (Some(ScalarMerge::Max), Value::Int(old), Value::Int(new)) => old >= new,
                _ => false,
            }
        });
        let i = if let Some(i) = absorbed {
            if self.effect_operand_audit {
                let prior = canon(&self.functions[i].value, &self.parents);
                if self.merge_value(t, prior.clone(), value)? != prior {
                    return Err("wrong ordered merge absorption".into());
                }
            }
            self.ordered_writes.stats.proved_absorbed += 1;
            i
        } else {
            self.set_function_at(t, &key, value, None, index)?
        };
        if remember {
            self.ordered_writes.last = Some((
                t,
                self.epoch,
                self.stats.unions,
                self.query_versions[t],
                key.to_vec(),
                i,
            ));
        }
        let changed = self.stats.function_updates != before;
        if self.effect_operand_audit {
            let refs = self.ordered_writes.stats.by_table.entry(t).or_default();
            refs[0] += 1;
            refs[1] += u64::from(changed);
            refs[2] += plan.ops.len() as u64;
            refs[3] += u64::from(hint.is_some());
        }
        if changed {
            let mut frame = self.new_cell(template, values, None);
            for (op, v) in plan.ops.iter().zip(results) {
                frame.values.insert(op.dst, v);
            }
            self.keep_writer(i, id, write.op, frame)?;
            self.ordered_writes.stats.changed += 1;
        } else {
            self.stats.rhs_frames_avoided += 1;
            self.stats.transient_writes += 1;
            self.ordered_writes.stats.unchanged += 1;
        }
        self.ordered_writes.stats.key_receipts += u64::from(keep_key);
        Ok((id, i, keep_key.then(|| key.into_vec()), changed))
    }
}
