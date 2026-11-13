//! Offline possible-operator closure. A certificate covers immutable body uses
//! and every admitted Entry substitution. It never proves equality or liveness.
use super::*;

const SCHEMA: &str = "eggfuse-query-classes/v1";
const MAX_WORDS: usize = 1_048_576;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Plan {
    schema: String,
    /// Class 0 accepts all operators. Other masks are interned dense bitsets.
    masks: Vec<Vec<u64>>,
    /// Concrete shared code -> local port symbol -> immutable class.
    pub symbols: Vec<Vec<u32>>,
}

fn code_groups(plan: &super::Plan) -> Vec<Vec<usize>> {
    let mut groups = vec![Vec::new(); plan.programs.len()];
    for marker in &plan.markers {
        if !groups[marker.program_id].contains(&marker.code) {
            groups[marker.program_id].push(marker.code);
        }
    }
    groups
}

/// Shape interning deliberately forgets concrete operator identity. Cover all
/// codes of the source layout, constrained only by the actual checked Entry.
fn edges(p: &Program, plan: &super::Plan, mut visit: impl FnMut((usize, usize), (usize, usize))) {
    // A dual-source takeover introduces aliases between complete old Shapes.
    // Propagate possible uses both ways before choosing any runtime origin class.
    for join in &plan.composition.joins {
        let mut origins=vec![None;join.shape.signals.len()];
        for (component,(shape,codes)) in join.pattern.components.iter().enumerate() {
            for (symbol,&(frame,local)) in plan.composition.shapes[*shape].origins.iter().enumerate() {
                let node=(codes[frame],local);let target=join.symbol_maps[component][symbol];
                if let Some(first)=origins[target] {visit(first,node);visit(node,first);} else {origins[target]=Some(node);}
            }
        }
    }
    let groups = code_groups(plan);
    for (key, _) in &plan.composition.transitions {
        let hop = &key.hop;
        let rule = &p.rules[hop.rule];
        let table = if let Some(&atom)=plan.entries[hop.rule].get(hop.entry) {
            let Call::Table(table)=rule.query[atom].call else {continue;};table
        } else {
            let operation=hop.entry-plan.entries[hop.rule].len();
            let Some(Op::Let(_,Call::Table(table),_))=p.templates[rule.template].ops.get(operation) else {continue;};
            if !p.tables[*table].constructor {continue;}*table
        };
        let program = plan.composition.shapes[key.shape].programs[hop.source_frame];
        let receiver = plan.markers[rule.template].code;
        for &code in &groups[program] {
            if plan.code_operators[code].get(hop.op as usize) != Some(&table) {
                continue;
            }
            for source in plan.composition.sources[hop.rule]
                .iter()
                .filter(|s| s.entry == hop.entry)
            {
                let local = plan.programs[program].fields[hop.op as usize][source.column]
                    .expect("checked substitution field");
                visit((code, local), (receiver, source.symbol));
            }
        }
    }
}

fn close(masks: &mut [Vec<u64>], incoming: &[BTreeSet<usize>]) {
    let mut pending = (0..masks.len()).collect::<std::collections::VecDeque<_>>();
    let mut queued = vec![true; masks.len()];
    while let Some(target) = pending.pop_front() {
        queued[target] = false;
        for &source in &incoming[target] {
            let mut changed = false;
            for word in 0..masks[target].len() {
                let value = masks[source][word] | masks[target][word];
                changed |= value != masks[source][word];
                masks[source][word] = value;
            }
            if changed && !queued[source] {
                queued[source] = true;
                pending.push_back(source);
            }
        }
    }
}

