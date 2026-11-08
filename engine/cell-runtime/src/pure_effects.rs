//! Source equalities are known; constructor equalities remain conservative.
//! Only displaced source roots start effects. Their unchanged peers contribute
//! outputs of the same operators through complete shared signal domains.
use super::*;
use smallvec::SmallVec;

pub(crate) struct Birth {
    pub table: usize,
    pub key: SmallVec<[Value; 4]>,
    pub output: u64,
}
#[derive(Default)]
pub(crate) struct Batch {
    pub pairs: SmallVec<[(u64, u64); 8]>,
    pub births: Vec<Birth>,
}
type Roots = SmallVec<[u64; 16]>;

struct Proof<'a> {
    graph: &'a Graph,
    batch: &'a Batch,
    counts: &'a mut Counts,
    before: u64,
    // This scratch relation contains only explicit source equalities, including
    // Set collisions in the sealed snapshot. It never proves congruence.
    parents: HashMap<u64, u64>,
    groups: HashMap<u64, Roots>,
}
fn cost(c: &Counts) -> u64 {
    visits(c) + c.pure_epoch_source_steps + c.pure_epoch_birth_checks + c.pure_epoch_order_checks
}
impl Proof<'_> {
    fn room(&self) -> bool {
        cost(self.counts) - self.before < MAX_VISITS
    }
    fn leader(&mut self, mut id: u64) -> Option<u64> {
        loop {
            if !self.room() {
                return None;
            }
            self.counts.pure_epoch_source_steps += 1;
            match self.parents.get(&id) {
                Some(&next) => id = next,
                None => return Some(id),
            }
        }
    }
    fn source_groups(&mut self) -> Option<()> {
        let mut roots = Roots::new();
        let mut seen = FxHashSet::default();
        for &(a, b) in &self.batch.pairs {
            let (a, b) = (self.leader(a)?, self.leader(b)?);
            if a == b {
                continue;
            }
            let before = self.parents.capacity();
            self.parents.insert(a.max(b), a.min(b));
            self.counts.scratch_growths += u64::from(before != self.parents.capacity());
            offer(a, &mut roots, &mut seen, self.counts);
            offer(b, &mut roots, &mut seen, self.counts);
        }
        for id in roots {
            let leader = self.leader(id)?;
            self.counts.pure_epoch_source_steps += 1;
            let before = self.groups.capacity();
            self.groups.entry(leader).or_default();
            self.counts.scratch_growths += u64::from(before != self.groups.capacity());
            let members = self.groups.get_mut(&leader).unwrap();
            let before = members.capacity();
            members.push(id);
            self.counts.scratch_growths += u64::from(before != members.capacity());
        }
        Some(())
    }
    fn boundary(&mut self, id: u64) -> Option<bool> {
        self.counts.root_visits += 1;
        for &dep in self.graph.uses.get(&id).into_iter().flat_map(|s| s.iter()) {
            if !self.room() {
                return None;
            }
            self.counts.legacy_boundaries += 1;
            if let Some(table) = self.graph.dependency_table(dep) {
                self.counts.pure_epoch_boundary_rejections += 1;
                *self
                    .counts
                    .pure_epoch_boundary_tables
                    .entry(table)
                    .or_default() += 1;
                return Some(false);
            }
        }
        Some(true)
    }
    fn preserves_order(&mut self, table: usize, forecast: &Forecast) -> bool {
        // Pure constructors still have ordered survivor selection. If a newer
        // epoch adds key tasks to an older unfinished closure, FactRef order
        // can retire a different witness than completing the epochs in order.
        // A shared sort alone is not a conflict; require an affected operator.
        let (ready, checks) = forecast.readiness(&[table]);
        self.counts.pure_epoch_order_checks += checks;
        if !ready {
            self.counts.pure_epoch_order_rejections += 1;
            *self
                .counts
                .pure_epoch_order_tables
                .entry(table)
                .or_default() += 1;
        }
        ready
    }
    /// A transient visitor, not an instance-owned consumer index. No table or
    /// operator bucket is scanned; every live site comes from shared wiring.
    fn outputs(
        &mut self,
        id: u64,
        mut use_output: impl FnMut(usize, u64, &mut Counts),
    ) -> Result<bool> {
        let runtime = self.graph.ownership.as_ref().unwrap();
        let plan = &self.graph.program.cell_ownership.composition;
        for signal in runtime
            .boundaries
            .get(&id)
            .into_iter()
            .flat_map(|s| s.iter().copied())
            .chain(self.graph.native_signal(id))
        {
            if !self.room() {
                return Ok(false);
            }
            self.counts.signal_visits += 1;
            let component = runtime.composition.components[signal.component as usize]
                .as_ref()
                .ok_or("expired pure-effect component")?;
            let Some(code) = plan.effects.get(component.shape) else {
                self.counts.pure_epoch_boundary_rejections += 1;
                return Ok(false);
            };
            for step in &code.signals[signal.symbol] {
                if !self.room() {
                    return Ok(false);
                }
                self.counts.static_steps += 1;
                let Some(output) = step.output else { continue };
                let fact = FactRef {
                    cell: component.frames[step.frame],
                    op: step.op,
                };
                let Some(state) = self
                    .graph
                    .cells
                    .get(&fact.cell)
                    .and_then(|c| c.facts.get(&fact.op))
                    .filter(|s| s.owned)
                else {
                    self.counts.inactive_steps += 1;
                    continue;
                };
                let stored = state
                    .ports
                    .as_ref()
                    .ok_or("pure effect requires stable ports")?;
                let output = component.signals[output].ok_or("unbound live effect output")?;
                self.counts.output_reads += 1;
                use_output(stored.table, root(&self.graph.parents, output), self.counts);
            }
        }
        // New Set sites are finite RHS-local data, discarded with this proof.
        for birth in &self.batch.births {
            for value in &birth.key {
                if !self.room() {
                    return Ok(false);
                }
                self.counts.pure_epoch_birth_checks += 1;
                if *value == Value::Eq(id) {
                    use_output(birth.table, birth.output, self.counts);
                    break;
                }
            }
        }
        Ok(true)
    }
    fn prove(&mut self, forecast: &Forecast) -> Result<Option<bool>> {
        if self.source_groups().is_none() {
            return Ok(None);
        }
        let mut roots = Roots::new();
        let mut seen = FxHashSet::default();
        // A new site can extend the older pending closure even without a new
        // source union. Only keys in that complete frontier expose its output.
        for birth in &self.batch.births {
            let mut exposed = false;
            for value in &birth.key {
                if let Value::Eq(id) = value {
                    for group in &forecast.groups {
                        if !self.room() {
                            return Ok(None);
                        }
                        self.counts.pure_epoch_birth_checks += 1;
                        if group.roots.as_ref().is_none_or(|s| s.contains(id)) {
                            exposed = true;
                            break;
                        }
                    }
                }
                if exposed {
                    break;
                }
            }
            if exposed {
                offer(birth.output, &mut roots, &mut seen, self.counts);
            }
        }
        // Borrow the groups separately so the wiring visitor can update counts.
        let groups = std::mem::take(&mut self.groups);
        for (&leader, members) in &groups {
            let mut operators = FxHashSet::default();
            let mut candidates = SmallVec::<[(usize, u64); 16]>::new();
            for &id in members {
                if !self.room() {
                    return Ok(None);
                }
                if id != leader {
                    self.counts.pure_epoch_displaced_roots += 1;
                    if self.boundary(id) != Some(true) {
                        return Ok(if self.room() { Some(false) } else { None });
                    }
                }
                if !self.outputs(id, |table, output, counts| {
                    counts.pure_epoch_peer_candidates += 1;
                    if id != leader {
                        let before = operators.capacity();
                        operators.insert(table);
                        counts.scratch_growths += u64::from(before != operators.capacity());
                    }
                    let before = candidates.capacity();
                    candidates.push((table, output));
                    counts.scratch_growths += u64::from(before != candidates.capacity());
                })? {
                    return Ok(None);
                }
            }
            // Overapproximate all key positions/scalar guards of an affected
            // operator. Both result endpoints are included, including peers
            // reached only through the unchanged input representative.
            for (table, output) in candidates {
                if !self.room() {
                    return Ok(None);
                }
                self.counts.pure_epoch_source_steps += 1;
                if operators.contains(&table) {
                    if !self.preserves_order(table, forecast) {
                        return Ok(Some(false));
                    }
                    offer(output, &mut roots, &mut seen, self.counts);
                }
            }
        }
        self.groups = groups;
        let mut next = 0;
        while next < roots.len() {
            if !self.room() {
                return Ok(None);
            }
            let id = roots[next];
            next += 1;
            match self.boundary(id) {
                Some(true) => (),
                other => return Ok(other),
            }
            // A constructor output may itself be an explicit union endpoint.
            // Close through the entire source class, including transitive pairs.
            let Some(leader) = self.leader(id) else {
                return Ok(None);
            };
            if let Some(members) = self.groups.get(&leader) {
                for &peer in members {
                    if !self.room() {
                        return Ok(None);
                    }
                    self.counts.pure_epoch_source_steps += 1;
                    offer(peer, &mut roots, &mut seen, self.counts);
                }
            }
            let mut order_ready = true;
            if !self.outputs(id, |table, output, counts| {
                let (ready, checks) = forecast.readiness(&[table]);
                counts.pure_epoch_order_checks += checks;
                if !ready {
                    counts.pure_epoch_order_rejections += 1;
                    *counts.pure_epoch_order_tables.entry(table).or_default() += 1;
                    order_ready = false;
                }
                offer(output, &mut roots, &mut seen, counts)
            })? {
                return Ok(None);
            }
            if !order_ready {
                return Ok(Some(false));
            }
        }
        Ok(Some(true))
    }
}
impl Graph {
    pub(crate) fn pure_epoch_closure(
        &mut self,
        batch: &Batch,
        forecast: &Forecast,
    ) -> Result<bool> {
        let mut counts = self
            .ownership
            .as_mut()
            .unwrap()
            .port_completion
            .take()
            .unwrap();
        counts.pure_epoch_proofs += 1;
        let before = cost(&counts);
        let boundaries = counts.pure_epoch_boundary_rejections;
        let result = Proof {
            graph: self,
            batch,
            counts: &mut counts,
            before,
            parents: HashMap::default(),
            groups: HashMap::default(),
        }
        .prove(forecast);
        counts.pure_epoch_peak_visits = counts.pure_epoch_peak_visits.max(cost(&counts) - before);
        match &result {
            Ok(Some(true)) => counts.pure_epoch_accepts += 1,
            Ok(None) if counts.pure_epoch_boundary_rejections == boundaries => {
                counts.pure_epoch_budget_rejections += 1;
            }
            _ => (),
        }
        self.ownership.as_mut().unwrap().port_completion = Some(counts);
        result.map(|proof| proof.unwrap_or(false))
    }
}
