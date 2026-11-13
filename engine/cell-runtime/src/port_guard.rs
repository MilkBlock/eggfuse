//! Borrowed, immutable inputs for constructor guards. Workers return local
//! counts and a match result; liveness, candidate ordering and commits remain
//! with the executor. Borrowed bases stay immutable; during an epoch the
//! coordinator can commit changes to separate overlays.
use super::*;
use composition::conditions::Condition;
use std::sync::Arc;

#[cfg(feature="sparse-cells")]
struct FrozenFact { fact: FactRef, node: Stored }
#[derive(Clone, Copy, Default, Serialize)]
pub(super) struct ProjectionWork {
    pub candidates: u64,
    pub records: u64,
    pub comparisons: u64,
    pub insertion_moves: u64,
    pub capacity_bytes: usize,
    pub scalar_values: u64,
    pub scalar_capacity_bytes: usize,
}

pub(super) struct Snapshot {
    #[cfg(feature="sparse-cells")]
    projected: Vec<FrozenFact>,
    pub projection_work: ProjectionWork,
    cell_fields: bool,
    parents: Arc<crate::value::parent_epoch::Base>,
    nodes: Arc<HashMap<FactRef, Stored>>,
    components: Arc<Vec<Option<composition::Component>>>,
    pending: Arc<Vec<BTreeMap<FactRef, u64>>>,
    programs: Arc<Vec<Arc<PortProgram>>>,
    shapes: Arc<Vec<Arc<composition::Shape>>>,
}
#[derive(Clone, Copy, Default, Serialize)]
pub(super) struct EpochWork {
    parents: crate::read_epoch::Work,
    nodes: crate::read_epoch::Work,
    components: crate::read_epoch::Work,
    queues: crate::read_epoch::Work,
}
impl EpochWork {
    pub fn add(&mut self, other: Self) {
        self.parents.add(other.parents);
        self.nodes.add(other.nodes);
        self.components.add(other.components);
        self.queues.add(other.queues);
    }
    pub fn total(&self) -> crate::read_epoch::Work {
        let mut total = self.parents;
        total.add(self.nodes);
        total.add(self.components);
        total.add(self.queues);
        total
    }
}
impl Snapshot {
    pub fn reader(&self) -> ReadView<'_> {
        ReadView {
            source_frames: None,
            #[cfg(feature="sparse-cells")]
            projected: (!self.projected.is_empty()).then_some(Projection::Frozen(&self.projected,self.cell_fields)),
            programs: &self.programs,
            shapes: &self.shapes,
            parents: crate::value::parent_epoch::Read {
                base: &self.parents,
                delta: None,
            },
            nodes: crate::read_epoch::MapRead {
                base: &self.nodes,
                changes: None,
            },
            components: crate::read_epoch::SlotsRead {
                base: &self.components,
                changes: None,
            },
        }
    }
    pub fn ready(&self) -> ready::ReadView<'_> {
        ready::ReadView::frozen(&self.pending)
    }
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize)]
pub struct Work {
    pub node_lookups: u64,
    pub template_node_projections: u64,
    pub field_layout_reads: u64,
    pub port_reads: u64,
    pub parent_probes: u64,
    pub key_fields: u64,
    pub scalar_guards: u64,
    pub cell_scalar_reads: u64,
    pub equality_guards: u64,
    pub shared_symbol_guards: u64,
}

/// This view borrows the authoritative stable nodes, port bindings and equality
/// relation. It contains no Graph, Rc, interior counters, locks or copied rows.
#[derive(Clone, Copy)]
pub struct ReadView<'a> {
    source_frames: Option<composition::FrameRead<'a>>,
    #[cfg(feature="sparse-cells")]
    projected: Option<Projection<'a>>,
    programs: &'a [Arc<PortProgram>],
    shapes: &'a [Arc<composition::Shape>],
    parents: crate::value::parent_epoch::Read<'a>,
    components: crate::read_epoch::SlotsRead<'a, Option<composition::Component>>,
    nodes: crate::read_epoch::MapRead<'a, FactRef, Stored>,
}

#[cfg(feature="sparse-cells")]
#[derive(Clone, Copy)]
enum Projection<'a> {
    Live {
        cells: &'a crate::graph::arena::Cells,
        frames: &'a composition::Frames,
        operators: &'a [Vec<usize>],
        templates: &'a [Template],
        cell_fields: bool,
    },
    Frozen(&'a [FrozenFact],bool),
}