impl Plan {
    fn all(plan: &super::Plan) -> Self {
        Self {
            schema: SCHEMA.into(),
            masks: vec![vec![]],
            symbols: plan
                .code_programs
                .iter()
                .map(|p| vec![0; p.signals.len()])
                .collect(),
        }
    }
    pub(super) fn bake(p: &Program, plan: &super::Plan) -> Self {
        let mut offsets = vec![0];
        for program in &plan.code_programs {
            offsets.push(offsets.last().unwrap() + program.signals.len());
        }
        let nodes = *offsets.last().unwrap();
        let width = p.tables.len().div_ceil(64);
        // A budget cut accepts all operators; it must never truncate a proof.
        if nodes.saturating_mul(width.max(1)) > MAX_WORDS {
            return Self::all(plan);
        }
        let mut masks = vec![vec![0u64; width]; nodes];
        for (code, program) in plan.code_programs.iter().enumerate() {
            for (symbol, steps) in program.signals.iter().enumerate() {
                for step in steps {
                    let table = plan.code_operators[code][step.op as usize];
                    masks[offsets[code] + symbol][table / 64] |= 1 << (table % 64);
                }
            }
        }
        // Bake-only reverse edges support the fixed point, including cycles.
        // These are code vertices; no runtime instance gets a consumer list.
        let mut incoming = vec![BTreeSet::new(); nodes];
        edges(p, plan, |(a, x), (b, y)| {
            incoming[offsets[b] + y].insert(offsets[a] + x);
        });
        close(&mut masks, &incoming);
        let mut result = Self::all(plan);
        let mut intern = BTreeMap::new();
        for (code, symbols) in result.symbols.iter_mut().enumerate() {
            for (symbol, class) in symbols.iter_mut().enumerate() {
                let mask = &masks[offsets[code] + symbol];
                *class = if let Some(&id) = intern.get(mask) {
                    id
                } else {
                    let id = u32::try_from(result.masks.len()).expect("bounded classes");
                    intern.insert(mask.clone(), id);
                    result.masks.push(mask.clone());
                    id
                };
            }
        }
        result
    }
    pub(super) fn validate(raw: &J, p: &Program, plan: &super::Plan) -> Result<Self> {
        let result: Self =
            serde_json::from_value(raw.clone()).map_err(|e| format!("query classes: {e}"))?;
        let width = p.tables.len().div_ceil(64);
        if result.schema != SCHEMA
            || result.masks.first() != Some(&vec![])
            || result.masks.iter().skip(1).any(|m| m.len() != width)
            || result.masks.len().saturating_mul(width.max(1)) > MAX_WORDS + width.max(1)
            || result.symbols.len() != plan.code_programs.len()
        {
            return Err("invalid query class certificate dimensions".into());
        }
        for (code, program) in plan.code_programs.iter().enumerate() {
            if result.symbols[code].len() != program.signals.len() {
                return Err("query class symbol coverage differs".into());
            }
            for (symbol, steps) in program.signals.iter().enumerate() {
                let class = result.symbols[code][symbol];
                if class as usize >= result.masks.len() {
                    return Err("query class out of bounds".into());
                }
                for step in steps {
                    if !result.contains(class, plan.code_operators[code][step.op as usize]) {
                        return Err("query class omits a current body operator".into());
                    }
                }
            }
        }
        let mut closed = true;
        edges(p, plan, |(a, x), (b, y)| {
            let source = result.symbols[a][x];
            let target = result.symbols[b][y];
            if source != 0
                && (target == 0
                    || result.masks[source as usize]
                        .iter()
                        .zip(&result.masks[target as usize])
                        .any(|(a, b)| b & !a != 0))
            {
                closed = false;
            }
        });
        if !closed {
            return Err("query class omits a future Entry use".into());
        }
        Ok(result)
    }
    #[inline]
    pub(super) fn contains(&self, class: u32, table: usize) -> bool {
        class == 0
            || self.masks[class as usize]
                .get(table / 64)
                .is_some_and(|word| word & (1 << (table % 64)) != 0)
    }
    pub fn report(&self) -> J {
        json!({"classes":self.masks.len(), "mask_words":self.masks.iter().map(Vec::len).sum::<usize>(),
            "symbol_slots":self.symbols.iter().map(Vec::len).sum::<usize>(),
            "all_operator_slots":self.symbols.iter().flatten().filter(|&&c| c == 0).count()})
    }
}

impl Program {
    /// Explicit offline compilation; production only checks the certificate.
    pub fn bake_query_classes(&mut self) -> Result<J> {
        self.prepare_cell_ownership()?;
        self.cell_ownership.prepare_codes(&self.templates);
        serde_json::to_value(Plan::bake(self, &self.cell_ownership)).map_err(|e| e.to_string())
    }
}

