use super::*;
use crate::{cell::Access, row_kernel::Kernel};
use smallvec::SmallVec;

#[cfg(feature = "sparse-cells")]
pub(super) struct SumDomain {
    version: u64,
    source: Rc<Vec<Dependency>>,
    groups: Option<rustc_hash::FxHashMap<i64, Rc<Vec<Dependency>>>>,
}
#[cfg(feature = "sparse-cells")]
impl SumDomain {
    fn select(exec: &mut Executor, site: (usize,usize), table: usize, left: usize, right: usize,
        target: i64, refs: Rc<Vec<Dependency>>) -> Result<Rc<Vec<Dependency>>> {
        let version = exec.graph.query_versions[table];
        let entry = exec.sum_domains.entry(site);
        use std::collections::hash_map::Entry;
        let slot = match entry {
            Entry::Occupied(e) if e.get().version == version && Rc::ptr_eq(&e.get().source, &refs) => e.into_mut(),
            other => {
                other.insert_entry(Self { version, source: refs.clone(), groups: None });
                return Ok(refs);
            }
        };
        if slot.groups.is_none() {
            let mut groups = rustc_hash::FxHashMap::<i64, Vec<Dependency>>::default();
            for &w in refs.iter() {
                exec.graph.stats.sum_index_reads += 1;
                let Some(row) = exec.graph.row(w)? else { continue };
                if row.hidden || row.table != table { continue; }
                let (Value::Int(a), Value::Int(b)) = (&row.values[left], &row.values[right]) else {
                    return Ok(refs);
                };
                if let Some(sum) = a.checked_add(*b) { groups.entry(sum).or_default().push(w); }
            }
            slot.groups = Some(groups.into_iter().map(|(k,v)| (k, Rc::new(v))).collect());
        }
        let subset = slot.groups.as_ref().unwrap().get(&target).cloned().unwrap_or_default();
        exec.graph.stats.sum_index_skips += (refs.len() - subset.len()) as u64;
        Ok(subset)
    }
}
pub(super) struct Registers {
    fields: Vec<Value>,
    witnesses: Vec<Option<Dependency>>,
}
impl Registers {
    fn producer_context(
        graph: &mut Graph,
        witness: Dependency,
        cache: &mut Option<Option<crate::graph::producer::Context>>,
    ) -> Option<crate::graph::producer::Context> {
        *cache.get_or_insert_with(|| {
            graph.stats.register_prefix.context_reads += 1;
            graph.continuation_context(witness)
        })
    }
    pub(super) fn new(r: &Rule) -> Self {
        Self {
            fields: vec![Value::Int(0); r.inputs.iter().copied().max().map_or(0, |s| s + 1)],
            witnesses: vec![None; r.query.len()],
        }
    }
    fn val(&self, a: &Arg, g: &Graph) -> Value {
        match a {
            Arg::Slot(s) => self.fields[*s].clone(),
            Arg::Literal(v) => canon(v, &g.parents),
        }
    }
    fn agrees(&self, a: &Arg, v: &Value, g: &Graph) -> bool {
        match a {
            Arg::Slot(s) => self.fields[*s] == *v,
            Arg::Literal(l) => canon(l, &g.parents) == *v,
        }
    }
    pub(super) fn start<const LOCAL: bool>(
        &mut self,
        exec: &mut Executor,
        rid: usize,
        r: &Rule,
        k: &Kernel,
        entry: &crate::entry_schedule::Seed,
        domains: &[Subtrie],
        known: &QueryFacts,
        out: &mut Vec<Binding>,
    ) -> Result<()> {
        exec.graph.stats.register_seeds += 1;
        let seed = &entry.packet.row;
        self.witnesses[k.pivot] = Some(seed.witness);
        for &(c, s) in &k.seed {
            self.fields[s] = seed.values[c].clone();
        }
        let (pc, epoch) = if k.prefixes.is_empty() {
            (0, seed.epoch)
        } else {
            let Some(resume) = self.prefix(exec, r, k, entry)? else { return Ok(()) };
            resume
        };
        self.step::<LOCAL>(
            exec,
            rid,
            r,
            k,
            pc,
            (seed.epoch, seed.witness),
            epoch,
            domains,
            known,
            out,
        )
    }
    /// Consume only a statically checked complete-key prefix. Reading an old
    /// producer is not a liveness proof: failure resumes this exact instruction
    /// through the ordinary matcher instead of rejecting its candidate.
    fn prefix(
        &mut self,
        exec: &mut Executor,
        r: &Rule,
        k: &Kernel,
        supplied: &crate::entry_schedule::Seed,
    ) -> Result<Option<(usize, u64)>> {
        exec.graph.stats.register_prefix.eligible_seeds += 1;
        let seed = &supplied.packet.row;
        let mut context = None;
        #[cfg(feature = "iterative-bake")]
        let entry = {
            #[cfg(feature = "sparse-cells")]
            let direct = exec.entry_schedule.owns_publications(seed.table);
            #[cfg(not(feature = "sparse-cells"))]
            let direct = false;
            exec.graph.stats.register_prefix.entry_publication_reads += u64::from(direct);
            exec.graph.stats.register_prefix.publication_probes += u64::from(!direct);
            exec.stage_spine.cell_results(&exec.entry_schedule, supplied)
        };
        #[cfg(feature = "iterative-bake")]
        let published = entry.map(|(r, op, _)| (exec.graph.program.rules[r].template, op));
        #[cfg(not(feature = "iterative-bake"))]
        let published: Option<(usize, usize)> = None;
        let Some(address) = published.or_else(|| Self::producer_context(&mut exec.graph, seed.witness, &mut context)
            .map(|c| (c.template, c.op))) else {
            exec.graph.stats.register_prefix.context_missing += 1;
            return Ok(Some((0, seed.epoch)));
        };
        exec.graph.stats.register_prefix.plan_lookups += 1;
        let Ok(plan) = k.prefixes.binary_search_by_key(
            &address, |p| {
                exec.graph.stats.register_prefix.plan_comparisons += 1;
                (p.template, p.publication)
            },
        ) else { return Ok(Some((0, seed.epoch))) };
        exec.graph.stats.register_prefix.plan_hits += 1;
        let mut epoch = seed.epoch;
        let owner = (seed.epoch, seed.witness);
        let mut pc = 0;
        for (ins, effect) in k.steps.iter().zip(&k.prefixes[plan].effects) {
            let a = &r.query[ins.atom];
            let result = match (&a.call, effect) {
                (Call::Table(table), Some(source)) => {
                    exec.graph.stats.register_prefix.donor_reads += 1;
                    #[cfg(feature = "iterative-bake")]
                    let receipt = source.port.and_then(|port| entry.and_then(|(_, _, results)| {
                        exec.graph.stats.register_prefix.receipt_probes += 1;
                        exec.graph.stats.register_prefix.receipt_slot_reads += 1;
                        results.and_then(|results| results.get(port))
                    }));
                    #[cfg(not(feature = "iterative-bake"))]
                    let receipt = None;
                    exec.graph.stats.register_prefix.receipt_hits += u64::from(receipt.is_some());
                    // An Entry's actual result needs no recovery of the Cell
                    // physically owning its anchor. Only the uncovered local
                    // effect fallback needs that context, and at most once.
                    let physical = if receipt.is_none()
                        && matches!(source.source, crate::cell::Site::Effect(_)) {
                        Self::producer_context(&mut exec.graph, seed.witness, &mut context)
                            .filter(|c| (c.template, c.op) == address)
                    } else { None };
                    let mut misses = std::mem::take(&mut exec.graph.stats.register_prefix.misses);
                    let mut reads = 0;
                    let row = exec.graph.context_witness_row(physical, source.source, receipt,
                        *table, a.args.len(), &mut misses, &mut reads)?;
                    exec.graph.stats.register_prefix.row_reads += reads;
                    exec.graph.stats.register_prefix.misses = misses;
                    let Some(row) = row else {
                        exec.graph.stats.register_prefix.stale_fallbacks += 1;
                        break;
                    };
                    let keys_match = a.args[..a.args.len() - 1].iter()
                        .zip(row.values.iter()).all(|(arg, value)| {
                            exec.graph.stats.register_prefix.field_checks += 1;
                            exec.graph.stats.register_prefix.key_fields += 1;
                            self.agrees(arg, value, &exec.graph)
                        });
                    if !keys_match {
                        exec.graph.stats.register_prefix.key_fallbacks += 1;
                        exec.graph.stats.register_prefix.misses.key += 1;
                        break;
                    }
                    exec.graph.stats.register_prefix.donor_hits += 1;
                    exec.graph.stats.register_prefix.key_reads_avoided += 1;
                    let stamp = (row.epoch, row.witness);
                    if stamp > owner || (stamp == owner && ins.atom < k.pivot) {
                        exec.graph.stats.register_prefix.owner_rejections += 1;
                        return Ok(None);
                    }
                    epoch = epoch.max(row.epoch);
                    self.witnesses[ins.atom] = Some(row.witness);
                    row.values.last().unwrap().clone()
                }
                (Call::Primitive(name, sort), None) => {
                    exec.graph.stats.register_prefix.primitive_checks += 1;
                    if name.starts_with("cell-key-") { exec.graph.stats.key_operations += 1; }
                    let args: SmallVec<[Value; 4]> = a.args[..a.args.len() - 1].iter()
                        .map(|arg| self.val(arg, &exec.graph)).collect();
                    let Some(value) = value::primitive(name, &args, sort, exec.graph.program.key_nodes())?
                    else {
                        exec.graph.stats.register_prefix.primitive_rejections += 1;
                        return Ok(None);
                    };
                    value
                }
                _ => unreachable!("validated register prefix instruction"),
            };
            if let Some((_, arg)) = ins.check.first() {
                exec.graph.stats.register_prefix.field_checks += 1;
                if !self.agrees(arg, &result, &exec.graph) {
                    exec.graph.stats.register_prefix.result_rejections += 1;
                    return Ok(None);
                }
            }
            if let Some(&(_, slot)) = ins.assign.first() {
                exec.graph.stats.register_prefix.field_writes += 1;
                self.fields[slot] = result;
            }
            pc += 1;
        }
        if pc != 0 {
            exec.graph.stats.register_prefix.resumes += 1;
            exec.graph.stats.register_prefix.resumed_instructions += pc as u64;
        }
        Ok(Some((pc, epoch)))
    }
    fn step<const LOCAL: bool>(
        &mut self,
        exec: &mut Executor,
        rid: usize,
        r: &Rule,
        k: &Kernel,
        pc: usize,
        owner: (u64, Dependency),
        mut epoch: u64,
        domains: &[Subtrie],
        known: &QueryFacts,
        out: &mut Vec<Binding>,
    ) -> Result<()> {
        for (offset, ins) in k.steps[pc..].iter().enumerate() {
            let a = &r.query[ins.atom];
            let keys = &a.args[..a.args.len() - 1];
            if let Access::Expand = ins.access {
                let Call::Table(t) = a.call else {
                    unreachable!()
                };
                let refs = if let Some(domain) = domains.iter().find(|d| d.atom == ins.atom) {
                    domain.rows.clone()
                } else {
                    let mut bound = smallvec::smallvec![None; a.args.len()];
                    for (col, arg) in &ins.bound {
                        bound[*col] = Some(self.val(arg, &exec.graph));
                    }
                    let bound: SmallVec<[Option<Value>; 6]> = bound;
                    exec.query_indexes.candidates(&exec.graph, t, &bound)?
                };
                #[cfg(feature = "sparse-cells")]
                let refs = if !LOCAL && refs.len() >= 8 && refs.len() <= 65536
                    && let Some((atom, left, right, target)) = &k.sum_filter
                    && *atom == ins.atom
                    && let Value::Int(value) = self.val(target, &exec.graph) {
                    SumDomain::select(exec, (rid, k.pivot), t, *left, *right, value, refs)?
                } else { refs };
                let mut access = if LOCAL {
                    exec.neighbor.neighborhood(&exec.graph, rid, t, &refs)
                } else {
                    crate::neighbor::Access::Direct
                };
                let mut visit = |row: &Row, exec: &mut Executor| -> Result<()> {
                    let w = row.witness;
                    if LOCAL {
                        exec.neighbor.stats(rid).expansion_visits += 1;
                    }
                    exec.graph.stats.residual_candidates += 1;
                    // Repeated fresh variables compare against this row's first column.
                    for &(col, s) in &ins.assign {
                        self.fields[s] = row.values[col].clone();
                    }
                    if !ins
                        .check
                        .iter()
                        .all(|(col, arg)| self.agrees(arg, &row.values[*col], &exec.graph))
                    {
                        return Ok(());
                    }
                    self.witnesses[ins.atom] = Some(w);
                    self.step::<LOCAL>(
                        exec,
                        rid,
                        r,
                        k,
                        pc + offset + 1,
                        owner,
                        epoch.max(row.epoch),
                        domains,
                        known,
                        out,
                    )
                };
                if let crate::neighbor::Access::Cached(rows) = access {
                    let count = rows.partition_point(|row| {
                        let stamp = (row.epoch, row.witness);
                        stamp < owner || (stamp == owner && ins.atom >= k.pivot)
                    });
                    let stats = exec.neighbor.stats(rid);
                    stats.owner_skips += (rows.len() - count) as u64;
                    stats.cached_parent_visits += count as u64;
                    for row in &rows[..count] {
                        visit(row, exec)?;
                    }
                } else {
                    for &w in refs.iter() {
                        let Some(row) = exec.graph.row(w)? else {
                            exec.graph.stats.residual_candidates += 1;
                            if LOCAL {
                                exec.neighbor.stats(rid).expansion_visits += 1;
                            }
                            continue;
                        };
                        if let crate::neighbor::Access::Build(rows) = &mut access
                            && !row.hidden
                            && row.table == t
                        {
                            let clock = exec.profile_queries.then(Instant::now);
                            rows.push(row.clone());
                            if let Some(clock) = clock {
                                exec.neighbor.stats(rid).maintenance_ns +=
                                    clock.elapsed().as_nanos() as u64;
                            }
                        }
                        let stamp = (row.epoch, w);
                        if row.hidden
                            || row.table != t
                            || stamp > owner
                            || (stamp == owner && ins.atom < k.pivot)
                        {
                            exec.graph.stats.residual_candidates += 1;
                            if LOCAL {
                                exec.neighbor.stats(rid).expansion_visits += 1;
                            }
                            continue;
                        }
                        visit(&row, exec)?;
                    }
                    if let crate::neighbor::Access::Build(rows) = access {
                        exec.neighbor.finish_group(rid, t, refs, rows);
                    }
                }
                return Ok(());
            }
            let args: SmallVec<[Value; 4]> =
                keys.iter().map(|arg| self.val(arg, &exec.graph)).collect();
            let result = match &a.call {
                Call::Table(t) => {
                    let neighbor = LOCAL && !exec.graph.program.tables[*t].virtual_fact;
                    let row = if neighbor {
                        exec.neighbor.point(&mut exec.graph, rid, *t, &args)?
                    } else {
                        exec.graph.stats.residual_candidates += 1;
                        #[cfg(feature = "sparse-cells")]
                        { exec.point_ports.read(&mut exec.graph, *t, &args)? }
                        #[cfg(not(feature = "sparse-cells"))]
                        { exec.graph.lookup_canonical(*t, &args)? }
                    };
                    let Some(row) = row else {
                        return Ok(());
                    };
                    let stamp = (row.epoch, row.witness);
                    if row.hidden || stamp > owner || (stamp == owner && ins.atom < k.pivot) {
                        return Ok(());
                    }
                    epoch = epoch.max(row.epoch);
                    self.witnesses[ins.atom] = Some(row.witness);
                    row.values.last().unwrap().clone()
                }
                Call::Primitive(name, sort) => {
                    if name.starts_with("cell-key-") {
                        exec.graph.stats.key_operations += 1;
                    }
                    let Some(v) =
                        value::primitive(name, &args, sort, exec.graph.program.key_nodes())?
                    else {
                        return Ok(());
                    };
                    v
                }
            };
            if let Some((_, arg)) = ins.check.first()
                && !self.agrees(arg, &result, &exec.graph)
            {
                return Ok(());
            }
            if let Some(&(_, s)) = ins.assign.first() {
                self.fields[s] = result;
            }
        }
        let mut facts = known.clone();
        if !matches!(facts, QueryFacts::None) {
            for (i, &w) in self.witnesses.iter().enumerate() {
                facts.record(i, w);
            }
        }
        exec.graph.stats.register_answers += 1;
        out.push(Binding {
            #[cfg(feature = "view-consumers")]
            view_source: None,
            #[cfg(feature = "iterative-bake")]
            direct: None,
            known: facts,
            values: r
                .inputs
                .iter()
                .map(|s| (*s, self.fields[*s].clone()))
                .collect(),
            epoch,
            parent: None,
            continuation: None,
            compiled: true,
        });
        Ok(())
    }
}