pub struct KeyGuard<'a> {
    view: ReadView<'a>,
    target: Cow<'a, Stored>,
    table: usize,
    key: &'a [Value],
}

impl KeyGuard<'_> {
    /// A true result proves this candidate's key, not domain completeness or
    /// permission to retire it. Hidden facts remain valid congruence peers.
    pub fn evaluate(&self) -> (Result<bool>, Work) {
        let mut work = Work::default();
        let result = self
            .view
            .key_matches(&self.target, self.table, self.key, &mut work);
        (result, work)
    }
}

impl<'a> ReadView<'a> {
    pub(super) fn fields<'b>(&self, node: &'b Stored) -> Result<FieldView<'b>> where 'a: 'b {
        let fields = &node.fields;
        let component = self.components.get(fields.component as usize).and_then(Option::as_ref)
            .ok_or("expired stable field component")?;
        let shape = self.shapes.get(component.shape)
            .ok_or("missing stable field shape")?;
        let program = self.programs.get(*shape.programs.get(fields.frame).ok_or("stable field frame")?)
            .ok_or("stable field program")?;
        let mut scalars=ScalarView::Stored(&fields.scalars);
        #[cfg(feature="sparse-cells")]
        if fields.scalars.is_empty() {
            if let Some(Projection::Live{cells,templates,cell_fields:true,..})=self.projected {
                let cell=*component.frames.get(fields.frame).ok_or("scalar source frame")?;
                // Equality-only/result reads do not touch scalar source metadata.
                scalars=ScalarView::Cell{cells,templates,cell,operation:fields.operation};
            }
        }
        Ok(FieldView { component: fields.component,
            columns: program.fields.get(fields.operation as usize).ok_or("stable field operation")?,
            ports: shape.ports.get(fields.frame).ok_or("stable field ports")?, scalars })
    }

    pub(in crate::graph::cell_ownership) fn node(&self, fact: FactRef, work: &mut Work) -> Option<Cow<'a, Stored>> {
        work.node_lookups += 1;
        #[cfg(feature="sparse-cells")]
        let direct=matches!(self.projected,Some(Projection::Live{cell_fields:true,..}|Projection::Frozen(_,true)));
        #[cfg(not(feature="sparse-cells"))]
        let direct=false;
        if !direct {if let Some(node) = self.nodes.get(&fact) {return Some(Cow::Borrowed(node));}}
        #[cfg(feature="sparse-cells")]
        if let Some(node) = self.project_node(fact) {
            work.template_node_projections += 1;
            return Some(node);
        }
        None
    }
    #[cfg(feature="sparse-cells")]
    pub(super) fn project_node(&self, fact: FactRef) -> Option<Cow<'a,Stored>> {
        let Projection::Live {cells, frames, operators, cell_fields,..} = self.projected? else {
            let Projection::Frozen(records,_) = self.projected? else {unreachable!()};
            let record = records.get(records.binary_search_by_key(&fact, |r| r.fact).ok()?)?;
            return Some(Cow::Borrowed(&record.node));
        };
        let state = cells.fact_state(fact)?;
        if !state.owned || state.decoded.is_some() {return None;}
        let frame = frames.get(cells,&fact.cell)?;
        let component = self.components.get(frame.component as usize)?.as_ref()?;
        let shape = self.shapes.get(component.shape)?;
        let program = self.programs.get(*shape.programs.get(frame.ordinal)?)?;
        let fields = program.fields.get(fact.op as usize)?;
        if fields.is_empty() || (!cell_fields && fields.iter().any(Option::is_none)) {return None;}
        Some(Cow::Owned(Stored {table:*operators.get(frame.code)?.get(fact.op as usize)?,
            fields:Fields{component:frame.component,frame:frame.ordinal,operation:fact.op,scalars:Box::default()}}))
    }
    pub fn read_port(&self, port: PortRef) -> Result<Value> {
        self.read_source_port_counted(port).map(|(value,_)|value)
    }
    pub(super) fn read_source_port_counted(&self, port: PortRef) -> Result<(Value,u64)> {
        let frame=self.source_frames.and_then(|frames|frames.get(&port.cell))
            .ok_or("expired stable source port or snapshot-local reader")?;
        let component=self.components.get(frame.component as usize).and_then(Option::as_ref)
            .ok_or("expired stable source component")?;
        let shape=self.shapes.get(component.shape).ok_or("stable source shape")?;
        let symbol=*shape.ports.get(frame.ordinal).and_then(|ports|ports.get(port.local)).ok_or("stable source local port")?;
        self.read_port_counted(ComponentPort{component:frame.component,symbol})
    }
    pub(super) fn read_port_counted(&self, port: ComponentPort) -> Result<(Value, u64)> {
        let signals = &self
            .components
            .get(port.component as usize)
            .and_then(Option::as_ref)
            .ok_or("expired stable port")?
            .signals;
        let (id, probes) = self.read_symbol(signals, port.symbol)?;
        Ok((Value::Eq(id), probes))
    }
    fn read_symbol(&self, signals: &[Option<u64>], symbol: usize) -> Result<(u64, u64)> {
        let id = signals
            .get(symbol)
            .copied()
            .flatten()
            .ok_or("expired stable port")?;
        Ok(self.parents.root_counted(id))
    }
    pub(super) fn field_value(&self, field: &Field, meter: bool, work: &mut Work) -> Result<Value> {
        if meter && matches!(field,Field::CellScalar(_)) {work.cell_scalar_reads+=1;}
        field.value(|port| {
            let (value, probes) = self.read_port_counted(port)?;
            if meter {
                work.port_reads += 1;
                work.parent_probes += probes;
            }
            Ok(value)
        })
    }

    fn field_matches(&self, field: &Field, value: &Value, work: &mut Work) -> Result<bool> {
        match field {
            Field::Scalar(stored) => Ok(stored == value),
            Field::CellScalar(stored) => {work.cell_scalar_reads+=1;Ok(stored==value)},
            Field::Port(port) => {
                let (current, probes) = self.read_port_counted(*port)?;
                work.port_reads += 1;
                work.parent_probes += probes;
                Ok(current == *value)
            }
        }
    }

    pub(in crate::graph::cell_ownership) fn key_matches(
        &self,
        target: &Stored,
        table: usize,
        key: &[Value],
        work: &mut Work,
    ) -> Result<bool> {
        if target.table != table { return Ok(false); }
        work.field_layout_reads += 1;
        let fields = self.fields(target)?;
        if fields.len() != key.len() + 1 { return Ok(false); }
        for (field, value) in fields.iter().zip(key) {
            work.key_fields += 1;
            if !self.field_matches(&field, value, work)? {
                return Ok(false);
            }
        }
        Ok(true)
    }

    #[cfg(feature = "sparse-cells")]
    pub(in crate::graph::cell_ownership) fn result(&self, node: &Stored, work: &mut Work) -> Result<Value> {
        work.field_layout_reads += 1;
        self.field_value(&self.fields(node)?.last().ok_or("constructor without result")?, true, work)
    }

    pub(super) fn condition_matches(
        &self,
        component: u32,
        condition: &Condition,
        target: &Stored,
        source: &[Value],
        work: &mut Work,
    ) -> Result<bool> {
        let fields = if condition.scalar_columns.is_empty() { None } else {
            work.field_layout_reads += 1;
            Some(self.fields(target)?)
        };
        for &column in &condition.scalar_columns {
            work.scalar_guards += 1;
            if !self.field_matches(&fields.as_ref().unwrap().get(column).ok_or("condition field column")?, &source[column], work)? {
                return Ok(false);
            }
        }
        // The compiled condition's two symbols belong to this one component.
        // Resolve its directory entry once, instead of twice per Eq guard.
        let signals = &self
            .components
            .get(component as usize)
            .and_then(Option::as_ref)
            .ok_or("expired condition component")?
            .signals;
        for &[a, b] in &condition.equality_inputs {
            if a == b {
                work.shared_symbol_guards += 1;
                continue;
            }
            work.equality_guards += 1;
            let mut resolve = |symbol: usize| -> Result<u64> {
                let (id, probes) = self.read_symbol(signals, symbol)?;
                work.port_reads += 1;
                work.parent_probes += probes;
                Ok(id)
            };
            if resolve(a)? != resolve(b)? {
                return Ok(false);
            }
        }
        Ok(true)
    }
}

