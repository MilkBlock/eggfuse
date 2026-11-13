//! Repair entries use the source Cell Query binder, ordered dataflow composition,
//! and typed host capabilities. Tables bind a shape; class/row IDs are inputs.
//! Only committed union deltas may enter a delta cell. The ordinary dirty queue
//! remains the ordering authority for exact-key completion and its effects.
use super::*;
use crate::cell::{Field, Query};
use std::{borrow::Cow, rc::Rc};

#[derive(Clone, Debug, Default)]
pub struct Catalog {
    shapes: Vec<Rc<Shape>>,
    tables: Vec<Option<usize>>,
    selected: BTreeSet<usize>,
}
#[derive(Clone, Debug, Serialize)]
struct Shape {
    schema: Vec<J>,
    key_ports: Query,
    result_port: Query,
    delta: Query,
    key: Query,
    collision: Template,
    vacant: Template,
}
// Lower through the same Rule -> Query compiler used by ordinary stage entries.
fn block(width: usize, calls: Vec<(&str, Vec<Arg>, usize)>, inputs: Vec<usize>) -> Query {
    let mut query = vec![Atom {
        call: Call::Primitive("repair-entry".into(), "Unit".into()),
        args: (0..width).map(Arg::Slot).collect(),
    }];
    query.extend(calls.into_iter().map(|(name, mut args, out)| {
        args.push(Arg::Slot(out));
        Atom {
            call: Call::Primitive(name.into(), "repair-port".into()),
            args,
        }
    }));
    let order = (1..query.len()).collect::<Vec<_>>();
    Query::compile(
        &Rule {
            completion: Default::default(),
            template: 0,
            query: Rc::new(query),
            inputs: inputs.into(),
            seminaive: false,
            direct: None,
        },
        0,
        &order,
    )
    .expect("internally typed repair block")
}
impl Catalog {
    pub(crate) fn derive(p: &Program) -> Result<Self> {
        let mut cat = Self {
            tables: vec![None; p.tables.len()],
            ..Self::default()
        };
        let mut shared = BTreeMap::new();
        for (table, t) in p.tables.iter().enumerate() {
            let Some(cols) = &p.repair_ports.key_eq_columns[table] else {
                continue;
            };
            let signature = serde_json::to_string(&t.schema).unwrap();
            let id = *shared.entry(signature).or_insert_with(|| {
                let width = 2 + t.schema.len(); // committed from, to, cached fields
                let mut inputs = (0..width).collect::<Vec<_>>();
                let calls = cols
                    .iter()
                    .enumerate()
                    .map(|(i, &col)| {
                        inputs[col + 2] = width + i;
                        (
                            "repair-replace",
                            vec![Arg::Slot(col + 2), Arg::Slot(0), Arg::Slot(1)],
                            width + i,
                        )
                    })
                    .collect();
                let key_ports = block(width, calls, inputs);
                let mut inputs = (0..width).collect::<Vec<_>>();
                inputs[width - 1] = width;
                let result_port = block(
                    width,
                    vec![(
                        "repair-replace",
                        vec![Arg::Slot(width - 1), Arg::Slot(0), Arg::Slot(1)],
                        width,
                    )],
                    inputs,
                );
                let delta = key_ports
                    .then(&result_port)
                    .expect("complete repair interface");
                let key = block(
                    1,
                    vec![
                        ("repair-key-hash", vec![], 1),
                        ("repair-exact-key", vec![Arg::Slot(1)], 2),
                    ],
                    vec![1, 2],
                );
                let effect = |collision: bool| {
                    let mut ops = vec![];
                    if collision {
                        ops.push(Op::Union(Arg::Slot(0), Arg::Slot(1)));
                    }
                    let op = ops.len();
                    ops.push(Op::Let(
                        2,
                        Call::Primitive("repair-publish".into(), "Unit".into()),
                        vec![],
                    ));
                    Template {
                        name: if collision {
                            "repair-collision"
                        } else {
                            "repair-vacant"
                        }
                        .into(),
                        sorts: vec![
                            t.schema.last().unwrap().clone(),
                            t.schema.last().unwrap().clone(),
                            json!({"kind":"Unit"}),
                        ],
                        defs: BTreeMap::from([(2, op)]),
                        ops: std::sync::Arc::new(ops),
                        parent_columns: BTreeMap::new(),
                    }
                };
                let id = cat.shapes.len();
                cat.shapes.push(Rc::new(Shape {
                    schema: t.schema.clone(),
                    key_ports,
                    result_port,
                    delta,
                    key,
                    collision: effect(true),
                    vacant: effect(false),
                }));
                id
            });
            cat.tables[table] = Some(id);
        }
        cat.selected.extend(0..cat.shapes.len());
        if let Some(raw) = p.artifact.get("repair_cells") {
            let selected: Vec<usize> =
                serde_json::from_value(raw["selected"].clone()).map_err(|e| e.to_string())?;
            if selected.windows(2).any(|s| s[0] >= s[1])
                || selected.iter().any(|&id| id >= cat.shapes.len())
            {
                return Err("invalid repair Cell selection".into());
            }
            cat.selected = selected.into_iter().collect();
            if *raw != cat.artifact(p) {
                return Err("repair Cell wiring differs from typed recipe".into());
            }
        }
        Ok(cat)
    }
    pub fn artifact(&self, p: &Program) -> J {
        json!({"schema":"eggfuse-repair-cells/v1", "recipe":p.artifact["recipe"]["sha256"],
            "tables":self.tables,"shapes":self.shapes,"selected":self.selected,
            "effects":{"delta":"cache canonical ports; result-only singleton may publish; otherwise enqueue ordered key entry",
                "key":"exact collision: request result union, forward and retire; vacant: reindex, subscribe and publish"},
            "entry_contracts":["committed equality + canonical scalar body", "ordered dirty fact + canonical body"],
            "joins":[{"left":"key_ports","right":"result_port","interface":"from,to,fields","result":"delta"}],
            "ordering":"dirty queue, pending union batches and source Run barriers remain authoritative"})
    }
    pub fn len(&self) -> usize {
        self.shapes.len()
    }
    pub fn is_empty(&self) -> bool {
        self.shapes.is_empty()
    }
    pub fn select(p: &Program, selected: &[usize]) -> Result<J> {
        let mut cat = p.repair_cells.clone();
        if selected.windows(2).any(|s| s[0] >= s[1]) || selected.iter().any(|&id| id >= cat.len()) {
            return Err("invalid repair Cell selection".into());
        }
        cat.selected = selected.iter().copied().collect();
        Ok(cat.artifact(p))
    }
    pub fn registry_nodes(&self) -> Vec<J> {
        let mut nodes = vec![];
        for (shape, s) in self.shapes.iter().enumerate() {
            let base = nodes.len();
            for (kind, body, parents) in [
                ("repair-key-ports", json!({"block":s.key_ports}), vec![]),
                ("repair-result-port", json!({"block":s.result_port}), vec![]),
                (
                    "repair-delta",
                    json!({"block":s.delta}),
                    vec![base, base + 1],
                ),
                (
                    "repair-union-effect",
                    json!({"template":s.collision}),
                    vec![],
                ),
                (
                    "repair-key-completion",
                    json!({"block":s.key,"vacant":s.vacant}),
                    vec![base + 3],
                ),
            ] {
                nodes.push(json!({"id":nodes.len(),"parents":parents,"descriptor":{"kind":kind,"schema":s.schema,"body":body},"shape":shape,"selected":self.selected.contains(&shape)}));
            }
        }
        nodes
    }
    fn get(&self, table: usize) -> Option<(usize, Rc<Shape>)> {
        let id = self.tables[table]?;
        self.selected
            .contains(&id)
            .then(|| (id, self.shapes[id].clone()))
    }
}
#[derive(Default, Serialize)]
pub(super) struct Runtime {
    pub attempts: u64,
    pub unmatched: u64,
    pub delta_cells: u64,
    pub key_cells: u64,
    pub steps: u64,
    pub effect_steps: u64,
    pub port_writes: u64,
    pub row_copies: u64,
    pub result_publications: u64,
    pub deferred_keys: u64,
    pub collisions: u64,
    pub union_requests: u64,
    pub by_shape: Vec<[u64; 2]>,
}
#[derive(Clone, Copy, PartialEq, Eq)]
pub(super) enum Delta {
    Uncovered,
    Deferred,
    Published,
}
fn field<'a>(f: &'a Field, anchor: impl Fn(usize) -> Value, values: &'a [Value]) -> Cow<'a, Value> {
    match f {
        Field::Anchor(i) => Cow::Owned(anchor(*i)),
        Field::StepResult(i) => Cow::Borrowed(&values[*i]),
        Field::Literal(v) => Cow::Borrowed(v),
        Field::Column { .. } => unreachable!("repair entry has no enumeration"),
    }
}
impl Graph {
    pub fn new_with_repair_cells(program: Program) -> Result<Self> {
        if program.repair_cells.selected.is_empty() {
            return Self::new_with_repair_ports(program);
        }
        let n = program.repair_cells.len();
        // Uncovered facts retain the previously validated result-port path.
        let mut g = Self::new_with_repair_ports(program)?;
        g.repair_cells = Some(Runtime {
            by_shape: vec![[0; 2]; n],
            ..Runtime::default()
        });
        Ok(g)
    }
    pub fn repair_cell_report(&self) -> J {
        json!({"enabled":self.repair_cells.is_some(),"stats":self.repair_cells,
            "catalog":self.program.repair_cells.artifact(&self.program),
            "scope":"scalar constructor delta and ordered exact-key cells; function/container repair remains residual"})
    }
    pub(super) fn match_repair_delta(&mut self, f: FactRef, from: u64, to: u64) -> Delta {
        let stats = self.repair_cells.as_mut().unwrap();
        stats.attempts += 1;
        let Some(mut state_guard) = self
            .cells.fact_state_mut(f)
        else {
            stats.unmatched += 1;
            return Delta::Uncovered;
        };
        let state = &mut *state_guard;
        let Some((table, fields)) = &mut state.decoded else {
            stats.unmatched += 1;
            return Delta::Uncovered;
        };
        let Some((id, shape)) = self.program.repair_cells.get(*table) else {
            stats.unmatched += 1;
            return Delta::Uncovered;
        };
        let mut results = smallvec::SmallVec::<[Value; 4]>::new();
        let anchor = |i| match i {
            0 => Value::Eq(from),
            1 => Value::Eq(to),
            i => fields[i - 2].clone(),
        };
        for step in &shape.delta.steps {
            let bound =
                step.bind::<smallvec::SmallVec<[Value; 4]>>(|f| field(f, &anchor, &results));
            let result = bound
                .evaluate(|a| {
                    debug_assert!(
                        matches!(&step.call, Call::Primitive(n, _) if n == "repair-replace")
                    );
                    Ok(Some(if a[0] == a[1] {
                        a[2].clone()
                    } else {
                        a[0].clone()
                    }))
                })
                .expect("total port replacement")
                .expect("total port replacement");
            results.push(result);
        }
        stats.steps += shape.delta.steps.len() as u64;
        stats.delta_cells += 1;
        stats.by_shape[id][0] += 1;
        let mut changed_key = false;
        // Only rewritten ports are outputs. Scalar fields are borrowed unchanged.
        for (col, source) in shape.delta.inputs[2..].iter().enumerate() {
            if let Field::StepResult(i) = source {
                if fields[col] != results[*i] {
                    changed_key |= col + 1 < fields.len();
                    stats.row_copies += u64::from(RowFields::strong_count(fields) > 1);
                    RowFields::make_mut(fields)[col] = results[*i].clone();
                    stats.port_writes += 1;
                }
            }
        }
        // An earlier key delta may already be pending; do not publish past it.
        if !changed_key
            && !self.dirty.contains(&Dependency::Fact(f))
            && !self.dirty_markers.contains(&f)
            && self
                .intern
                .get(&state.hash)
                .is_some_and(|b| b.len() == 1 && b.first() == Some(&f))
        {
            state.epoch = self.epoch;
            self.query_versions[*table] += 1;
            self.changes.touch(*table, Dependency::Fact(f));
            stats.result_publications += 1;
            Delta::Published
        } else {
            stats.deferred_keys += 1;
            Delta::Deferred
        }
    }
    /// Match the exact key from the retained canonical body, then execute the
    /// checked terminal effect. No legacy decode or second lookup follows.
    pub(super) fn match_repair_key(&mut self, f: FactRef) -> Result<bool> {
        let Some(state) = self.cells.fact_state(f) else {
            return Ok(false);
        };
        let Some((table, _)) = &state.decoded else {
            return Ok(false);
        };
        let Some((id, shape)) = self.program.repair_cells.get(*table) else {
            return Ok(false);
        };
        let r = self.fact(f)?.expect("live cached fact");
        let mut results = smallvec::SmallVec::<[Value; 4]>::new();
        let mut found = None;
        for step in &shape.key.steps {
            let bound = step
                .bind::<smallvec::SmallVec<[Value; 4]>>(|f| field(f, |_| Value::Int(0), &results));
            let result = bound
                .evaluate(|a| match &step.call {
                    Call::Primitive(n, _) if n == "repair-key-hash" => Ok(Some(Value::Int(
                        hashkey(r.table, &r.values[..r.values.len() - 1]) as i64,
                    ))),
                    Call::Primitive(n, _) if n == "repair-exact-key" => {
                        let Value::Int(h) = a[0] else { unreachable!() };
                        found = self.find_repair_collision(f, &r, h as u64)?;
                        Ok(Some(Value::Int(i64::from(found.is_some()))))
                    }
                    _ => unreachable!("validated repair capability"),
                })?
                .expect("total exact-key capability");
            results.push(result);
        }
        let Value::Int(h) = results[0] else {
            unreachable!()
        };
        let stats = self.repair_cells.as_mut().unwrap();
        stats.key_cells += 1;
        stats.steps += shape.key.steps.len() as u64;
        stats.by_shape[id][1] += 1;
        stats.collisions += u64::from(found.is_some());
        let effect = if found.is_some() {
            &shape.collision
        } else {
            &shape.vacant
        };
        let current = r.values.last().unwrap().clone();
        let other = found.as_ref().map(|r| r.values.last().unwrap().clone());
        let mut publication = Some((r, found));
        for op in effect.ops.iter() {
            self.repair_cells.as_mut().unwrap().effect_steps += 1;
            match op {
                Op::Union(a, b) => {
                    let value = |arg: &Arg| match arg {
                        Arg::Slot(0) => current.clone(),
                        Arg::Slot(1) => other.clone().expect("matched exact collision"),
                        _ => unreachable!("validated repair effect port"),
                    };
                    self.enqueue_union(value(a), value(b))?;
                    self.repair_cells.as_mut().unwrap().union_requests += 1;
                }
                Op::Let(_, Call::Primitive(name, _), _) if name == "repair-publish" => {
                    let (r, found) = publication.take().expect("one checked publication effect");
                    // The Cell's preceding source Union is already enqueued;
                    // publish its terminal effect without issuing it again.
                    self.commit_constructor_collision(f, r, Some(h as u64), found)?;
                }
                _ => unreachable!("validated repair effect"),
            }
        }
        Ok(true)
    }
}
