//! One temporary Cell executor for source constructor prefixes and selected
//! local blocks. Policies select source positions and account for their scope;
//! lookup, reuse, first-miss ownership and continuation share one implementation.
use super::*;

pub(crate) enum Start {
    Complete { cell: u32, frame: Cell },
    Resume { cell: u32, next_op: usize },
}

pub(crate) trait Prefix {
    #[cfg(feature = "sparse-cells")]
    const SEALED_INPUTS: bool;
    const RECORD_RECEIPTS: bool;
    fn next(&mut self, known: &mut crate::known_results::Stats) -> Option<usize>;
    fn enter(&mut self) {}
    fn reused(&mut self) {}
    fn union(&mut self, _changed: bool) {}
    fn finish(&mut self, _promoted: bool) {}
}

pub(crate) struct SourcePrefix<'a> {
    positions: std::ops::Range<usize>,
    aliases: Option<&'a [bool]>,
}
impl<'a> SourcePrefix<'a> {
    pub fn new(width: usize, aliases: Option<&'a [bool]>) -> Self {
        Self { positions: 0..width, aliases }
    }
}
impl Prefix for SourcePrefix<'_> {
    #[cfg(feature = "sparse-cells")]
    const SEALED_INPUTS: bool = true;
    const RECORD_RECEIPTS: bool = cfg!(feature = "structural-depth");
    fn next(&mut self, known: &mut crate::known_results::Stats) -> Option<usize> {
        for op in self.positions.by_ref() {
            if known.elide_static(self.aliases, op) { known.lazy_prefix_eliminated += 1; }
            else { return Some(op); }
        }
        None
    }
}

#[cfg(feature = "rhs-locals")]
pub(crate) struct LocalPrefix<'a> {
    plan: &'a crate::local_rhs::Block,
    stats: &'a mut crate::local_rhs::Counts,
    position: usize,
    lets: u64,
}
#[cfg(feature = "rhs-locals")]
impl<'a> LocalPrefix<'a> {
    pub fn new(plan: &'a crate::local_rhs::Block, stats: &'a mut crate::local_rhs::Counts) -> Self {
        Self { plan, stats, position: 0, lets: 0 }
    }
}
#[cfg(feature = "rhs-locals")]
impl Prefix for LocalPrefix<'_> {
    #[cfg(feature = "sparse-cells")]
    const SEALED_INPUTS: bool = false;
    const RECORD_RECEIPTS: bool = true;
    fn next(&mut self, known: &mut crate::known_results::Stats) -> Option<usize> {
        let step = self.plan.steps.get(self.position);
        let skipped = step.map_or(self.plan.trailing_aliases, |s| s.skip_before);
        known.static_eliminated += skipped;
        known.avoided_lookups += skipped;
        self.position += 1;
        step.map(|s| s.op)
    }
    fn enter(&mut self) { self.stats.enter += 1; }
    fn reused(&mut self) { self.lets += 1; self.stats.local_let_results += 1; }
    fn union(&mut self, changed: bool) {
        if changed { self.stats.ordered_unions += 1; }
        else { self.stats.no_op_unions += 1; }
    }
    fn finish(&mut self, promoted: bool) {
        if promoted {
            self.stats.promoted += 1;
            self.stats.prefix_lets_on_promotion += self.lets;
        } else {
            self.stats.local_complete += 1;
            self.stats.block_local_intermediates += self.plan.intermediate_ops.len() as u64;
        }
    }
}

impl Graph {
    /// Preserve one source Cell ID even on a full hit. A miss commits that
    /// same frame and returns the next original operation; no prefix is replayed.
    pub(crate) fn start_cell<P: Prefix>(&mut self, template: usize,
        values: crate::slots::Slots, parent: Option<FactRef>,
        receipts: &mut crate::cell::Effects, mut prefix: P,
        #[cfg(feature = "sparse-cells")] mut prepared: Option<(usize, &mut Option<FactRef>)>) -> Result<Start> {
        let cell = self.reserve_cell_id()?;
        #[cfg(feature = "sparse-cells")]
        if P::SEALED_INPUTS { self.trust_sealed_frame(cell); }
        let mut frame = self.new_cell(template, values, parent);
        let ops = self.program.templates[template].ops.clone();
        prefix.enter();
        while let Some(op) = prefix.next(&mut self.known_stats) {
            let instruction = &ops[op];
            let (table, args) = match instruction {
                Op::Copy(..) => continue,
                Op::Let(_, Call::Table(t), args) | Op::Set(t, args, _) => (*t, args),
                _ => return Err("unexpected operation in Cell constructor prefix".into()),
            };
            #[cfg(feature = "sparse-cells")]
            let witness = prepared.as_mut().filter(|(position,_)| *position == op).and_then(|(_,fact)| fact.take());
            #[cfg(not(feature = "sparse-cells"))]
            let witness = None;
            #[cfg(feature = "sparse-cells")]
            if let Some(witness) = witness
                && let Some(point) = self.sealed_constructor_result(cell, table, witness)? {
                let Op::Let(dst, ..) = instruction else { unreachable!("checked prepared constructor") };
                self.stats.constructor_requests += 1;
                frame.values.insert(*dst, point.value);
                self.stats.constructor_reused += 1;
                prefix.reused();
                if P::RECORD_RECEIPTS { receipts.record(op, point.witness); }
                continue;
            }
            let key: smallvec::SmallVec<[Value; 4]> = self.frame_arguments(cell, &frame, args)?;
            if matches!(instruction, Op::Let(..)) { self.stats.constructor_requests += 1; }
            let assigned = if let Op::Set(_, _, v) = instruction {
                Some(self.argument_in(cell, &frame, v)?)
            } else { None };
            if let Some(row) = self.lookup_prepared_constructor(table, &key, witness)? {
                let value = row.values.last().unwrap();
                match instruction {
                    Op::Let(dst, ..) => {
                        frame.values.insert(*dst, value.clone());
                        self.stats.constructor_reused += 1;
                        prefix.reused();
                    }
                    Op::Set(..) => {
                        let rhs = assigned.unwrap();
                        let changed = *value != rhs;
                        if changed { self.enqueue_union(value.clone(), rhs)?; }
                        prefix.union(changed);
                    }
                    _ => unreachable!(),
                }
                if P::RECORD_RECEIPTS { receipts.record(op, row.witness); }
            } else {
                self.store_cell(cell, frame);
                let fact = FactRef { cell, op: op as u32 };
                match instruction {
                    Op::Let(dst, ..) => { self.insert_constructor(cell, op, table, &key, *dst)?; }
                    Op::Set(..) => { self.activate(fact, table, &key, assigned.unwrap(), false)?; }
                    _ => unreachable!(),
                }
                if P::RECORD_RECEIPTS { receipts.record(op, Dependency::Fact(fact)); }
                prefix.finish(true);
                return Ok(Start::Resume { cell, next_op: op + 1 });
            }
        }
        prefix.finish(false);
        self.stats.rhs_frames_avoided += 1;
        Ok(Start::Complete { cell, frame })
    }
}