impl Graph {
    pub(super) fn freeze_completion_reads(&mut self, candidates: impl Iterator<Item=FactRef>) -> Snapshot {
        // Capture only the read set selected by these prepared tasks. The worker
        // sees presence at this boundary even if the coordinator later retires it.
        // Scalar data, port bindings and equality still use their existing bases.
        let mut projection_work = ProjectionWork::default();
        #[cfg(feature="sparse-cells")]
        let projected = {
            let mut records = Vec::<FrozenFact>::new();
            if self.stable_ports.as_ref().unwrap().template_fields {
                let view = self.stable_port_reader().expect("stable completion reader");
                for fact in candidates {
                    projection_work.candidates += 1;
                    let Err(position) = records.binary_search_by(|record| {
                        projection_work.comparisons += 1;
                        record.fact.cmp(&fact)
                    }) else {continue;};
                    if let Some(node) = view.project_node(fact) {
                        projection_work.insertion_moves += (records.len()-position) as u64;
                        let fields=view.fields(&node).expect("projected scalar source");
                        let scalars=fields.iter().filter_map(|field|match field {Field::Scalar(v)|Field::CellScalar(v)=>Some(v),_=>None}).collect::<Vec<_>>().into_boxed_slice();
                        projection_work.scalar_values+=scalars.len() as u64;
                        projection_work.scalar_capacity_bytes+=std::mem::size_of_val(scalars.as_ref());
                        let mut node=node.into_owned();node.fields.scalars=scalars;
                        records.insert(position, FrozenFact {fact,node});
                    }
                }
                projection_work.records = records.len() as u64;
                projection_work.capacity_bytes = records.capacity()*std::mem::size_of::<FrozenFact>();
            }
            records
        };
        #[cfg(not(feature="sparse-cells"))]
        let _ = candidates;
        let parents = self.parents.freeze();
        let nodes = self.stable_ports.as_mut().unwrap().nodes.freeze();
        let cell_fields=self.cell_stable_fields_enabled();
        let owner = self.ownership.as_mut().unwrap();
        let components = owner.composition.components.freeze();
        let pending = owner.pending.freeze();
        Snapshot {
            #[cfg(feature="sparse-cells")]
            projected,
            projection_work,
            cell_fields,
            programs: self.program.cell_ownership.programs.clone(),
            shapes: owner.composition.shapes.clone(),
            parents,
            nodes,
            components,
            pending,
        }
    }
    pub(super) fn thaw_completion_reads(&mut self) -> EpochWork {
        let parents = self.parents.thaw();
        let nodes = self.stable_ports.as_mut().unwrap().nodes.thaw();
        let owner = self.ownership.as_mut().unwrap();
        let components = owner.composition.components.thaw();
        let queues = owner.pending.thaw();
        EpochWork {
            parents,
            nodes,
            components,
            queues,
        }
    }
    pub fn stable_port_reader(&self) -> Result<ReadView<'_>> {
        if self.stable_ports.is_none() {
            return Err("stable fields disabled".into());
        }
        Ok(ReadView {
            source_frames: Some(self.ownership.as_ref().unwrap().composition.frames.reader(&self.cells)),
            #[cfg(feature="sparse-cells")]
            projected: self.stable_ports.as_ref().unwrap().template_fields.then_some(Projection::Live {
                cells: &self.cells, frames: &self.ownership.as_ref().unwrap().composition.frames,
                operators: &self.program.cell_ownership.code_operators,
                templates: &self.program.templates, cell_fields:self.cell_stable_fields_enabled(),
            }),
            programs: &self.program.cell_ownership.programs,
            shapes: &self.ownership.as_ref().unwrap().composition.shapes,
            parents: self.parents.reader(),
            components: self
                .ownership
                .as_ref()
                .unwrap()
                .composition
                .components
                .reader(),
            nodes: self.stable_ports.as_ref().unwrap().nodes.reader(),
        })
    }

    /// Bind a live candidate to a key already canonicalized in this read epoch,
    /// as required by lookup_port_key. This is one candidate, not a lookup over
    /// the complete domain. Rebuild the key after releasing the borrow for a
    /// union; this descriptor cannot be retained across graph mutation.
    pub fn stable_key_guard<'a>(
        &'a self,
        fact: FactRef,
        table: usize,
        key: &'a [Value],
    ) -> Result<Option<KeyGuard<'a>>> {
        let view = self.stable_port_reader()?;
        let target = self.stable_node(fact);
        Ok(target.map(|target| KeyGuard {
            view,
            target,
            table,
            key,
        }))
    }

    pub(super) fn record_port_reads(&self, reads: u64, probes: u64) {
        let stats = self.stable_ports.as_ref().unwrap();
        stats.port_reads.set(stats.port_reads.get() + reads);
        stats
            .root_resolutions
            .set(stats.root_resolutions.get() + reads);
        stats
            .root_parent_probes
            .set(stats.root_parent_probes.get() + probes);
    }
    pub(super) fn record_guard_reads(&self, work: &Work) {
        self.record_port_reads(work.port_reads, work.parent_probes);
        let stats = self.stable_ports.as_ref().unwrap();
        stats.cell_scalar_reads.set(stats.cell_scalar_reads.get()+work.cell_scalar_reads);
        stats.field_layout_reads.set(stats.field_layout_reads.get() + work.field_layout_reads);
        stats.template_node_projections.set(stats.template_node_projections.get() + work.template_node_projections);
        stats
            .node_lookups
            .set(stats.node_lookups.get() + work.node_lookups);
        stats
            .key_field_comparisons
            .set(stats.key_field_comparisons.get() + work.key_fields);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn source_port_survives_component_and_symbol_relocation_but_not_retirement() {
        fn read(cells:&SourceCells,frames:&composition::Frames,components:&[Option<composition::Component>],
                shapes:&[Arc<composition::Shape>],parents:&Parents,port:PortRef)->Result<Value> {
            ReadView {
                source_frames:Some(frames.reader(cells)),
                #[cfg(feature="sparse-cells")]
                projected:None,
                programs:&[],shapes,parents:parents.reader(),
                components:crate::read_epoch::SlotsRead{base:components,changes:None},
                nodes:crate::read_epoch::MapRead{base:&HashMap::default(),changes:None},
            }.read_port(port)
        }
        let shapes=vec![
            Arc::new(composition::Shape{ports:vec![Arc::new(vec![0])],..Default::default()}),
            Arc::new(composition::Shape{ports:vec![Arc::new(vec![0]),Arc::new(vec![1])],..Default::default()}),
        ];
        let mut frames=composition::Frames::default();
        let mut cells=SourceCells::default();
        frames.insert(&mut cells,7,composition::Frame{component:0,ordinal:0,code:0});
        let mut components=vec![Some(composition::Component{shape:0,frames:smallvec::smallvec![7],signals:vec![Some(10)]})];
        let mut parents=Parents::default();let port=PortRef{cell:7,local:0};
        assert_eq!(read(&cells,&frames,&components,&shapes,&parents,port).unwrap(),Value::Eq(10));
        components.push(Some(composition::Component{shape:1,frames:smallvec::smallvec![8,7],signals:vec![Some(99),Some(10)]}));
        frames.insert(&mut cells,7,composition::Frame{component:1,ordinal:1,code:0});
        frames.insert(&mut cells,8,composition::Frame{component:1,ordinal:0,code:0});
        components[0]=None;
        assert_eq!(read(&cells,&frames,&components,&shapes,&parents,port).unwrap(),Value::Eq(10));
        parents.insert(10,5);
        assert_eq!(read(&cells,&frames,&components,&shapes,&parents,port).unwrap(),Value::Eq(5));
        frames.remove(&mut cells,&7);
        assert!(read(&cells,&frames,&components,&shapes,&parents,port).is_err());
        assert_eq!(read(&cells,&frames,&components,&shapes,&parents,PortRef{cell:8,local:0}).unwrap(),Value::Eq(99));
    }

    #[test]
    fn shared_multi_input_code_requires_every_equality_and_scalar_guard() {
        let programs = vec![Arc::new(PortProgram { fields: vec![vec![None]], ..Default::default() })];
        let shapes = vec![Arc::new(composition::Shape { programs: vec![0], ports: vec![Arc::new(vec![])], ..Default::default() })];
        let mut parents = Parents::default();
        parents.insert(11, 10);
        let components = vec![Some(composition::Component {
            shape: 0,
            frames: smallvec::smallvec![1],
            signals: vec![Some(10), Some(11), Some(20), Some(21), Some(30)],
        })];
        let condition = Condition {
            sites: [0, 1],
            equality_inputs: vec![[0, 1], [2, 3], [4, 4]],
            scalar_columns: vec![0],
            outputs: [0, 1],
        };
        let target = Stored {
            table: 0,
            fields: Fields { component: 0, frame: 0, operation: 0, scalars: vec![Value::Int(7)].into_boxed_slice() },
        };
        let mut work = Work::default();
        assert!(
            !ReadView {
            source_frames: None,
            #[cfg(feature="sparse-cells")]
            projected: None,
                programs: &programs, shapes: &shapes,
                parents: parents.reader(),
                components: crate::read_epoch::SlotsRead {
                    base: &components,
                    changes: None
                },
                nodes: crate::read_epoch::MapRead {
                    base: &HashMap::default(),
                    changes: None
                },
            }
            .condition_matches(0, &condition, &target, &[Value::Int(8)], &mut work)
            .unwrap()
        );
        assert_eq!(work.scalar_guards, 1);
        assert_eq!(work.port_reads, 0);
        let mut work = Work::default();
        assert!(
            !ReadView {
            source_frames: None,
            #[cfg(feature="sparse-cells")]
            projected: None,
                programs: &programs, shapes: &shapes,
                parents: parents.reader(),
                components: crate::read_epoch::SlotsRead {
                    base: &components,
                    changes: None
                },
                nodes: crate::read_epoch::MapRead {
                    base: &HashMap::default(),
                    changes: None
                },
            }
            .condition_matches(0, &condition, &target, &[Value::Int(7)], &mut work)
            .unwrap()
        );
        assert_eq!(
            (
                work.equality_guards,
                work.port_reads,
                work.shared_symbol_guards
            ),
            (2, 4, 0)
        );
        parents.insert(21, 20);
        let mut work = Work::default();
        assert!(
            ReadView {
            source_frames: None,
            #[cfg(feature="sparse-cells")]
            projected: None,
                programs: &programs, shapes: &shapes,
                parents: parents.reader(),
                components: crate::read_epoch::SlotsRead {
                    base: &components,
                    changes: None
                },
                nodes: crate::read_epoch::MapRead {
                    base: &HashMap::default(),
                    changes: None
                },
            }
            .condition_matches(0, &condition, &target, &[Value::Int(7)], &mut work)
            .unwrap()
        );
        assert_eq!(
            (
                work.equality_guards,
                work.port_reads,
                work.shared_symbol_guards
            ),
            (2, 4, 1)
        );
    }

    #[test]
    fn compiled_conditions_and_bound_inputs_are_shared_by_scoped_workers() {
        fn send_sync<T: Send + Sync>() {}
        send_sync::<ReadView<'static>>();
        send_sync::<KeyGuard<'static>>();
        send_sync::<composition::conditions::Plan>();
        let programs = vec![Arc::new(PortProgram { fields: vec![vec![None]], ..Default::default() })];
        let shapes = vec![Arc::new(composition::Shape { programs: vec![0], ports: vec![Arc::new(vec![])], ..Default::default() })];
        let mut parents = Parents::default();
        parents.insert(11, 10);
        let components = vec![Some(composition::Component {
            shape: 0,
            frames: smallvec::smallvec![1],
            signals: vec![Some(10), Some(11)],
        })];
        let nodes = HashMap::default();
        let view = ReadView {
            source_frames: None,
            #[cfg(feature="sparse-cells")]
            projected: None,
            programs: &programs, shapes: &shapes,
            parents: parents.reader(),
            components: crate::read_epoch::SlotsRead {
                base: &components,
                changes: None,
            },
            nodes: crate::read_epoch::MapRead {
                base: &nodes,
                changes: None,
            },
        };
        let condition = Condition {
            sites: [0, 1],
            equality_inputs: vec![[0, 1]],
            scalar_columns: vec![],
            outputs: [0, 1],
        };
        let target = Stored {
            table: 0,
            fields: Fields { component: 0, frame: 0, operation: 0, scalars: Box::new([]) },
        };
        let barrier = std::sync::Barrier::new(3);
        let answers = std::thread::scope(|scope| {
            let mut workers = Vec::new();
            for _ in 0..2 {
                let (condition, target, barrier) = (&condition, &target, &barrier);
                workers.push(scope.spawn(move || {
                    barrier.wait();
                    let mut work = Work::default();
                    let result = view.condition_matches(0, condition, target, &[], &mut work);
                    (std::thread::current().id(), result, work)
                }));
            }
            barrier.wait();
            workers
                .into_iter()
                .map(|w| w.join().unwrap())
                .collect::<Vec<_>>()
        });
        assert_ne!(answers[0].0, answers[1].0);
        for (_, result, work) in answers {
            assert!(result.unwrap());
            assert_eq!((work.equality_guards, work.port_reads), (1, 2));
        }
    }
}
