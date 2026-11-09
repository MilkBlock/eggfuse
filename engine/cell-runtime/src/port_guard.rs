//! Borrowed, immutable inputs for constructor guards. Workers return local
//! counts and a match result; liveness, candidate ordering and commits remain
//! with the executor. Borrowed bases stay immutable; during an epoch the
//! coordinator can commit changes to separate overlays.
use super::*;
use composition::conditions::Condition;
use std::sync::Arc;

pub(super) struct Snapshot {
    parents: Arc<crate::value::parent_epoch::Base>,
    nodes: Arc<HashMap<FactRef, Stored>>,
    components: Arc<Vec<Option<composition::Component>>>,
    pending: Arc<Vec<BTreeMap<FactRef, u64>>>,
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
    pub port_reads: u64,
    pub parent_probes: u64,
    pub key_fields: u64,
    pub scalar_guards: u64,
    pub equality_guards: u64,
    pub shared_symbol_guards: u64,
}

/// This view borrows the authoritative stable nodes, port bindings and equality
/// relation. It contains no Graph, Rc, interior counters, locks or copied rows.
#[derive(Clone, Copy)]
pub struct ReadView<'a> {
    parents: crate::value::parent_epoch::Read<'a>,
    components: crate::read_epoch::SlotsRead<'a, Option<composition::Component>>,
    nodes: crate::read_epoch::MapRead<'a, FactRef, Stored>,
}

pub struct KeyGuard<'a> {
    view: ReadView<'a>,
    target: &'a Stored,
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
            .key_matches(self.target, self.table, self.key, &mut work);
        (result, work)
    }
}

impl ReadView<'_> {
    pub(super) fn node(&self, fact: FactRef, work: &mut Work) -> Option<&Stored> {
        work.node_lookups += 1;
        self.nodes.get(&fact)
    }
    pub fn read_port(&self, port: PortRef) -> Result<Value> {
        self.read_port_counted(port).map(|(value, _)| value)
    }
    pub(super) fn read_port_counted(&self, port: PortRef) -> Result<(Value, u64)> {
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
            Field::Port(port) => {
                let (current, probes) = self.read_port_counted(*port)?;
                work.port_reads += 1;
                work.parent_probes += probes;
                Ok(current == *value)
            }
        }
    }

    pub(super) fn key_matches(
        &self,
        target: &Stored,
        table: usize,
        key: &[Value],
        work: &mut Work,
    ) -> Result<bool> {
        if target.table != table || target.fields.len() != key.len() + 1 {
            return Ok(false);
        }
        for (field, value) in target.fields.iter().zip(key) {
            work.key_fields += 1;
            if !self.field_matches(field, value, work)? {
                return Ok(false);
            }
        }
        Ok(true)
    }

    pub(super) fn condition_matches(
        &self,
        component: u32,
        condition: &Condition,
        target: &Stored,
        source: &[Value],
        work: &mut Work,
    ) -> Result<bool> {
        for &column in &condition.scalar_columns {
            work.scalar_guards += 1;
            if !self.field_matches(&target.fields[column], &source[column], work)? {
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
    pub(super) fn freeze_completion_reads(&mut self) -> Snapshot {
        let parents = self.parents.freeze();
        let nodes = self.stable_ports.as_mut().unwrap().nodes.freeze();
        let owner = self.ownership.as_mut().unwrap();
        let components = owner.composition.components.freeze();
        let pending = owner.pending.freeze();
        Snapshot {
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
    fn shared_multi_input_code_requires_every_equality_and_scalar_guard() {
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
            fields: vec![Field::Scalar(Value::Int(7))],
        };
        let mut work = Work::default();
        assert!(
            !ReadView {
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
        let mut parents = Parents::default();
        parents.insert(11, 10);
        let components = vec![Some(composition::Component {
            shape: 0,
            frames: smallvec::smallvec![1],
            signals: vec![Some(10), Some(11)],
        })];
        let nodes = HashMap::default();
        let view = ReadView {
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
            fields: vec![],
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
