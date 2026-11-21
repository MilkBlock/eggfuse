struct EffectBlock {
    template: usize,
    source: std::rc::Rc<Vec<Op>>,
    wired: std::rc::Rc<Vec<Op>>,
    // Source positions are authoritative even when an early constructor miss
    // promotes this Cell, or a Hide terminates a partially executed suffix.
    next: Vec<usize>,
    aliases_before: Vec<usize>,
    protected: Vec<usize>,
    rewrites: Vec<usize>,
}

impl EffectBlock {
    fn compile(program: &Program, rid: usize, rule: &Rule, fault: bool) -> Self {
        let template = &program.templates[rule.template];
        let ops = &template.ops;
        let mut definitions = std::collections::BTreeMap::<usize, Option<Arg>>::new();
        for op in ops.iter() {
            let (dst, source) = match op {
                Op::Copy(dst, a) => (*dst, Some(a.clone())),
                Op::Let(dst, _, _) => (*dst, None),
                _ => continue,
            };
            definitions
                .entry(dst)
                .and_modify(|v| *v = None)
                .or_insert(source);
        }
        for slot in rule.inputs.iter().chain(template.parent_columns.keys()) {
            definitions.remove(slot);
        }
        for atom in rule.query.iter() {
            for a in &atom.args {
                if let Arg::Slot(s) = a {
                    definitions.remove(s);
                }
            }
        }
        if let Some(known) = program.known_results.static_slots.get(rule.template) {
            for (i, value) in known.iter().enumerate() {
                if value.is_some() {
                    definitions.remove(&i);
                }
            }
        }
        let mut protected = std::collections::BTreeSet::new();
        let mut rewrites = vec![0; ops.len()];
        let mut wired = ops.as_ref().clone();
        for (i, op) in wired.iter_mut().enumerate() {
            let mut rewrite = |a: &mut Arg| {
                let mut v = a.clone();
                let mut chain = std::collections::BTreeSet::new();
                while let Arg::Slot(s) = v {
                    let Some(Some(next)) = definitions.get(&s) else {
                        break;
                    };
                    if !chain.insert(s) {
                        return;
                    }
                    v = next.clone();
                }
                if !chain.is_empty() {
                    rewrites[i] += 1;
                    protected.extend(chain);
                    *a = if fault {
                        Arg::Literal(Value::Int(-713197281))
                    } else {
                        v
                    };
                }
            };
            match op {
                Op::Let(_, _, args) | Op::Hide(_, args, _) => args.iter_mut().for_each(rewrite),
                Op::Set(_, args, value) => {
                    args.iter_mut().for_each(&mut rewrite);
                    rewrite(value);
                }
                Op::Union(a, b) => {
                    rewrite(a);
                    rewrite(b);
                }
                Op::Copy(..) | Op::Panic => {}
            }
        }
        let aliases = &program.known_results.static_skip[rid];
        let mut next = vec![ops.len(); ops.len() + 1];
        let mut aliases_before = vec![0];
        for (i, flag) in aliases.iter().enumerate() {
            aliases_before.push(aliases_before[i] + usize::from(*flag));
        }
        for i in (0..ops.len()).rev() {
            next[i] = if aliases[i] || matches!(ops[i], Op::Copy(..)) {
                next[i + 1]
            } else {
                i
            };
        }
        Self {
            template: rule.template,
            source: ops.clone(),
            wired: std::rc::Rc::new(wired),
            next,
            aliases_before,
            protected: protected.into_iter().collect(),
            rewrites,
        }
    }

    fn ops(&self, wired: bool) -> std::rc::Rc<Vec<Op>> {
        if wired {
            self.wired.clone()
        } else {
            self.source.clone()
        }
    }
}

