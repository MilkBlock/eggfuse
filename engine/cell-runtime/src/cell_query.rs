//! Cell query dataflow, including residual enumeration. Catalog selection does not change its executor.
use crate::{
    cell::{QueryFrame, bind_operand},
    graph::{Graph, Row},
    program::*,
    value::{Value, canon},
};
use serde::Serialize;
use serde_json::json;
use std::{borrow::Cow, collections::BTreeMap};
#[cfg(any(test, not(feature = "sparse-cells")))]
use std::rc::Rc;

#[cfg(feature = "sparse-cells")]
pub(crate) type SharedQuery = std::sync::Arc<Query>;
#[cfg(not(feature = "sparse-cells"))]
pub(crate) type SharedQuery = Rc<Query>;

impl QueryFrame for crate::entry_schedule::Inputs {
    #[inline]
    fn slot(&self, slot: usize) -> Option<&Value> { self.get(slot) }
    #[inline]
    fn bind_slot(&mut self, slot: usize, value: Value) { self.set(slot, Some(value)); }
}
impl QueryFrame for [Option<Value>] {
    #[inline]
    fn slot(&self, slot: usize) -> Option<&Value> { self[slot].as_ref() }
    #[inline]
    fn bind_slot(&mut self, slot: usize, value: Value) { self[slot] = Some(value); }
}

#[inline]
pub(crate) fn query_operand<F: QueryFrame + ?Sized>(a: &Arg, frame: &F, g: &Graph) -> Option<Value> {
    match a {
        Arg::Literal(v) => Some(canon(v, &g.parents)),
        Arg::Slot(slot) => frame.slot(*slot).cloned(),
    }
}

