//! Checked Entry substitutions compose immutable port programs. Runtime frame
//! locations are instance parameters, never part of a shared shape's identity.
use super::*;

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct Source {
    pub symbol: usize,
    pub entry: usize,
    pub column: usize,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Shape {
    pub programs: Vec<usize>,
    pub ports: Vec<Rc<Vec<usize>>>,
    pub signals: Vec<Rc<Vec<Instruction>>>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct Instruction {
    pub frame: usize,
    pub op: u32,
    pub columns: Rc<Vec<usize>>,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Key {
    pub parent: usize,
    pub program: usize,
    pub substitutions: Vec<(usize, usize)>,
}
impl Shape {
    fn initial(id: usize, p: &PortProgram) -> Self {
        Self::default().append(id, p, &[]).0
    }
    fn append(
        &self,
        id: usize,
        p: &PortProgram,
        substitutions: &[(usize, usize)],
    ) -> (Self, usize) {
        let mut shape = self.clone();
        let mut copied_steps = 0;
        let mut touched = smallvec::SmallVec::<[usize; 8]>::new();
        let frame = shape.programs.len();
        shape.programs.push(id);
        let mut ports = Vec::with_capacity(p.signals.len());
        for (local, steps) in p.signals.iter().enumerate() {
            let symbol =
                if let Some(&(_, shared)) = substitutions.iter().find(|&&(s, _)| s == local) {
                    assert!(shared < self.signals.len());
                    shared
                } else {
                    let new = shape.signals.len();
                    shape.signals.push(Rc::new(Vec::new()));
                    new
                };
            ports.push(symbol);
            if !touched.contains(&symbol) {
                touched.push(symbol);
                copied_steps += shape.signals[symbol].len();
            }
            copied_steps += steps.len();
            Rc::make_mut(&mut shape.signals[symbol]).extend(steps.iter().map(|s| Instruction {
                frame,
                op: s.op,
                columns: Rc::new(s.columns.clone()),
            }));
        }
        // Several checked query inputs may substitute to the same symbol.
        // Coalesce their columns once in the shape, not on every equality.
        // The old prefix is already ordered and its column arrays are shared.
        // Only modified slices copy instruction handles; untouched slices and
        // all previous frame port maps retain their existing allocations.
        for symbol in touched {
            let steps = Rc::make_mut(&mut shape.signals[symbol]);
            let prefix = steps.partition_point(|s| s.frame < frame);
            steps[prefix..].sort_unstable_by_key(|s| s.op);
            steps.dedup_by(|next, prev| {
                if (next.frame, next.op) != (prev.frame, prev.op) {
                    return false;
                }
                let columns = Rc::make_mut(&mut prev.columns);
                columns.extend_from_slice(&next.columns);
                columns.sort_unstable();
                columns.dedup();
                true
            });
        }
        shape.ports.push(Rc::new(ports));
        (shape, copied_steps)
    }
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    pub sources: Vec<Vec<Source>>,
    #[serde(skip)]
    pub shapes: Vec<Rc<Shape>>,
    pub transitions: Vec<(Key, usize)>,
    pub max_frames: usize,
    pub precompile_budget: usize,
}
impl Plan {
    pub(super) fn derive(
        p: &Program,
        markers: &[Marker],
        programs: &[Rc<PortProgram>],
        entries: &[Vec<usize>],
    ) -> Self {
        let sources = p
            .rules
            .iter()
            .enumerate()
            .map(|(rid, r)| {
                let program = &markers[r.template].program;
                let mut sources = Vec::new();
                for (entry, &atom) in entries[rid].iter().enumerate() {
                    for (column, arg) in r.query[atom].args.iter().enumerate() {
                        if let Arg::Slot(slot) = arg
                            && p.templates[r.template].sorts[*slot]["kind"] == "eq"
                            && let Some(symbol) = program.slots[*slot]
                        {
                            sources.push(Source {
                                symbol,
                                entry,
                                column,
                            });
                        }
                    }
                }
                sources
            })
            .collect::<Vec<_>>();
        let shapes = programs
            .iter()
            .enumerate()
            .map(|(id, p)| Rc::new(Shape::initial(id, p)))
            .collect::<Vec<_>>();
        let mut producers = vec![Vec::new(); p.tables.len()];
        for (tid, t) in p.templates.iter().enumerate() {
            for (op, ins) in t.ops.iter().enumerate() {
                if let Op::Let(_, Call::Table(table), _) | Op::Set(table, _, _) = ins
                    && markers[tid].bodies[op]
                {
                    producers[*table].push((markers[tid].program_id, op));
                }
            }
        }
        let mut transitions = BTreeMap::new();
        let budget = 4096;
        for (rid, r) in p.rules.iter().enumerate() {
            let callee = markers[r.template].program_id;
            for (entry, &atom) in entries[rid].iter().enumerate() {
                let Call::Table(table) = r.query[atom].call else {
                    continue;
                };
                for &(producer, op) in &producers[table] {
                    let mut subst = BTreeMap::new();
                    for source in sources[rid].iter().filter(|s| s.entry == entry) {
                        if let Some(symbol) = programs[producer].fields[op][source.column] {
                            subst.entry(source.symbol).or_insert(symbol);
                        }
                    }
                    if subst.is_empty() {
                        continue;
                    }
                    let key = Key {
                        parent: producer,
                        program: callee,
                        substitutions: subst.into_iter().collect(),
                    };
                    if transitions.len() < budget && !transitions.contains_key(&key) {
                        let id = programs.len() + transitions.len();
                        transitions.insert(key, id);
                    }
                }
            }
        }
        Self {
            sources,
            shapes,
            transitions: transitions.into_iter().collect(),
            max_frames: 16,
            precompile_budget: budget,
        }
    }
}

pub(super) struct Component {
    pub shape: usize,
    pub frames: Vec<u32>,
    pub live_facts: usize,
}
#[derive(Clone, Copy)]
pub(super) struct Frame {
    pub component: u32,
    pub ordinal: usize,
    pub program: usize,
}
#[derive(Clone, Copy)]
pub(super) struct Cursor {
    pub signal: Signal,
    pub position: usize,
    pub fact: FactRef,
}
pub(super) struct Runtime {
    pub components: Vec<Option<Component>>,
    pub frames: HashMap<u32, Frame>,
    pub shapes: Vec<Option<Rc<Shape>>>,
    pub transitions: HashMap<Key, usize>,
    pub entry_rule: Option<usize>,
    pub anchors: smallvec::SmallVec<[Option<Dependency>; 4]>,
    pub entry_template: Option<usize>,
    pub heap: Vec<Cursor>,
    pub columns: Vec<usize>,
}
impl Runtime {
    pub fn new(p: &Plan) -> Self {
        Self {
            components: vec![],
            frames: HashMap::default(),
            shapes: p
                .shapes
                .iter()
                .cloned()
                .map(Some)
                .chain(std::iter::repeat_n(None, p.transitions.len()))
                .collect(),
            transitions: p.transitions.iter().cloned().collect(),
            entry_rule: None,
            anchors: smallvec::SmallVec::new(),
            entry_template: None,
            heap: vec![],
            columns: vec![],
        }
    }
}
impl Graph {
    pub(super) fn composition_entry(&mut self, rid: usize, anchors: &[Option<Dependency>]) {
        let Some(m) = &mut self.ownership else {
            return;
        };
        // Keep checked Entry receipts; resolve their symbolic ports only if this
        // application actually creates an owned frame. All-hit RHSs pay no
        // composition lookups or shape construction.
        m.composition.entry_rule = Some(rid);
        m.composition.anchors.clear();
        m.composition.anchors.extend_from_slice(anchors);
        m.composition.entry_template = Some(self.program.rules[rid].template);
    }
    pub(super) fn ensure_composition_frame(&mut self, cell: u32) {
        let template = self.cells[&cell].template;
        let program = self.program.cell_ownership.markers[template].program_id;
        let m = self.ownership.as_mut().unwrap();
        if m.composition.frames.contains_key(&cell) {
            return;
        }
        let mut parent = None;
        let mut subst = BTreeMap::new();
        if m.composition.entry_template == Some(template) {
            let rid = m.composition.entry_rule.unwrap();
            for source in &self.program.cell_ownership.composition.sources[rid] {
                m.stats.composition_entry_reads += 1;
                let Some(Dependency::Fact(f)) = m.composition.anchors[source.entry] else {
                    continue;
                };
                let Some(frame) = m.composition.frames.get(&f.cell) else {
                    continue;
                };
                let Some(symbol) = self.program.cell_ownership.programs[frame.program].fields
                    [f.op as usize]
                    .get(source.column)
                    .copied()
                    .flatten()
                else {
                    continue;
                };
                let shape = m.composition.components[frame.component as usize]
                    .as_ref()
                    .unwrap()
                    .shape;
                let local = source.symbol;
                let source = Signal {
                    component: frame.component,
                    symbol: m.composition.shapes[shape].as_ref().unwrap().ports[frame.ordinal]
                        [symbol],
                };
                if !m.signals.contains_key(&source) {
                    m.stats.composition_missing_sources += 1;
                    continue;
                }
                let Some(c) = m.composition.components[source.component as usize].as_ref() else {
                    continue;
                };
                if c.frames.len() >= self.program.cell_ownership.composition.max_frames {
                    m.stats.composition_capacity_cuts += 1;
                    continue;
                }
                if c.frames.last().is_some_and(|&last| last >= cell) {
                    continue;
                }
                if parent.is_none() {
                    parent = Some(source.component);
                }
                if parent == Some(source.component) {
                    subst.entry(local).or_insert(source.symbol);
                } else {
                    m.stats.composition_foreign_inputs += 1;
                }
            }
        }
        let (component, ordinal) = if let Some(component) = parent {
            let c = m.composition.components[component as usize]
                .as_ref()
                .unwrap();
            let key = Key {
                parent: c.shape,
                program,
                substitutions: subst.into_iter().collect(),
            };
            m.stats.composition_requests += 1;
            m.stats.composition_substituted_ports += key.substitutions.len() as u64;
            let baked_count = self.program.cell_ownership.composition.shapes.len()
                + self.program.cell_ownership.composition.transitions.len();
            let shape = if let Some(&id) = m.composition.transitions.get(&key) {
                m.stats.composition_cache_hits += 1;
                m.stats.composition_baked_hits += u64::from(id < baked_count);
                id
            } else {
                let id = m.composition.shapes.len();
                m.composition.shapes.push(None);
                m.composition.transitions.insert(key.clone(), id);
                m.stats.composition_shape_builds += 1;
                id
            };
            if m.composition.shapes[shape].is_none() {
                let (code, copied_steps) =
                    m.composition.shapes[key.parent].as_ref().unwrap().append(
                        program,
                        &self.program.cell_ownership.programs[program],
                        &key.substitutions,
                    );
                m.stats.composition_materializations += 1;
                m.stats.composition_shape_steps += copied_steps as u64;
                m.composition.shapes[shape] = Some(Rc::new(code));
            }
            let c = m.composition.components[component as usize]
                .as_mut()
                .unwrap();
            let ordinal = c.frames.len();
            c.frames.push(cell);
            c.shape = shape;
            (component, ordinal)
        } else {
            let id = u32::try_from(m.composition.components.len()).expect("composition capacity");
            m.composition.components.push(Some(Component {
                shape: program,
                frames: vec![cell],
                live_facts: 0,
            }));
            m.stats.components_created += 1;
            m.stats.components_live += 1;
            (id, 0)
        };
        m.stats.composition_frames += 1;
        m.composition.frames.insert(
            cell,
            Frame {
                component,
                ordinal,
                program,
            },
        );
    }
    pub(super) fn composed_signal(&self, cell: u32, local: usize) -> Signal {
        let m = &self.ownership.as_ref().unwrap().composition;
        let f = m.frames[&cell];
        let shape = m.components[f.component as usize].as_ref().unwrap().shape;
        Signal {
            component: f.component,
            symbol: m.shapes[shape].as_ref().unwrap().ports[f.ordinal][local],
        }
    }
    pub(super) fn composition_retire_fact(&mut self, cell: u32) {
        let m = self.ownership.as_mut().unwrap();
        let f = m.composition.frames[&cell];
        let c = m.composition.components[f.component as usize]
            .as_mut()
            .unwrap();
        c.live_facts -= 1;
        if c.live_facts == 0 {
            for id in &c.frames {
                m.composition.frames.remove(id);
            }
            m.composition.components[f.component as usize] = None;
            m.stats.components_live -= 1;
            m.stats.components_retired += 1;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn appending_a_receiver_preserves_unrelated_program_storage() {
        let producer = PortProgram {
            signals: (0..200)
                .map(|op| {
                    vec![slices::Step {
                        op,
                        columns: vec![0],
                    }]
                })
                .collect(),
            ..PortProgram::default()
        };
        let receiver = PortProgram {
            signals: vec![vec![slices::Step {
                op: 0,
                columns: vec![0],
            }]],
            ..PortProgram::default()
        };
        let parent = Shape::initial(0, &producer);
        let (child, copied) = parent.append(1, &receiver, &[(0, 0)]);
        assert_eq!(copied, 2);
        assert_eq!(parent.signals[0].len(), 1);
        assert_eq!(child.signals[0].len(), 2);
        assert!(Rc::ptr_eq(&parent.ports[0], &child.ports[0]));
        for symbol in 1..200 {
            assert!(Rc::ptr_eq(&parent.signals[symbol], &child.signals[symbol]));
        }
    }
}