#[derive(Default, serde::Serialize)]
struct EffectWork {
    plans: u64,
    static_live_ops: u64,
    static_copy_positions: u64,
    static_rewired_operands: u64,
    groups: u64,
    group_rows: u64,
    multirow_groups: u64,
    multirow_bindings: u64,
    constructor_calls: u64,
    dynamic_calls: u64,
    dispatched: u64,
    skipped_copies: u64,
    static_skips: u64,
    rewired_occurrences: u64,
    materialized_copy_conflicts: u64,
}
#[derive(Default)]
struct BlockRuntime {
    fault: bool,
    mode: u8,
    by_rule: std::collections::BTreeMap<usize, [u64; 4]>,
    plans: Vec<Option<std::rc::Rc<EffectBlock>>>,
    work: EffectWork,
}
struct EffectPositions<'a> {
    block: &'a EffectBlock,
    work: &'a mut EffectWork,
    pos: usize,
    wired: bool,
}
impl EffectPositions<'_> {
    fn advance(&mut self, known: &mut crate::known_results::Stats, prefix: bool) -> Option<usize> {
        let i = self.block.next[self.pos];
        let skipped = self.block.aliases_before[i] - self.block.aliases_before[self.pos];
        self.work.skipped_copies += (i - self.pos - skipped) as u64;
        self.work.static_skips += skipped as u64;
        known.static_eliminated += skipped as u64;
        known.avoided_lookups += skipped as u64;
        if prefix {
            known.lazy_prefix_eliminated += skipped as u64;
        }
        if i == self.block.source.len() {
            return None;
        }
        self.pos = i + 1;
        self.work.dispatched += 1;
        if self.wired {
            self.work.rewired_occurrences += self.block.rewrites[i] as u64;
        }
        Some(i)
    }
}
impl crate::graph::cell_prefix::Prefix for EffectPositions<'_> {
    #[cfg(feature = "sparse-cells")]
    const SEALED_INPUTS: bool = true;
    const RECORD_RECEIPTS: bool = cfg!(feature = "structural-depth");
    fn next(&mut self, known: &mut crate::known_results::Stats) -> Option<usize> {
        self.advance(known, true)
    }
}
impl Executor {
    pub fn configure_effect_blocks(&mut self, mode: u64, audit: bool, fault: bool) -> Result<()> {
        if !(1..=2).contains(&mode) {
            return Err("invalid ordered block mode".into());
        }
        if fault && !audit {
            return Err("wire corruption requires source audit".into());
        }
        self.effect_blocks.fault = fault;
        self.graph.effect_operand_audit = audit;
        self.effect_blocks.mode = mode as u8;
        Ok(())
    }
    fn block_for_group(&mut self, rid: usize, n: usize) -> Option<Rc<EffectBlock>> {
        if self.effect_blocks.mode == 0 || n == 0 {
            return None;
        }
        let p = &self.graph.program;
        self.effect_blocks.work.groups += 1;
        self.effect_blocks.work.group_rows += n as u64;
        if n >= 2 {
            self.effect_blocks.work.multirow_groups += 1;
            self.effect_blocks.work.multirow_bindings += n as u64;
        }
        let plans = &mut self.effect_blocks.plans;
        if plans.len() <= rid {
            plans.resize_with(rid + 1, || None);
        }
        if plans[rid].is_none() {
            let b = EffectBlock::compile(p, rid, &p.rules[rid], self.effect_blocks.fault);
            self.effect_blocks.work.plans += 1;
            self.effect_blocks.work.static_live_ops +=
                (0..b.source.len()).filter(|&i| b.next[i] == i).count() as u64;
            self.effect_blocks.work.static_copy_positions += b
                .source
                .iter()
                .filter(|op| matches!(op, Op::Copy(..)))
                .count() as u64;
            self.effect_blocks.work.static_rewired_operands +=
                b.rewrites.iter().sum::<usize>() as u64;
            plans[rid] = Some(Rc::new(b));
        }
        plans[rid].clone()
    }
    fn group_effect_counts(&self) -> [u64; 4] {
        let w = &self.effect_blocks.work;
        [
            w.dispatched,
            w.skipped_copies,
            w.static_skips,
            w.rewired_occurrences,
        ]
    }
    fn save_group_counts(&mut self, rid: usize, before: [u64; 4]) {
        let now = self.group_effect_counts();
        let dest = self.effect_blocks.by_rule.entry(rid).or_default();
        for i in 0..4 {
            dest[i] += now[i] - before[i];
        }
    }
    pub fn ordered_block_report(&self) -> serde_json::Value {
        {
            let mut report = serde_json::json!(self.effect_blocks.work);
            report["by_rule"] = json!(self.effect_blocks.by_rule);
            report["audited_fields"] = json!(self.graph.effect_audit_fields.get());
            report
        }
    }
}