/// Matching runs over a repaired, immutable snapshot. Rows and primitive
/// results are already canonical; only source literals need canonicalizing.
/// A failed comparison leaves bindings untouched. Branch rollback remains
/// the caller's responsibility, including earlier fields of a rejected row.
#[inline]
pub(crate) fn bind_query<F: QueryFrame + ?Sized>(a: &Arg, value: &Value, frame: &mut F, g: &Graph) -> bool {
    bind_operand(a, value, frame, PartialEq::eq, |expected, value| canon(expected, &g.parents) == *value)
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub(crate) enum Field {
    Anchor(usize),
    StepResult(usize),
    Column { step: usize, column: usize },
    Literal(Value),
}
impl Field {
    /// Candidate fields are borrowed until the recursive enumeration call
    /// returns. No row binding is retained across mutation or the next Run.
    fn value<'a>(
        &'a self,
        anchor: impl FnOnce(usize) -> &'a Value,
        results: &'a [Value],
        expanded: Option<(usize, &'a Row)>,
    ) -> &'a Value {
        match self {
            Self::Anchor(col) => anchor(*col),
            Self::StepResult(i) => &results[*i],
            Self::Column { step, column } => {
                let (current, row) = expanded.expect("validated expansion operand");
                debug_assert_eq!(*step, current);
                &row.values[*column]
            }
            Self::Literal(v) => v,
        }
    }
    pub(crate) fn operand<'a>(
        &'a self,
        g: &Graph,
        anchor: impl FnOnce(usize) -> &'a Value,
        results: &'a [Value],
        expanded: Option<(usize, &'a Row)>,
    ) -> Cow<'a, Value> {
        self.operand_in(&g.parents, anchor, results, expanded)
    }
    pub(crate) fn operand_in<'a>(
        &'a self,
        parents: &crate::value::Parents,
        anchor: impl FnOnce(usize) -> &'a Value,
        results: &'a [Value],
        expanded: Option<(usize, &'a Row)>,
    ) -> Cow<'a, Value> {
        match self {
            Self::Literal(v) => Cow::Owned(canon(v, parents)),
            _ => Cow::Borrowed(self.value(anchor, results, expanded)),
        }
    }
    pub(crate) fn read<'a>(
        &'a self,
        g: &Graph,
        anchor: impl FnOnce(usize) -> &'a Value,
        results: &'a [Value],
        expanded: Option<(usize, &'a Row)>,
    ) -> Value {
        match self {
            Self::Literal(v) => canon(v, &g.parents),
            _ => self.value(anchor, results, expanded).clone(),
        }
    }
    pub(crate) fn agrees<'a>(
        &'a self,
        v: &Value,
        g: &Graph,
        anchor: impl FnOnce(usize) -> &'a Value,
        results: &'a [Value],
        expanded: Option<(usize, &'a Row)>,
    ) -> bool {
        match self {
            Self::Literal(l) => canon(l, &g.parents) == *v,
            _ => self.value(anchor, results, expanded) == v,
        }
    }
}
#[derive(Clone, Debug)]
pub(crate) struct Query {
    result_slots: usize,
    pub steps: Vec<Step>,
    pub inputs: Vec<Field>,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Step {
    pub atom: usize,
    pub call: Call,
    pub key: Vec<Field>,
    pub check_result: Option<Field>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub expansion: Option<Box<Expansion>>,
}
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Expansion {
    pub width: usize,
    pub bound: Vec<(usize, Field)>,
    pub checks: Vec<(usize, Field)>,
}
impl Expansion {
    /// Query indexes consume a sparse column key. Its source fields come from
    /// the same Cell expansion used for row checks, regardless of frame storage.
    pub(crate) fn bind<A: FromIterator<Option<Value>> + AsMut<[Option<Value>]>>(
        &self, mut read: impl FnMut(&Field) -> Value) -> A {
        let mut bound: A = std::iter::repeat_with(|| None).take(self.width).collect();
        for (column, field) in &self.bound { bound.as_mut()[*column] = Some(read(field)); }
        bound
    }
}
/// A shared query instruction whose newly introduced fields are retained in
/// the caller's original frame. These static writes are also its rollback scope;
/// no per-branch trail or separate scalar interpreter is required.
#[derive(Clone, Debug)]
pub(crate) struct ScopedStep {
    pub step: Step,
    /// Dense frame addresses are this base plus the projection index. Original
    /// slot names stay in bindings for source/artifact provenance, not lookup.
    pub base: usize,
    pub bindings: Vec<(usize, Field)>,
}
impl ScopedStep {
    pub(crate) fn end(&self) -> usize { self.base + self.bindings.len() }
    /// Scoped instructions only write newly introduced slots. Check the whole
    /// candidate first (including repeated fields), then install its projection
    /// into the existing frame. Root and internal rows have the same semantics.
    pub(crate) fn bind_row<F: QueryFrame + ?Sized>(&self, g: &Graph, row: &Row, frame: &mut F) -> bool {
        let Call::Table(table) = self.step.call else { unreachable!("scoped table") };
        let expansion = self.step.expansion.as_ref().expect("scoped expansion");
        let expanded = Some((0, row));
        if row.hidden || row.table != table || !expansion.checks.iter().all(|(col, field)|
            field.agrees(&row.values[*col], g, |slot| frame.slot(slot).unwrap(), &[], expanded)) {
            return false;
        }
        for (offset, (_, field)) in self.bindings.iter().enumerate() {
            let slot = self.base + offset;
            debug_assert!(frame.slot(slot).is_none(), "scoped Cell write overwrites a live binding");
            let value = field.read(g, |slot| frame.slot(slot).unwrap(), &[], expanded);
            frame.bind_slot(slot, value);
        }
        true
    }
}
/// Shared binding/checking instruction used by source entries and repair cells.
/// The host supplies typed table/primitive capabilities; a failed predicate
/// never publishes an effect.
pub(crate) struct BoundStep<'a, A> {
    args: A,
    expected: Option<Cow<'a, Value>>,
}
impl Step {
    fn lower(rule: &Rule, atom: usize, access: Access, position: usize,
        sources: &mut BTreeMap<usize, Field>) -> Option<Self> {
        let field = |a: &Arg, map: &BTreeMap<usize, Field>| match a {
            Arg::Slot(s) => map.get(s).cloned(),
            Arg::Literal(v) => Some(Field::Literal(v.clone())),
        };
        let a = rule.query.get(atom)?;
        let (out, keys) = a.args.split_last()?;
        if matches!(access, Access::Expand) {
            if !matches!(a.call, Call::Table(_)) {
                return None;
            }
            let bound = a
                .args
                .iter()
                .enumerate()
                .filter_map(|(c, a)| Some((c, field(a, sources)?)))
                .collect();
            let mut checks = Vec::new();
            for (column, a) in a.args.iter().enumerate() {
                if let Some(source) = field(a, sources) {
                    checks.push((column, source));
                } else if let Arg::Slot(s) = a {
                    sources.insert(
                        *s,
                        Field::Column {
                            step: position,
                            column,
                        },
                    );
                }
            }
            return Some(Step {
                atom,
                call: a.call.clone(),
                key: vec![],
                check_result: None,
                expansion: Some(Box::new(Expansion {
                    width: a.args.len(),
                    bound,
                    checks,
                })),
            });
        }
        let key = keys
            .iter()
            .map(|a| field(a, sources))
            .collect::<Option<_>>()?;
        let check_result = field(out, sources);
        if let Arg::Slot(s) = out {
            sources.entry(*s).or_insert(Field::StepResult(position));
        }
        Some(Step {
            atom,
            call: a.call.clone(),
            key,
            check_result,
            expansion: None,
        })
    }
    pub(crate) fn access(&self) -> Access {
        if self.expansion.is_some() {
            Access::Expand
        } else if matches!(self.call, Call::Primitive(..)) {
            Access::Primitive
        } else {
            Access::Key
        }
    }
    pub(crate) fn bind<'a, A: FromIterator<Value>>(
        &'a self,
        mut field: impl FnMut(&'a Field) -> Cow<'a, Value>,
    ) -> BoundStep<'a, A> {
        BoundStep {
            args: self.key.iter().map(|f| field(f).into_owned()).collect(),
            expected: self.check_result.as_ref().map(field),
        }
    }
    /// A shared read has already bound and consumed its key. The per-Entry
    /// result predicate still uses the original instruction semantics.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn bind_result<'a>(
        &'a self, field: impl FnMut(&'a Field) -> Cow<'a, Value>,
    ) -> BoundStep<'a, ()> {
        BoundStep { args: (), expected: self.check_result.as_ref().map(field) }
    }
}
impl<A> BoundStep<'_, A> {
    pub(crate) fn evaluate(
        self,
        call: impl FnOnce(A) -> Result<Option<Value>>,
    ) -> Result<Option<Value>> {
        Ok(call(self.args)?.filter(|v| self.expected.as_ref().is_none_or(|e| e.as_ref() == v)))
    }
}
impl Query {
    /// Only the unconditional first point read may be shared before dispatch.
    /// Later reads can be guarded or depend on earlier runtime results.
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn first_literal_read(&self) -> Option<(usize, Vec<Value>)> {
        let step = self.steps.first()?;
        let Call::Table(table) = step.call else { return None };
        if step.expansion.is_some() { return None; }
        let key = step.key.iter().map(|field| match field {
            Field::Literal(v) => Some(v.clone()), _ => None,
        }).collect::<Option<Vec<_>>>()?;
        Some((table, key))
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn point_tables(&self) -> Option<Box<[usize]>> {
        self.steps.iter().all(|s| s.expansion.is_none())
            .then(|| self.steps.iter().filter_map(|s| match s.call {
                Call::Table(t) => Some(t), _ => None,
            }).collect::<std::collections::BTreeSet<_>>().into_iter().collect::<Vec<_>>().into_boxed_slice())
    }

    /// Computed outputs retain instruction-position addresses. Expansion rows
    /// stay borrowed, and a checked existing result needs no new value slot.
    pub(crate) fn result_slots(&self) -> usize { self.result_slots }
    fn new(steps: Vec<Step>, inputs: Vec<Field>) -> Self {
        let result_slots = steps.iter().rposition(|s| s.expansion.is_none() && s.check_result.is_none())
            .map_or(0, |i| i + 1);
        Self { steps, inputs, result_slots }
    }
    /// Substitute a complete block's outputs into the next block's anchor.
    /// This is dataflow composition: no intermediate row or slot map is needed.
    #[cfg(feature = "spine-blocks")]
    pub(crate) fn then(&self, next: &Self) -> Option<Self> {
        // The current enumerator borrows at most one candidate row at a time.
        if self
            .steps
            .iter()
            .chain(&next.steps)
            .filter(|s| s.expansion.is_some())
            .count()
            > 1
        {
            return None;
        }
        let field = |f: &Field| -> Option<Field> {
            Some(match f {
                Field::Anchor(i) => self.inputs.get(*i)?.clone(),
                Field::StepResult(i) => Field::StepResult(self.steps.len() + i),
                Field::Column { step, column } => Field::Column {
                    step: self.steps.len() + step,
                    column: *column,
                },
                Field::Literal(v) => Field::Literal(v.clone()),
            })
        };
        let mut steps = self.steps.clone();
        for step in &next.steps {
            steps.push(Step {
                atom: self.steps.len() + step.atom,
                call: step.call.clone(),
                key: step.key.iter().map(&field).collect::<Option<_>>()?,
                check_result: match &step.check_result {
                    Some(f) => Some(field(f)?),
                    None => None,
                },
                expansion: match &step.expansion {
                    Some(e) => Some(Box::new(Expansion {
                        width: e.width,
                        bound: e
                            .bound
                            .iter()
                            .map(|(c, f)| Some((*c, field(f)?)))
                            .collect::<Option<_>>()?,
                        checks: e
                            .checks
                            .iter()
                            .map(|(c, f)| Some((*c, field(f)?)))
                            .collect::<Option<_>>()?,
                    })),
                    None => None,
                },
            });
        }
        Some(Self::new(steps, next.inputs.iter().map(field).collect::<Option<_>>()?))
    }
    pub(crate) fn compile(rule: &Rule, pivot: usize, order: &[usize]) -> Option<Self> {
        let order = order
            .iter()
            .map(|&atom| {
                Some((
                    atom,
                    match rule.query.get(atom)?.call {
                        Call::Table(_) => Access::Key,
                        Call::Primitive(..) => Access::Primitive,
                    },
                ))
            })
            .collect::<Option<Vec<_>>>()?;
        Self::lower(rule, pivot, &order)
    }
    pub(crate) fn residual(rule: &Rule, pivot: usize) -> Option<Self> {
        Self::lower(rule, pivot, &query_order(rule, pivot, 1)?)
    }
    /// Borrow two matched rows and evaluate Unit guards in source order. Unit
    /// results are constants after their guard succeeds, so their users need
    /// neither a result frame nor a separate operand language.
    pub(crate) fn guarded_pair(rule: &Rule, pivot: usize, peer: usize) -> Option<Self> {
        let mut order = vec![(peer, Access::Expand)];
        for (atom, a) in rule.query.iter().enumerate() {
            if atom == pivot || atom == peer { continue; }
            if !matches!(&a.call, Call::Primitive(_, out) if out == "Unit") { return None; }
            order.push((atom, Access::Primitive));
        }
        let mut query = Self::lower(rule, pivot, &order)?;
        let fold = |field: &mut Field, units: &[Field]| {
            if let Field::StepResult(i) = field {
                debug_assert!(*i > 0, "the peer exports columns, not a scalar result");
                *field = Field::Literal(Value::Int(0));
            } else if units.contains(field) {
                *field = Field::Literal(Value::Int(0));
            }
        };
        let mut units = Vec::new();
        for step in &mut query.steps {
            step.key.iter_mut().for_each(|f| fold(f, &units));
            step.check_result.iter_mut().for_each(|f| fold(f, &units));
            if let Some(expansion) = &mut step.expansion {
                for (_, field) in expansion.bound.iter_mut().chain(&mut expansion.checks) { fold(field, &units); }
            }
            // Once this guard succeeds, a previously bound result is also Unit.
            // Keep its check here; only later uses may use the proven constant.
            if let Some(expected) = &step.check_result { units.push(expected.clone()); }
        }
        query.inputs.iter_mut().for_each(|f| fold(f, &units));
        query.result_slots = 0;
        Some(query)
    }
    /// Compile a retained prefix with the same lowering used by ordinary
    /// queries. Each completed instruction makes its new fields available from
    /// the existing frame; candidate rows never outlive their enumeration.
    pub(crate) fn scoped_prefix(rule: &Rule, pivot: usize, order: &[usize])
        -> Option<(BTreeMap<usize, Field>, Vec<ScopedStep>)> {
        let mut sources = BTreeMap::new();
        let mut seen = std::collections::BTreeSet::new();
        let mut steps = Vec::with_capacity(order.len() + 1);
        for atom in std::iter::once(pivot).chain(order.iter().copied()) {
            if !seen.insert(atom) { return None; }
            let access = match rule.query.get(atom)?.call {
                Call::Table(_) => Access::Expand, Call::Primitive(..) => Access::Primitive,
            };
            let base = sources.len();
            let step = Step::lower(rule, atom, access, 0, &mut sources)?;
            let mut next = base;
            let bindings = sources.iter_mut().filter_map(|(&slot, field)| {
                if matches!(field, Field::Anchor(_)) { None }
                else {
                    let previous = std::mem::replace(field, Field::Anchor(next));
                    next += 1;
                    Some((slot, previous))
                }
            }).collect();
            steps.push(ScopedStep { step, base, bindings });
        }
        Some((sources, steps))
    }
    /// Resume an already matched prefix from its existing slots, then borrow
    /// the terminal row and execute the original remaining scalar operations.
    /// `sources` maps source slots to that prefix's compiled dense addresses.
    /// The map is consumed during lowering; runtime fields address slots directly.
    pub(crate) fn continuation(rule: &Rule, prefix: impl Iterator<Item = usize>,
        sources: BTreeMap<usize, Field>, tail: usize, post: &[usize]) -> Option<Self> {
        let mut seen = std::collections::BTreeSet::new();
        for atom in prefix {
            rule.query.get(atom)?;
            if !seen.insert(atom) { return None; }
        }
        let mut order = vec![(tail, Access::Expand)];
        for &atom in post {
            if !matches!(rule.query.get(atom)?.call, Call::Primitive(..)) { return None; }
            order.push((atom, Access::Primitive));
        }
        Self::lower_from(rule, sources, seen, &order)
    }
    fn lower(rule: &Rule, pivot: usize, order: &[(usize, Access)]) -> Option<Self> {
        let mut sources = BTreeMap::new();
        for (col, arg) in rule.query.get(pivot)?.args.iter().enumerate() {
            if let Arg::Slot(s) = arg {
                sources.entry(*s).or_insert(Field::Anchor(col));
            }
        }
        Self::lower_from(rule, sources, std::collections::BTreeSet::from([pivot]), order)
    }
    fn lower_from(rule: &Rule, mut sources: BTreeMap<usize, Field>,
        mut seen: std::collections::BTreeSet<usize>, order: &[(usize, Access)]) -> Option<Self> {
        let mut steps = Vec::new();
        for &(atom, access) in order {
            if !seen.insert(atom) { return None; }
            steps.push(Step::lower(rule, atom, access, steps.len(), &mut sources)?);
        }
        if seen.len() != rule.query.len() {
            return None;
        }
        Some(Self::new(steps, rule.inputs.iter().map(|s| sources.get(s).cloned()).collect::<Option<_>>()?))
    }
}

/// Legacy Bake JSON is a wire format only. Every loaded entry executes Query;
/// PortResult is never retained as a second runtime operand kind.
impl Serialize for Query {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        let wire = if let [
            Step {
                atom,
                call: Call::Table(table),
                key,
                check_result,
                expansion: None,
            },
        ] = self.steps.as_slice()
        {
            let inputs = self
                .inputs
                .iter()
                .map(|f| match f {
                    Field::StepResult(0) => json!("PortResult"),
                    _ => json!(f),
                })
                .collect::<Vec<_>>();
            json!({"port":{"atom":atom,"table":table,"key":key,"check_result":check_result},"inputs":inputs})
        } else if self.steps.is_empty() {
            json!({"port":null,"inputs":self.inputs})
        } else {
            json!({"port":null,"steps":self.steps,"inputs":self.inputs})
        };
        wire.serialize(serializer)
    }
}