enum Members<'a> {
    Plain(crate::tiny_set::Iter<'a, Signal>),
    One(Option<Signal>),
    Groups {
        set: &'a BTreeSet<Signal>,
        range: std::collections::btree_set::Range<'a, Signal>,
        accepted: Option<u32>,
    },
}
pub(super) struct Signals<'a> {
    members: Members<'a>,
    plan: Option<&'a Plan>,
    table: usize,
    stats: Option<&'a Stats>,
    pub(super) probes: u64,
    pub(super) jumps: u64,
}
impl<'a> Signals<'a> {
    pub(super) fn new(
        set: Option<&'a crate::tiny_set::TinySet<Signal>>,
        plan: Option<&'a Plan>,
        table: usize,
        stats: Option<&'a Stats>,
    ) -> Self {
        use crate::tiny_set::TinySet;
        let members = match (set, plan) {
            (Some(set), None) => Members::Plain(set.iter()),
            (Some(TinySet::Tree(set)), Some(_)) => Members::Groups {
                set,
                range: set.range(..),
                accepted: None,
            },
            (Some(TinySet::One(signal)), Some(_)) => Members::One(Some(*signal)),
            _ => Members::One(None),
        };
        Self {
            members,
            plan,
            table,
            stats, probes: 0, jumps: 0,
        }
    }
}
impl Iterator for Signals<'_> {
    type Item = Signal;
    fn next(&mut self) -> Option<Signal> {
        match &mut self.members {
            Members::Plain(iter) => iter.next().copied(),
            Members::One(signal) => {
                let signal = signal.take()?;
                self.probes += 1;
                if let Some(stats) = self.stats { stats.query_class_probes.set(stats.query_class_probes.get() + 1); }
                self.plan
                    .unwrap()
                    .contains(signal.class, self.table)
                    .then_some(signal)
            }
            Members::Groups {
                set,
                range,
                accepted,
            } => loop {
                let signal = *range.next()?;
                if *accepted == Some(signal.class) {
                    return Some(signal);
                }
                self.probes += 1;
                if let Some(stats) = self.stats { stats.query_class_probes.set(stats.query_class_probes.get() + 1); }
                if self.plan.unwrap().contains(signal.class, self.table) {
                    *accepted = Some(signal.class);
                    return Some(signal);
                }
                // Do not enumerate rejected members to count "saved work".
                // Jump directly to the next actual class in this root bucket.
                let end = Signal {
                    class: signal.class,
                    component: u32::MAX,
                    symbol: usize::MAX,
                };
                *range = set.range((std::ops::Bound::Excluded(end), std::ops::Bound::Unbounded));
                self.jumps += 1;
                if let Some(stats) = self.stats { stats.query_class_range_jumps.set(stats.query_class_range_jumps.get() + 1); }
            },
        }
    }
}
impl Graph {
    pub(super) fn query_signals(&self, table: usize, id: u64) -> impl Iterator<Item = Signal> + '_ {
        let owner = self.ownership.as_ref().unwrap();
        // Training may introduce edges absent from the frozen certificate.
        // It disables filtering, never changes an already inserted Signal key.
        let plan = self
            .program
            .cell_ownership
            .query_classes
            .as_deref()
            .filter(|_| owner.composition.training.is_none());
        let native = self.native_signal(id).filter(|s| {
            plan.is_none_or(|plan| {
                owner
                    .stats
                    .query_class_probes
                    .set(owner.stats.query_class_probes.get() + 1);
                plan.contains(s.class, table)
            })
        });
        Signals::new(owner.boundaries.get(&id), plan, table, Some(&owner.stats))
            .filter(move |signal| Some(*signal) != native)
            .chain(native)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn cyclic_continuations_reach_a_fixed_point_without_merging_distinct_ports() {
        let mut masks = vec![vec![1], vec![2], vec![4], vec![8], vec![16]];
        // 0 -> 1 -> 2 -> 1; 2 -> 3. Symbol 4 is unrelated.
        let incoming = vec![
            BTreeSet::new(),
            BTreeSet::from([0, 2]),
            BTreeSet::from([1]),
            BTreeSet::from([2]),
            BTreeSet::new(),
        ];
        close(&mut masks, &incoming);
        assert_eq!(masks, [vec![15], vec![14], vec![14], vec![8], vec![16]]);
    }
    #[test]
    fn incompatible_range_is_skipped_with_one_class_probe() {
        let plan = Plan {
            schema: SCHEMA.into(),
            masks: vec![vec![], vec![1], vec![2]],
            symbols: vec![],
        };
        let stats = Stats::default();
        let mut set = crate::tiny_set::TinySet::default();
        for component in 0..4096 {
            set.insert(Signal {
                class: 1,
                component,
                symbol: 0,
            });
        }
        let kept = Signal {
            class: 2,
            component: 4096,
            symbol: 0,
        };
        set.insert(kept);
        assert_eq!(
            Signals::new(Some(&set), Some(&plan), 1, Some(&stats)).collect::<Vec<_>>(),
            [kept]
        );
        assert_eq!(stats.query_class_probes.get(), 2);
        assert_eq!(stats.query_class_range_jumps.get(), 1);
        #[cfg(target_pointer_width = "64")]
        assert_eq!(
            std::mem::size_of::<Signal>(),
            16,
            "class occupies the previous padding"
        );
    }
}
