use super::*;
use crate::row_kernel::Kernel;
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
pub(super) struct Frame {
    results: Vec<Value>,
    witnesses: Vec<Option<Dependency>>,
}
impl Frame {
    pub(super) fn new(r: &Rule) -> Self {
        Self {
            results: vec![Value::Int(0); r.query.len().saturating_sub(1)],
            witnesses: vec![None; r.query.len()],
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
        let (pc, epoch) = if k.routes.is_none() {
            (0, seed.epoch)
        } else {
            let Some(resume) = self.prefix(exec, k, entry)? else { return Ok(()) };
            resume
        };
        self.step::<LOCAL>(
            exec,
            rid,
            r,
            k,
            pc,
            seed,
            None,
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
        k: &Kernel,
        supplied: &crate::entry_schedule::Seed,
    ) -> Result<Option<(usize, u64)>> {
        exec.graph.stats.register_prefix.eligible_seeds += 1;
        let seed = &supplied.packet.row;
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
        let mut producer = crate::cell::Producer::new(seed.witness, published);
        let mut context_reads = 0;
        let address = producer.address(&exec.graph, &mut context_reads);
        exec.graph.stats.register_prefix.context_reads += context_reads;
        let Some(address) = address else {
            exec.graph.stats.register_prefix.context_missing += 1;
            return Ok(Some((0, seed.epoch)));
        };
        exec.graph.stats.register_prefix.plan_lookups += 1;
        let Some(source) = exec.graph.program.multi_stage.routes.source(address.0, address.1)
            else { return Ok(Some((0, seed.epoch))) };
        let (route, indexed, comparisons) = k.routes.as_ref().unwrap().lookup(source);
        exec.graph.stats.register_prefix.plan_index_probes += indexed;
        exec.graph.stats.register_prefix.plan_comparisons += comparisons;
        let Some(route) = route.filter(|r| r.prefix_len != 0)
            else { return Ok(Some((0, seed.epoch))) };
        exec.graph.stats.register_prefix.plan_hits += 1;
        let mut epoch = seed.epoch;
        let owner = (seed.epoch, seed.witness);
        let mut pc = 0;
        for ins in k.query.steps.iter().take(route.prefix_len) {
            let result = match &ins.call {
                Call::Table(table) => {
                    exec.graph.stats.register_prefix.source_index_probes += 1;
                    let source = route.witness(ins.atom).expect("validated Cell prefix donor");
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
                    let mut misses = std::mem::take(&mut exec.graph.stats.register_prefix.misses);
                    let (mut reads, mut context_reads) = (0, 0);
                    let row = producer.row(&exec.graph, source.source, receipt,
                        *table, ins.key.len() + 1, &mut misses, &mut context_reads, &mut reads)?;
                    exec.graph.stats.register_prefix.context_reads += context_reads;
                    exec.graph.stats.register_prefix.row_reads += reads;
                    exec.graph.stats.register_prefix.misses = misses;
                    let Some(row) = row else {
                        exec.graph.stats.register_prefix.stale_fallbacks += 1;
                        break;
                    };
                    let keys_match = ins.key.iter()
                        .zip(row.values.iter()).all(|(arg, value)| {
                            exec.graph.stats.register_prefix.field_checks += 1;
                            exec.graph.stats.register_prefix.key_fields += 1;
                            arg.agrees(value, &exec.graph, seed, &self.results, None)
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
                Call::Primitive(name, sort) => {
                    exec.graph.stats.register_prefix.primitive_checks += 1;
                    if name.starts_with("cell-key-") { exec.graph.stats.key_operations += 1; }
                    let args: SmallVec<[Value; 4]> = ins.key.iter()
                        .map(|arg| arg.read(&exec.graph, seed, &self.results, None)).collect();
                    let Some(value) = value::primitive(name, &args, sort, exec.graph.program.key_nodes())?
                    else {
                        exec.graph.stats.register_prefix.primitive_rejections += 1;
                        return Ok(None);
                    };
                    value
                }
            };
            if let Some(arg) = &ins.check_result {
                exec.graph.stats.register_prefix.field_checks += 1;
                if !arg.agrees(&result, &exec.graph, seed, &self.results, None) {
                    exec.graph.stats.register_prefix.result_rejections += 1;
                    return Ok(None);
                }
            }
            if ins.check_result.is_none() {
                exec.graph.stats.register_prefix.field_writes += 1;
                exec.graph.stats.register_result_writes += 1;
                self.results[pc] = result;
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
        seed: &Row,
        expanded: Option<(usize, &Row)>,
        owner: (u64, Dependency),
        mut epoch: u64,
        domains: &[Subtrie],
        known: &QueryFacts,
        out: &mut Vec<Binding>,
    ) -> Result<()> {
        for (position, ins) in k.query.steps.iter().enumerate().skip(pc) {
            if let Some(expansion) = &ins.expansion {
                let Call::Table(t) = ins.call else {
                    unreachable!()
                };
                let refs = if let Some(domain) = domains.iter().find(|d| d.atom == ins.atom) {
                    domain.rows.clone()
                } else {
                    let mut bound = smallvec::smallvec![None; expansion.width];
                    for (col, arg) in &expansion.bound {
                        bound[*col] = Some(arg.read(&exec.graph, seed, &self.results, expanded));
                    }
                    let bound: SmallVec<[Option<Value>; 6]> = bound;
                    exec.query_indexes.candidates(&exec.graph, t, &bound)?
                };
                #[cfg(feature = "sparse-cells")]
                let refs = if !LOCAL && refs.len() >= 8 && refs.len() <= 65536
                    && let Some((atom, left, right, target)) = &k.sum_filter
                    && *atom == ins.atom
                    && let Value::Int(value) = target.read(&exec.graph, seed, &self.results, expanded) {
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
                    exec.graph.stats.register_expansion_rows += 1;
                    // Repeated fresh variables refer to this row's first
                    // occurrence directly; no assignments or undo log.
                    if !expansion.checks.iter().all(|(col, arg)| {
                        arg.agrees(&row.values[*col], &exec.graph, seed, &self.results, Some((position, row)))
                    }) { return Ok(()); }
                    self.witnesses[ins.atom] = Some(w);
                    self.step::<LOCAL>(
                        exec,
                        rid,
                        r,
                        k,
                        position + 1,
                        seed,
                        Some((position, row)),
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
            let bound = ins.bind::<SmallVec<[Value; 4]>>(|arg| arg.operand(&exec.graph, seed, &self.results, expanded));
            let result = bound.evaluate(|args| match &ins.call {
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
                        return Ok(None);
                    };
                    let stamp = (row.epoch, row.witness);
                    if row.hidden || stamp > owner || (stamp == owner && ins.atom < k.pivot) {
                        return Ok(None);
                    }
                    epoch = epoch.max(row.epoch);
                    self.witnesses[ins.atom] = Some(row.witness);
                    Ok(Some(row.values.last().unwrap().clone()))
                }
                Call::Primitive(name, sort) => {
                    if name.starts_with("cell-key-") {
                        exec.graph.stats.key_operations += 1;
                    }
                    let Some(v) =
                        value::primitive(name, &args, sort, exec.graph.program.key_nodes())?
                    else {
                        return Ok(None);
                    };
                    Ok(Some(v))
                }
            })?;
            let Some(result) = result else { return Ok(()); };
            if ins.check_result.is_none() {
                exec.graph.stats.register_result_writes += 1;
                self.results[position] = result;
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
            values: r.inputs.iter().zip(&k.query.inputs)
                .map(|(s, field)| (*s, field.read(&exec.graph, seed, &self.results, expanded)))
                .collect(),
            epoch,
            parent: None,
            continuation: None,
            compiled: true,
        });
        Ok(())
    }
}