#[derive(Clone, Copy, Debug, Serialize)]
pub(crate) enum Access {
    Key,
    Expand,
    Primitive,
}

/// One deterministic scheduler for complete Entries and residual enumeration.
/// The caller chooses its coverage budget; expansion still needs delta ownership.
pub(crate) fn query_order(
    rule: &Rule,
    pivot: usize,
    mut expansions: usize,
) -> Option<Vec<(usize, Access)>> {
    use std::collections::BTreeSet;
    let mut known = rule
        .query
        .get(pivot)?
        .args
        .iter()
        .filter_map(|a| match a {
            Arg::Slot(s) => Some(*s),
            _ => None,
        })
        .collect::<BTreeSet<_>>();
    let mut pending = (0..rule.query.len())
        .filter(|&i| i != pivot)
        .collect::<BTreeSet<_>>();
    let mut out = Vec::with_capacity(pending.len());
    while !pending.is_empty() {
        let available = |v: &Arg| {
            matches!(v, Arg::Literal(_)) || matches!(v, Arg::Slot(s) if known.contains(s))
        };
        let (rank, atom) = pending
            .iter()
            .filter_map(|&i| {
                let a = &rule.query[i];
                let (_, keys) = a.args.split_last()?;
                if keys.iter().all(available) {
                    Some((usize::from(matches!(a.call, Call::Table(_))), i))
                } else if expansions != 0
                    && matches!(a.call, Call::Table(_))
                    && a.args.iter().any(available)
                {
                    Some((2, i))
                } else {
                    None
                }
            })
            .min()?;
        let access = match rank {
            0 => Access::Primitive,
            1 => Access::Key,
            _ => {
                expansions -= 1;
                Access::Expand
            }
        };
        pending.remove(&atom);
        known.extend(rule.query[atom].args.iter().filter_map(|a| match a {
            Arg::Slot(s) => Some(*s),
            _ => None,
        }));
        out.push((atom, access));
    }
    rule.inputs.iter().all(|i| known.contains(i)).then_some(out)
}

