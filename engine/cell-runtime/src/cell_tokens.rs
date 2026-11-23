//! Direct replay of certificates naming independent source premises by token and operation.
//! The inverse index used by the offline teacher is absent from the receiver.
use crate::{
    cell::{CompletedEffects, Instance, QueryFacts, Site, bind_query, query_operand},
    graph::{Dependency, Graph},
    program::{Call, Result},
    value::Value,
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use std::hash::{DefaultHasher, Hash, Hasher};
use std::io::{BufWriter, Write};
use std::time::{Duration, Instant};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Address {
    pub token: i64,
    pub op: usize,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Premise {
    pub address: Address,
    pub version: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub token: i64,
    pub run: usize,
    pub rule: usize,
    pub parents: Vec<Premise>,
}

#[derive(Default, Serialize)]
pub struct Counts {
    pub calls: usize,
    pub accepted: usize,
    pub duplicates: usize,
    pub reads: usize,
    pub reads_by_kind: BTreeMap<&'static str, usize>,
    pub rejected: BTreeMap<&'static str, usize>,
}
#[derive(Default)]
pub(crate) struct MergeOutputs {
    pub set_op: Option<usize>,
    pub rows: Vec<(usize, usize, Dependency)>,
    pub repairing: bool,
    pub event_ports: Vec<(usize, Dependency)>,
    pub events: Vec<CollisionResult>,
}
pub(crate) struct CollisionResult {
    pub table: usize,
    pub inputs: [(usize, u64); 2],
    pub input_hashes: [u64; 2],
    pub ports: Vec<(usize, Dependency)>,
}
/// Runtime-issued certificates have the merge program as their template.
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RepairEvent {
    pub token: i64,
    pub run: usize,
    pub merge_table: usize,
    pub visible_from_run: usize,
    pub parents: [Premise; 2],
    #[serde(default)]
    pub input_hashes: Option<[u64; 2]>,
    pub operations: Vec<usize>,
}
#[derive(Serialize, PartialEq, Eq)]
struct PortObservation {
    table: usize,
    version: u64,
    forwarded: bool,
    hashes: Vec<u64>,
}
pub(crate) fn value_hash(value: &Value) -> u64 {
    let mut hash = DefaultHasher::new();
    value.hash(&mut hash);
    hash.finish()
}
/// Optional diagnostic exporter. Normal reference, capture and replay clocks do
/// not scan token memory. Each record describes the snapshot before any RHS.
struct MemoryExport {
    writer: Box<dyn Write>,
    previous: BTreeMap<Address, PortObservation>,
    accepted: Vec<Request>,
    online_ids: Option<BTreeSet<i64>>,
}
pub struct History {
    memory: Option<MemoryExport>,
    pub repair_events: Vec<RepairEvent>,
    pub event_time: Duration,
    merge_offsets: Vec<BTreeMap<usize, usize>>,
    teacher: Option<BTreeMap<Dependency, Address>>,
    // This index links a collision already located by native repair to its two
    // actual writers. It cannot enumerate candidates for a model query.
    function_sources: BTreeMap<usize, Address>,
    returns: BTreeMap<Address, Dependency>,
    forwards: BTreeMap<Dependency, Dependency>,
    queue: BTreeMap<(usize, usize), Vec<Request>>,
    signing: BTreeMap<(usize, Vec<Value>), i64>,
    current: Option<i64>,
    next: i64,
    pub tape: Vec<Request>,
    pub counts: Counts,
    pub verify_time: Duration,
}
impl History {
    fn new(g: &Graph, teacher: bool) -> Result<Self> {
        // Preserve every original PC. Append the statically ordered merge-program
        // blocks; a Set that does not execute its merge contributes no result.
        let merge_offsets = g
            .program
            .rules
            .iter()
            .map(|r| {
                let ops = &g.program.templates[r.template].ops;
                let mut next = ops.len();
                let mut offsets = BTreeMap::new();
                for (i, op) in ops.iter().enumerate() {
                    if let crate::program::Op::Set(t, _, _) = op
                        && let Some(m) = g.program.merge_programs.merges.get(t)
                    {
                        offsets.insert(i, next);
                        next += m.operations.len();
                    }
                }
                offsets
            })
            .collect();
        let mut history = Self {
            memory: None,
            merge_offsets,
            function_sources: BTreeMap::new(),
            repair_events: Vec::new(),
            event_time: Duration::ZERO,
            teacher: teacher.then(BTreeMap::new),
            returns: BTreeMap::new(),
            forwards: BTreeMap::new(),
            queue: BTreeMap::new(),
            signing: BTreeMap::new(),
            current: None,
            next: 1,
            tape: Vec::new(),
            counts: Counts::default(),
            verify_time: Duration::ZERO,
        };
        // Stable input tokens belong to a separate namespace. Sort the source facts
        // by typed contents before assigning handles; physical placement is private.
        let mut id = -1;
        for table in 0..g.program.tables.len() {
            let mut initial = Vec::new();
            for w in g.witnesses(table) {
                if let Some(row) = g.row(w)?
                    && !row.hidden
                {
                    initial.push((row.values, w));
                }
            }
            initial.sort();
            for (_, witness) in initial {
                history.bind(Address { token: id, op: 0 }, witness);
                id -= 2;
            }
        }
        Ok(history)
    }
    pub fn capture(g: &Graph) -> Result<Self> {
        Self::new(g, true)
    }
    pub fn replay(g: &Graph, tape: Vec<Request>) -> Result<Self> {
        let mut h = Self::new(g, false)?;
        let mut ids = BTreeSet::new();
        for packet in tape {
            if packet.token <= 0 || !ids.insert(packet.token) {
                return Err("duplicate token or collision with seed namespace".into());
            }
            h.queue
                .entry((packet.run, packet.rule))
                .or_default()
                .push(packet);
        }
        Ok(h)
    }
    pub fn unused(&self) -> usize {
        self.queue.values().map(Vec::len).sum()
    }
    pub(crate) fn observing(&self) -> bool {
        self.memory.is_some()
    }
    pub(crate) fn export_memory(&mut self, path: Option<&std::path::Path>) -> Result<()> {
        let writer: Box<dyn Write> = match path {
            Some(path) => Box::new(BufWriter::new(
                std::fs::File::create(path).map_err(|e| e.to_string())?,
            )),
            None => Box::new(std::io::stdout()),
        };
        self.memory = Some(MemoryExport {
            writer,
            previous: BTreeMap::new(),
            accepted: Vec::new(),
            online_ids: path.is_none().then(BTreeSet::new),
        });
        Ok(())
    }
    pub(crate) fn observe(
        &mut self,
        graph: &Graph,
        run: usize,
        rules: &[(usize, u64)],
    ) -> Result<()> {
        if self.memory.is_none() {
            return Ok(());
        }
        let mut visible = BTreeMap::new();
        for (&address, &original) in &self.returns {
            let Some(witness) = self.resolve(address) else {
                continue;
            };
            let Some(row) = graph.row(witness)? else {
                continue;
            };
            if row.hidden || row.epoch >= graph.epoch {
                continue;
            }
            let hashes = row.values.iter().map(value_hash).collect();
            visible.insert(
                address,
                PortObservation {
                    table: row.table,
                    version: row.epoch,
                    forwarded: witness != original,
                    hashes,
                },
            );
        }
        let memory = self.memory.as_mut().expect("enabled observation");
        let updates: Vec<_> = visible
            .iter()
            .filter(|(a, row)| memory.previous.get(a) != Some(*row))
            .collect();
        let retired: Vec<_> = memory
            .previous
            .keys()
            .filter(|a| !visible.contains_key(a))
            .collect();
        serde_json::to_writer(
            &mut memory.writer,
            &serde_json::json!({
                "run":run, "epoch":graph.epoch, "rules":rules, "updates":updates, "retired":retired,
                "accepted":memory.accepted,
                "repair_events":&self.repair_events[self.repair_events.partition_point(|e| e.visible_from_run < run)..],
            }),
        )
        .map_err(|e| e.to_string())?;
        memory
            .writer
            .write_all(b"\n")
            .and_then(|_| memory.writer.flush())
            .map_err(|e| e.to_string())?;
        memory.previous = visible;
        memory.accepted.clear();
        if let Some(ids) = &mut memory.online_ids {
            let mut line = String::new();
            std::io::stdin()
                .read_line(&mut line)
                .map_err(|e| e.to_string())?;
            let proposals: Vec<Request> = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            for request in proposals {
                if request.run != run
                    || !rules.iter().any(|&(rid, _)| rid == request.rule)
                    || request.token <= 0
                    || !ids.insert(request.token)
                {
                    return Err("invalid online issue envelope".into());
                }
                self.queue
                    .entry((run, request.rule))
                    .or_default()
                    .push(request);
            }
        }
        Ok(())
    }
    pub(crate) fn is_teacher(&self) -> bool {
        self.teacher.is_some()
    }
    fn bind(&mut self, address: Address, witness: Dependency) {
        self.returns.insert(address, witness);
        if let Dependency::Function(i) = witness {
            self.function_sources.insert(i, address);
        }
        if let Some(index) = &mut self.teacher {
            index.insert(witness, address);
        }
    }
    pub(crate) fn release_events(&mut self, run: usize, merges: &mut MergeOutputs) -> Result<()> {
        if merges.events.is_empty() {
            return Ok(());
        }
        let started = Instant::now();
        for event in merges.events.drain(..) {
            let [old, new] = event.inputs;
            let premise = |(i, version)| -> Result<Premise> {
                Ok(Premise {
                    address: *self
                        .function_sources
                        .get(&i)
                        .ok_or("collision parent has no token provenance")?,
                    version,
                })
            };
            let parents = [premise(old)?, premise(new)?];
            let ports = event.ports;
            let token = -2 * (self.repair_events.len() as i64 + 1);
            let mut operations = Vec::with_capacity(ports.len());
            for (op, w) in ports {
                self.bind(Address { token, op }, w);
                operations.push(op);
            }
            self.repair_events.push(RepairEvent {
                token,
                run,
                merge_table: event.table,
                parents,
                input_hashes: Some(event.input_hashes),
                visible_from_run: run + 1,
                operations,
            });
        }
        self.event_time += started.elapsed();
        Ok(())
    }
    pub(crate) fn advance(&mut self, g: &Graph) {
        for (&old, &new) in &g.receipt_forwards {
            self.forwards.insert(old, new);
            if let Some(index) = &mut self.teacher
                && let Some(&address) = index.get(&old)
            {
                index.entry(g.resolve_receipt(new)).or_insert(address);
            }
        }
    }
    fn resolve(&self, a: Address) -> Option<Dependency> {
        let mut w = *self.returns.get(&a)?;
        for _ in 0..=self.forwards.len() {
            let Some(&next) = self.forwards.get(&w) else {
                return Some(w);
            };
            w = next;
        }
        None
    }
    pub(crate) fn capture_binding(
        &mut self,
        g: &Graph,
        run: usize,
        rid: usize,
        b: &Instance,
    ) -> Result<()> {
        let Some(index) = &self.teacher else {
            return Ok(());
        };
        let rule = &g.program.rules[rid];
        let mut parents = Vec::new();
        for (i, atom) in rule.query.iter().enumerate() {
            let Call::Table(_) = atom.call else { continue };
            let w = b.known.receipt(i).ok_or_else(|| {
                format!("Run {run}, rule {rid}, atom {i}: unretained teacher witness")
            })?;
            let address = *index.get(&w).ok_or_else(|| {
                format!("Run {run}, rule {rid}, atom {i}: no signed output for {w:?}")
            })?;
            let row = g.row(w)?.ok_or("teacher witness missing from snapshot")?;
            parents.push(Premise {
                address,
                version: row.epoch,
            });
        }
        let token = self.next;
        self.next += 1;
        self.signing.insert(
            (rid, b.input_values(&rule.inputs).cloned().collect()),
            token,
        );
        self.tape.push(Request {
            token,
            rule: rid,
            run,
            parents,
        });
        if let Some(memory) = &mut self.memory {
            memory.accepted.push(self.tape.last().unwrap().clone());
        }
        Ok(())
    }
    pub(crate) fn begin_rhs(&mut self, g: &Graph, rid: usize, b: &Instance) -> Result<()> {
        self.current = Some(
            self.signing
                .remove(&(
                    rid,
                    b.input_values(&g.program.rules[rid].inputs)
                        .cloned()
                        .collect(),
                ))
                .ok_or("RHS missing its issued token")?,
        );
        Ok(())
    }
    pub(crate) fn finish_rhs(&mut self, rid: usize, merges: &mut MergeOutputs) -> Result<()> {
        let token = self.current.take().ok_or("missing ordered token")?;
        merges.set_op = None;
        for (set, pc, w) in merges.rows.drain(..) {
            let base = self.merge_offsets[rid]
                .get(&set)
                .ok_or("unmapped merge result")?;
            self.bind(
                Address {
                    token,
                    op: base + pc,
                },
                w,
            );
        }
        Ok(())
    }
    pub(crate) fn output(
        &mut self,
        g: &Graph,
        rid: usize,
        known: &QueryFacts,
        effects: &impl CompletedEffects,
        executed: usize,
    ) {
        let token = self.current.expect("ordered RHS token");
        let sources = &g.program.known_results.static_sources[rid];
        for op in 0..executed {
            let witness = effects
                .get(op)
                .or_else(|| match sources.get(op).copied().flatten()? {
                    Site::Query(atom) => known.receipt(atom),
                    Site::Effect(source) => {
                        self.returns.get(&Address { token, op: source }).copied()
                    }
                });
            if let Some(w) = witness {
                self.bind(Address { token, op }, w);
            }
        }
    }
    pub(crate) fn verify(
        &mut self,
        g: &Graph,
        run: usize,
        rid: usize,
        wm: u64,
    ) -> Result<Vec<Instance>> {
        let started = Instant::now();
        let rule = &g.program.rules[rid];
        self.counts.calls += 1;
        let mut answers = Vec::new();
        for packet in self.queue.remove(&(run, rid)).unwrap_or_default() {
            let result = self.check(g, rid, wm, &packet)?;
            match result {
                Ok(answer) => {
                    let key = (rid, answer.input_values(&rule.inputs).cloned().collect());
                    match self.signing.entry(key) {
                        std::collections::btree_map::Entry::Vacant(slot) => {
                            slot.insert(packet.token);
                            answers.push(answer);
                            self.counts.accepted += 1;
                            if let Some(memory) = &mut self.memory {
                                memory.accepted.push(packet);
                            }
                        }
                        _ => self.counts.duplicates += 1,
                    }
                }
                Err(reason) => *self.counts.rejected.entry(reason).or_default() += 1,
            }
        }
        self.verify_time += started.elapsed();
        Ok(answers)
    }
    fn check(
        &mut self,
        g: &Graph,
        rid: usize,
        wm: u64,
        p: &Request,
    ) -> Result<std::result::Result<Instance, &'static str>> {
        let rule = &g.program.rules[rid];
        let atoms = &rule.query;
        if p.parents.len()
            != atoms
                .iter()
                .filter(|a| matches!(a.call, Call::Table(_)))
                .count()
        {
            return Ok(Err("arity"));
        }
        let mut env = BTreeMap::new();
        let mut seen = vec![None; atoms.len()];
        let mut epoch = 0;
        let mut parents = p.parents.iter();
        for (i, atom) in atoms.iter().enumerate() {
            let Call::Table(table) = atom.call else {
                continue;
            };
            let parent = parents.next().expect("checked arity");
            let Some(w) = self.resolve(parent.address) else {
                return Ok(Err("unknown_output"));
            };
            self.counts.reads += 1;
            let kind = if parent.address.token > 0 {
                "generated"
            } else if parent.address.token % 2 == 0 {
                "repair"
            } else {
                "initial"
            };
            *self.counts.reads_by_kind.entry(kind).or_default() += 1;
            let Some(row) = g.row(w)? else {
                return Ok(Err("retired"));
            };
            if row.hidden {
                return Ok(Err("hidden"));
            }
            if row.table != table {
                return Ok(Err("type"));
            }
            if row.epoch != parent.version || row.epoch >= g.epoch {
                return Ok(Err("version"));
            }
            if row.values.len() != atom.args.len()
                || !atom
                    .args
                    .iter()
                    .zip(row.values.iter())
                    .all(|(a, v)| bind_query(a, v, &mut env, g))
            {
                return Ok(Err("binding"));
            }
            epoch = epoch.max(row.epoch);
            seen[i] = Some(w);
        }
        if rule.seminaive && epoch < wm {
            return Ok(Err("watermark"));
        }
        for atom in atoms.iter() {
            if let Call::Primitive(name, sort) = &atom.call {
                let (out, args) = atom.args.split_last().ok_or("primitive without result")?;
                let Some(values) = args
                    .iter()
                    .map(|a| query_operand(a, &env, g))
                    .collect::<Option<Vec<_>>>()
                else {
                    return Ok(Err("unbound_primitive"));
                };
                let Some(v) = g.primitive(name, &values, sort)? else {
                    return Ok(Err("guard"));
                };
                if !bind_query(out, &v, &mut env, g) {
                    return Ok(Err("guard"));
                }
            }
        }
        let mut inputs = crate::slots::Slots::default();
        for &slot in rule.inputs.iter() {
            let Some(v) = env.get(&slot) else {
                return Ok(Err("unbound_input"));
            };
            inputs.insert(slot, v.clone());
        }
        Ok(Ok(Instance::matched(
            inputs,
            QueryFacts::Ports(seen),
            epoch,
        )))
    }
}