/// Shared by execution and Bake selection. The source stage-entry certificate
/// remains authoritative; this table owns no live instance facts.
#[derive(Clone, Debug, Default)]
pub(crate) struct Queries {
    entries: Vec<Vec<Option<SharedQuery>>>,
    count: usize,
    shared: usize,
    #[cfg(feature = "sparse-cells")]
    point_tables: Vec<Vec<Option<Box<[usize]>>>>,
}
impl Queries {
    pub(crate) fn compile(p: &Program) -> Result<Self> {
        let mut entries = p
            .rules
            .iter()
            .map(|r| vec![None; r.query.len()])
            .collect::<Vec<_>>();
        let mut shared_count = 0;
        for (rid, pivot, order) in &p.multi_stage.stage_entries {
            let shared = p.kernels[*rid][*pivot]
                .as_ref()
                .filter(|k| {
                    k.query.steps.iter().all(|s| s.expansion.is_none())
                        && k.query
                            .steps
                            .iter()
                            .map(|s| s.atom)
                            .eq(order.iter().copied())
                })
                .map(|k| k.query.clone());
            entries[*rid][*pivot] = Some(match shared {
                Some(query) => {
                    shared_count += 1;
                    query
                }
                None => SharedQuery::new(
                    Query::compile(&p.rules[*rid], *pivot, order)
                        .ok_or("invalid Cell query certificate")?,
                ),
            });
        }
        #[cfg(feature = "sparse-cells")]
        let point_tables = entries.iter().map(|row| row.iter().map(|q|
            q.as_ref().and_then(|q| q.point_tables())).collect()).collect();
        Ok(Self {
            #[cfg(feature = "sparse-cells")]
            point_tables,
            entries,
            count: p.multi_stage.stage_entries.len(),
            shared: shared_count,
        })
    }
    #[inline]
    pub(crate) fn get(&self, rid: usize, pivot: usize) -> Option<&SharedQuery> {
        self.entries.get(rid)?.get(pivot)?.as_ref()
    }
    #[cfg(feature = "sparse-cells")]
    pub(crate) fn point_tables(&self, rid: usize, pivot: usize) -> Option<&[usize]> {
        self.point_tables.get(rid)?.get(pivot)?.as_deref()
    }
    pub(crate) fn shared(&self) -> usize {
        self.shared
    }
    pub(crate) fn len(&self) -> usize {
        self.count
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn shared_first_read_keeps_result_guards_and_never_hoists_past_a_guard() {
        let read = Step { atom: 1, call: Call::Table(4), key: vec![Field::Literal(Value::Int(7))],
            check_result: Some(Field::Anchor(0)), expansion: None };
        let query = Query::new(vec![read.clone()], vec![]);
        assert_eq!(query.first_literal_read(), Some((4, vec![Value::Int(7)])));
        // Binding the predicate must never visit or rebuild the key.
        for value in [8, 9] {
            let expected = Value::Int(9);
            let bound = read.bind_result(|field| {
                assert_eq!(field, &Field::Anchor(0));
                Cow::Borrowed(&expected)
            });
            assert_eq!(bound.evaluate(|()| Ok(Some(Value::Int(value)))).unwrap(),
                (value == 9).then_some(Value::Int(9)));
        }
        let guard = Step { call: Call::Primitive("<".into(), "Unit".into()), ..read.clone() };
        assert!(Query::new(vec![guard, read.clone()], vec![]).first_literal_read().is_none());
        let dependent = Step { key: vec![Field::Anchor(0)], ..read };
        assert!(Query::new(vec![dependent], vec![]).first_literal_read().is_none());
    }
    #[test]
    fn guarded_pair_preserves_bound_results_and_folds_guard_outputs() {
        use crate::cell::Operand::Slot;
        let mut rule = Rule {
            completion: Default::default(), template: 0, seminaive: true, direct: None,
            inputs: vec![0, 3, 4, 2].into(),
            query: Rc::new(vec![
                Atom { call: Call::Table(0), args: vec![Slot(0), Slot(1), Slot(2)] },
                Atom { call: Call::Table(1), args: vec![Slot(0), Slot(1), Slot(3)] },
                Atom { call: Call::Primitive("<".into(), "Unit".into()), args: vec![Slot(1), Slot(3), Slot(4)] },
                Atom { call: Call::Primitive(">".into(), "Unit".into()), args: vec![Slot(3), Slot(1), Slot(4)] },
                // A result bound by a row remains an equality check, not a constant binding.
                Atom { call: Call::Primitive("<=".into(), "Unit".into()), args: vec![Slot(1), Slot(3), Slot(2)] },
            ]),
        };
        let query = Query::guarded_pair(&rule, 0, 1).unwrap();
        assert_eq!(query.result_slots(), 0);
        assert_eq!(query.steps[0].expansion.as_ref().unwrap().checks.len(), 2);
        assert_eq!(query.steps[2].check_result, Some(Field::Literal(Value::Int(0))));
        assert_eq!(query.steps[3].check_result, Some(Field::Anchor(2)));
        assert_eq!(query.inputs, vec![Field::Anchor(0), Field::Column { step: 0, column: 2 }, Field::Literal(Value::Int(0)), Field::Literal(Value::Int(0))]);
        assert!(Query::guarded_pair(&rule, 0, 0).is_none());
        Rc::make_mut(&mut rule.query)[2].call = Call::Primitive("+".into(), "i64".into());
        assert!(Query::guarded_pair(&rule, 0, 1).is_none());
    }
    #[test]
    fn staged_ports_preserve_dependencies_guards_and_bound_results() {
        use crate::cell::Operand::{Literal, Slot};
        let mut rule = Rule {
            completion: Default::default(),
            template: 0,
            seminaive: true,
            direct: None,
            inputs: vec![3, 0, 1].into(),
            query: Rc::new(vec![
                Atom {
                    call: Call::Table(0),
                    args: vec![Slot(0), Slot(1)],
                },
                Atom {
                    call: Call::Table(1),
                    args: vec![Slot(0), Slot(2)],
                },
                Atom {
                    call: Call::Primitive("+".into(), "i64".into()),
                    args: vec![Slot(2), Literal(Value::Int(1)), Slot(3)],
                },
                Atom {
                    call: Call::Table(2),
                    args: vec![Slot(3), Slot(1)],
                },
            ]),
        };
        let b = Query::compile(&rule, 0, &[1, 2, 3]).unwrap();
        assert_eq!(json!(b.steps[1].key[0]), json!({"StepResult":0}));
        assert_eq!(json!(b.steps[2].key), json!([{"StepResult":1}]));
        assert_eq!(json!(b.steps[2].check_result), json!({"Anchor":1}));
        assert_eq!(
            json!(b.inputs),
            json!([{"StepResult":1},{"Anchor":0},{"Anchor":1}])
        );
        assert!(Query::compile(&rule, 0, &[1]).is_none());
        assert!(Query::compile(&rule, 0, &[2, 1, 3]).is_none());
        assert!(Query::compile(&rule, 0, &[1, 2, 3, 3]).is_none());
        Rc::make_mut(&mut rule.query)[1].args[0] = Slot(9);
        assert!(Query::compile(&rule, 0, &[1]).is_none());
    }
    #[test]
    fn residual_expansion_never_certifies_a_complete_entry() {
        use crate::cell::Operand::Slot;
        let rule = Rule {
            completion: Default::default(),
            template: 0,
            seminaive: true,
            direct: None,
            inputs: vec![3].into(),
            query: Rc::new(vec![
                Atom {
                    call: Call::Table(0),
                    args: vec![Slot(0), Slot(1)],
                },
                Atom {
                    call: Call::Table(1),
                    args: vec![Slot(0), Slot(2), Slot(3)],
                },
                Atom {
                    call: Call::Primitive("=".into(), "Unit".into()),
                    args: vec![Slot(3), Slot(1), Slot(4)],
                },
            ]),
        };
        assert!(query_order(&rule, 0, 0).is_none());
        assert_eq!(
            json!(query_order(&rule, 0, 1).unwrap()),
            json!([[1, "Expand"], [2, "Primitive"]])
        );
        assert!(Query::compile(&rule, 0, &[1, 2]).is_none());
        let mut disconnected = rule;
        Rc::make_mut(&mut disconnected.query)[1].args[0] = Slot(9);
        assert!(query_order(&disconnected, 0, 1).is_none());
    }
    #[test]
    fn keyed_port_preserves_bound_result_constraints_and_slot_order() {
        use crate::cell::Operand::{Literal, Slot};
        let rule = Rule {
            completion: Default::default(),
            template: 3,
            seminaive: true,
            direct: None,
            inputs: vec![1, 0].into(),
            query: Rc::new(vec![
                Atom {
                    call: Call::Table(1),
                    args: vec![Slot(0), Slot(1), Slot(0)],
                },
                Atom {
                    call: Call::Table(2),
                    args: vec![Slot(1), Literal(Value::Int(7)), Slot(0)],
                },
            ]),
        };
        let b = Query::compile(&rule, 0, &[1]).unwrap();
        let p = &b.steps[0];
        assert_eq!(json!(p.key), json!([{"Anchor":1},{"Literal":{"Int":7}}]));
        assert_eq!(json!(p.check_result), json!({"Anchor":0}));
        assert_eq!(json!(b.inputs), json!([{"Anchor":1},{"Anchor":0}]));
        assert!(Query::compile(&rule, 0, &[1, 1]).is_none());
        let mut rule = rule;
        Rc::make_mut(&mut rule.query)[1].args[0] = Slot(9);
        assert!(Query::compile(&rule, 0, &[1]).is_none());
    }
}
