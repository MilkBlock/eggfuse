//! Direct replay of certificates naming independent source premises by token and operation.
//! The inverse index used by the offline teacher is absent from the receiver.
#[path = "higher_tokens.rs"]
mod higher;
#[path = "graph_tokens.rs"]
mod graph_tokens;
pub use graph_tokens::{Certificate,Layout};
pub use higher::Recipe as HigherRecipe;
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
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
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
    #[serde(default, skip_serializing_if="Option::is_none")]
    pub unit: Option<usize>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub side: Option<Premise>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub closed_branch: Option<usize>,
    #[serde(default,skip_serializing_if="Option::is_none")]
    pub graph: Option<Certificate>,
    #[serde(skip)]
    step: usize,
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
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Wave {
    requests: Vec<Request>,
    finish: bool,
    #[serde(default)]
    prefix_probe: Option<PrefixProbe>,
}

/// Rules and atom roles are static. Every dynamic alternative is named by the caller.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PrefixProbe {
    run: usize,
    rule: usize,
    roles: Vec<usize>,
    rows: Vec<(Vec<Premise>, Vec<Premise>)>,
}

#[derive(Default)]
pub struct WaveReceiver {
    pub shadow: bool,
    pub prefix_reads: usize,
    pub prefixes_checked: usize,
    pub prefix_time: Duration,
    pub checks: Counts,
    ready: BTreeMap<(usize, usize), Vec<(Request, Instance)>>,
    pub batches: usize,
    pub requests: usize,
}

#[derive(Default)]
pub struct RecallAudit {
    queue: BTreeMap<(usize, usize), Vec<Request>>,
    pub verdicts: Vec<(usize, i64, Option<i64>, &'static str)>,
}
impl RecallAudit {
    pub fn pending(&self) -> usize {
        self.queue.values().map(Vec::len).sum()
    }
}

#[derive(Default, Serialize)]
pub struct AssistCounts {
    pub exact_rule_calls: usize,
    pub skipped_rule_calls: usize,
    pub point_domain_skips: usize,
    pub delta_domain_skips: usize,
    pub delta_members_checked: usize,
    pub certified_bindings: usize,
    #[serde(skip)]
    pub(crate) point_pivots: Vec<Vec<(usize, usize, bool)>>,
    pub exact_rows: usize,
    pub exact_candidates: u64,
    pub residual_commits: usize,
    pub exact_seconds: f64,
    pub rejected_reads: usize,
    pub rejected_seconds: f64,
    pub duplicate_reads: usize,
    pub duplicate_seconds: f64,
}

pub struct History {
    pub assist: Option<AssistCounts>,
    higher: Option<higher::Higher>,
    layouts:Option<graph_tokens::Receiver>,
    pub recall: Option<RecallAudit>,
    pub waves: Option<WaveReceiver>,
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
    pub(crate) current: Option<i64>,
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
            assist: None,
            higher: None,
            layouts:None,
            memory: None,
            recall: None,
            waves: None,
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
    pub(crate) fn enable_higher(&mut self, g: &Graph, recipes: Vec<HigherRecipe>) -> Result<()> {
        self.higher = Some(higher::Higher::new(&g.program, recipes)?);
        Ok(())
    }
    pub(crate) fn enable_layouts(&mut self,g:&Graph,layouts:Vec<Layout>,feedback:bool)->Result<()> {
        let mut receiver=graph_tokens::Receiver::new(&g.program,layouts)?;
        if feedback {receiver.enable_feedback();}
        self.layouts=Some(receiver);
        Ok(())
    }
    pub fn layout_report(&self)->Option<serde_json::Value> {
        self.layouts.as_ref().map(graph_tokens::Receiver::report)
    }
    pub fn higher_report(&self) -> Option<serde_json::Value> {
        self.higher.as_ref().map(|h| serde_json::json!({"counts":h.counts, "outstanding":h.remaining()}))
    }
    pub fn capture(g: &Graph) -> Result<Self> {
        Self::new(g, true)
    }
    pub fn replay(g: &Graph, tape: Vec<Request>) -> Result<Self> {
        let mut h = Self::new(g, false)?;
        let mut ids = BTreeSet::new();
        for packet in tape {
            if packet.closed_branch.is_some() || packet.side.is_some() || packet.unit.is_some() || packet.token <= 0 || !ids.insert(packet.token) {
                return Err("duplicate token or collision with seed namespace".into());
            }
            h.queue
                .entry((packet.run, packet.rule))
                .or_default()
                .push(packet);
        }
        Ok(h)
    }
    pub(crate) fn enable_recall(&mut self, proposals: Vec<Request>) -> Result<()> {
        let mut audit = RecallAudit::default();
        let mut ids = BTreeSet::new();
        for p in proposals {
            if p.unit.is_some() || p.side.is_some() || p.closed_branch.is_some() || !ids.insert(p.token) || p.token <= 0 || p.run == 0 {
                return Err("invalid recall proposal identity".into());
            }
            audit.queue.entry((p.run,p.rule)).or_default().push(p);
        }
        self.recall = Some(audit);
        Ok(())
    }

    pub fn unused(&self) -> usize {
        self.queue.values().map(Vec::len).sum::<usize>()
            + self.waves.as_ref().map_or(0, |w| w.ready.values().map(Vec::len).sum())
    }
    pub(crate) fn reject_untriggered(&mut self, run: usize, rid: usize) {
        if let Some(audit) = &mut self.recall {
            for p in audit.queue.remove(&(run, rid)).unwrap_or_default() {
                audit.verdicts.push((run, p.token, None, "untriggered_rule"));
            }
        }
        if let Some(packets) = self.queue.remove(&(run, rid)) {
            if let Some(higher)=&mut self.higher {
                for p in &packets {higher.verdict(p,"untriggered_rule");}
            }
            if let Some(layouts)=&mut self.layouts {
                for packet in &packets {layouts.completed_step(packet.token,"untriggered_rule");}
            }
            *self.counts.rejected.entry("untriggered_rule").or_default() += packets.len();
        }
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
        dirty: &[bool],
        check_dirty: bool,
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
        let mut frame=serde_json::json!({
            "run":run, "epoch":graph.epoch, "rules":rules, "updates":updates, "retired":retired,
            "accepted":memory.accepted,
            "repair_events":&self.repair_events[self.repair_events.partition_point(|e| e.visible_from_run < run)..],
        });
        if let Some(layouts)=&mut self.layouts {
            layouts.advance(&visible,&memory.accepted,run,rules,&mut self.queue)?;
            if let Some(feedback)=layouts.snapshot(run,&self.queue) {
                frame["layout_feedback"]=feedback;
            }
        }
        serde_json::to_writer(&mut memory.writer,&frame)
        .map_err(|e| e.to_string())?;
        memory
            .writer
            .write_all(b"\n")
            .and_then(|_| memory.writer.flush())
            .map_err(|e| e.to_string())?;
        if let Some(higher) = &mut self.higher {
            higher.dispatch(&visible, run, rules, &mut self.queue)?;
        }
        memory.previous = visible;
        memory.accepted.clear();
        if self.waves.is_some() {
            return self.receive_waves(graph, run, rules, dirty, check_dirty);
        }
        if let Some(ids) = &mut memory.online_ids {
            let mut line = String::new();
            std::io::stdin()
                .read_line(&mut line)
                .map_err(|e| e.to_string())?;
            let mut proposals: Vec<Request> = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            let mut attached=BTreeSet::new();
            for request in &mut proposals {
                if let Some(higher) = &mut self.higher { higher.issue(request,&memory.previous)?; }
                if (request.unit.is_some() || request.side.is_some() || request.closed_branch.is_some()) && self.higher.is_none() { return Err("missing higher catalog".into()); }
                if request.run != run
                    || ((self.higher.is_some() || self.layouts.is_some()) && request.token >= higher::INTERNAL)
                    || (self.assist.is_some() && request.token >= i64::MAX / 2)
                    || !rules.iter().any(|&(rid, _)| rid == request.rule)
                    || request.token <= 0
                    || !ids.insert(request.token)
                {
                    return Err("invalid online issue envelope".into());
                }
                if request.graph.is_some() {
                    let layouts=self.layouts.as_mut().ok_or("missing graph catalog")?;
                    if layouts.issue(request,&memory.previous,rules,&mut self.queue)? {
                        attached.insert(request.token);
                    }
                }
            }
            for request in proposals {
                if attached.contains(&request.token) {continue;}
                self.queue
                    .entry((run, request.rule))
                    .or_default()
                    .push(request);
            }
        }
        Ok(())
    }
    fn receive_waves(
        &mut self, graph: &Graph, run: usize, rules: &[(usize, u64)], dirty: &[bool], check_dirty: bool,
    ) -> Result<()> {
        let shadow = self.waves.as_ref().unwrap().shadow;
        let mut seen = BTreeSet::new();
        loop {
            let mut line = String::new();
            std::io::stdin().read_line(&mut line).map_err(|e| e.to_string())?;
            let wave: Wave = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            if let Some(probe) = wave.prefix_probe {
                if wave.finish || !wave.requests.is_empty() || probe.run != run
                    || !rules.iter().any(|&(r, _)| r == probe.rule) {
                    return Err("invalid partial proof envelope".into());
                }
                let start = Instant::now();
                let (accepted, reads) = self.check_prefixes(graph, &probe)?;
                let state = self.waves.as_mut().unwrap();
                state.prefix_time += start.elapsed();
                state.prefix_reads += reads;
                state.prefixes_checked += accepted.iter().map(Vec::len).sum::<usize>();
                let writer = &mut self.memory.as_mut().unwrap().writer;
                serde_json::to_writer(&mut *writer, &serde_json::json!({"run":run, "prefix_ok":accepted}))
                    .map_err(|e| e.to_string())?;
                writer.write_all(b"\n").and_then(|_| writer.flush()).map_err(|e| e.to_string())?;
                continue;
            }
            if wave.finish {
                if wave.requests.is_empty() { return Ok(()); }
                return Err("finish must follow the last receipt".into());
            }
            if wave.requests.is_empty() { return Err("empty issue wave".into()); }
            let started = Instant::now();
            if shadow {
                std::mem::swap(&mut self.counts, &mut self.waves.as_mut().unwrap().checks);
            }
            let mut replies = Vec::new();
            for packet in wave.requests {
                if packet.graph.is_some() {return Err("graph certificates require the sealed batch receiver".into());}
                let rid = packet.rule;
                let Some(&(_, wm)) = rules.iter().find(|&&(r, _)| r == rid) else {
                    return Err("unscheduled wave request".into());
                };
                let id = packet.token;
                let memory = self.memory.as_mut().expect("wave memory");
                if packet.unit.is_some() || packet.side.is_some() || packet.closed_branch.is_some() || packet.run != run || id <= 0 || !memory.online_ids.as_mut().expect("online").insert(id) {
                    return Err("invalid wave request identity".into());
                }
                if shadow {
                    self.recall.as_mut().unwrap().queue.entry((run,rid)).or_default().push(packet.clone());
                }
                let verdict = if check_dirty && !dirty[rid] {
                    *self.counts.rejected.entry("untriggered_rule").or_default() += 1;
                    "untriggered_rule"
                } else if shadow {
                    match self.check(graph, rid, wm, &packet)? {
                        Ok(answer) => {
                            let key: Vec<_> = answer.input_values(&graph.program.rules[rid].inputs).cloned().collect();
                            if seen.insert((rid,key)) {
                                self.counts.accepted += 1;
                                "accepted"
                            } else {
                                self.counts.duplicates += 1;
                                "duplicate"
                            }
                        }
                        Err(reason) => {
                            *self.counts.rejected.entry(reason).or_default() += 1;
                            reason
                        }
                    }
                } else {
                    let (answer, verdict) = self.admit(graph, rid, wm, &packet)?;
                    if let Some(answer) = answer {
                        self.waves.as_mut().unwrap().ready.entry((run, rid)).or_default().push((packet, answer));
                    }
                    verdict
                };
                replies.push((id, verdict));
            }
            self.verify_time += started.elapsed();
            let w = self.waves.as_mut().unwrap();
            if shadow { std::mem::swap(&mut self.counts, &mut w.checks); }
            w.batches += 1;
            w.requests += replies.len();
            let writer = &mut self.memory.as_mut().unwrap().writer;
            serde_json::to_writer(&mut *writer, &serde_json::json!({"run":run, "verdicts":replies}))
                .map_err(|e| e.to_string())?;
            writer.write_all(b"\n").and_then(|_| writer.flush()).map_err(|e| e.to_string())?;
        }
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
        if self.assist.is_some() && self.signing.contains_key(&(rid, b.input_values(&rule.inputs).cloned().collect())) {
            return Ok(());
        }
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
        let token = if let Some(counts) = &mut self.assist {
            counts.residual_commits += 1;
            (i64::MAX / 2).checked_add(self.next).ok_or("residual token namespace exhausted")?
        } else {
            self.next
        };
        self.next += 1;
        self.signing.insert(
            (rid, b.input_values(&rule.inputs).cloned().collect()),
            token,
        );
        let request = Request { token, rule: rid, run, parents, unit: None, side: None, closed_branch: None, graph:None, step: 0 };
        if let Some(memory) = &mut self.memory {
            memory.accepted.push(request.clone());
        }
        if self.assist.is_none() {
            self.tape.push(request);
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
        if let Some(receiver) = &mut self.waves && !receiver.shadow {
            for (packet, answer) in receiver.ready.remove(&(run,rid)).unwrap_or_default() {
                answers.push(answer);
                self.memory.as_mut().unwrap().accepted.push(packet);
            }
        } else {
            for packet in self.queue.remove(&(run, rid)).unwrap_or_default() {
                let meter = self.assist.as_ref().map(|_| (Instant::now(), self.counts.reads));
                let (answer, verdict) = self.admit(g,rid,wm,&packet)?;
                if let Some(higher)=&mut self.higher {higher.verdict(&packet,verdict);}
                if let Some(layouts)=&mut self.layouts {layouts.completed_step(packet.token,verdict);}
                if let Some((clock, reads)) = meter && answer.is_none() {
                    let stats = self.assist.as_mut().unwrap();
                    if verdict == "duplicate" {
                        stats.duplicate_reads += self.counts.reads - reads;
                        stats.duplicate_seconds += clock.elapsed().as_secs_f64();
                    } else {
                        stats.rejected_reads += self.counts.reads - reads;
                        stats.rejected_seconds += clock.elapsed().as_secs_f64();
                    }
                }
                if let Some(answer) = answer {
                    answers.push(answer);
                    if let Some(higher) = &mut self.higher { higher.accepted(&packet); }
                    if let Some(memory) = &mut self.memory { memory.accepted.push(packet); }
                }
            }
        }
        // All reference bindings for this rule are signed, before any RHS writes.
        // Resolve alternate certificates against the same input key used by the receiver.
        if let Some(mut audit) = self.recall.take() {
            let teacher_counts = std::mem::take(&mut self.counts);
            for p in audit.queue.remove(&(run, rid)).unwrap_or_default() {
                let (teacher, reason) = match self.check(g, rid, wm, &p)? {
                    Ok(answer) => {
                        let key = (rid, answer.input_values(&rule.inputs).cloned().collect());
                        match self.signing.get(&key) {
                            Some(id) => (Some(*id), "match"),
                            None => (None, "off_reference"),
                        }
                    }
                    Err(reason) => (None, reason),
                };
                audit.verdicts.push((run, p.token, teacher, reason));
            }
            self.counts = teacher_counts;
            self.recall = Some(audit);
        }
        self.verify_time += started.elapsed();
        Ok(answers)
    }
    fn admit(&mut self, g: &Graph, rid: usize, wm: u64, packet: &Request) -> Result<(Option<Instance>, &'static str)> {
        match self.check(g, rid, wm, packet)? {
            Ok(answer) => {
                let key = (rid, answer.input_values(&g.program.rules[rid].inputs).cloned().collect());
                match self.signing.entry(key) {
                    std::collections::btree_map::Entry::Vacant(slot) => {
                        slot.insert(packet.token);
                        self.counts.accepted += 1;
                        Ok((Some(answer), "accepted"))
                    }
                    std::collections::btree_map::Entry::Occupied(slot) => {
                        if packet.token < higher::INTERNAL && let Some(layouts)=&mut self.layouts {
                            layouts.completed_step(*slot.get(),"external_alternative");
                        }
                        self.counts.duplicates += 1;
                        Ok((None, "duplicate"))
                    }
                }
            }
            Err(reason) => {
                *self.counts.rejected.entry(reason).or_default() += 1;
                Ok((None, reason))
            }
        }
    }
    fn bind_named(&self, g: &Graph, table: usize, atom: &crate::program::Atom, p: &Premise,
                  witness: Dependency, env: &mut BTreeMap<usize, Value>)
        -> Result<std::result::Result<u64, &'static str>> {
        let Some(row) = g.row(witness)? else { return Ok(Err("retired")); };
        if row.hidden { return Ok(Err("hidden")); }
        if row.table != table { return Ok(Err("type")); }
        if row.epoch != p.version || row.epoch >= g.epoch { return Ok(Err("version")); }
        if row.values.len() != atom.args.len() || !atom.args.iter().zip(row.values.iter())
            .all(|(a, v)| bind_query(a, v, env, g)) { return Ok(Err("binding")); }
        Ok(Ok(row.epoch))
    }

    fn check_prefixes(&self, g: &Graph, probe: &PrefixProbe) -> Result<(Vec<Vec<bool>>, usize)> {
        let atoms: Vec<_> = g.program.rules[probe.rule].query.iter().filter_map(|a| match a.call {
            Call::Table(t) => Some((t, a)),
            _ => None,
        }).collect();
        if probe.roles.is_empty() || probe.roles.iter().any(|&r| r >= atoms.len())
            || probe.roles.iter().collect::<BTreeSet<_>>().len() != probe.roles.len() {
            return Err("invalid partial proof roles".into());
        }
        let (last, prior) = probe.roles.split_last().unwrap();
        let mut reads = 0;
        let mut bind = |role: usize, p: &Premise, env: &mut BTreeMap<usize, Value>| -> Result<bool> {
            let (table, atom) = atoms[role];
            let Some(w) = self.resolve(p.address) else { return Ok(false); };
            reads += 1;
            Ok(self.bind_named(g, table, atom, p, w, env)?.is_ok())
        };
        let mut replies = Vec::with_capacity(probe.rows.len());
        for (prefix, choices) in &probe.rows {
            if prior.len() != prefix.len() { return Err("partial proof arity".into()); }
            let mut env = BTreeMap::new();
            let mut valid = true;
            for (&role, p) in prior.iter().zip(prefix) {
                if !bind(role, p, &mut env)? { valid = false; break; }
            }
            let mut row = Vec::with_capacity(choices.len());
            for p in choices {
                row.push(valid && bind(*last, p, &mut env.clone())?);
            }
            replies.push(row);
        }
        Ok((replies, reads))
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
            match self.bind_named(g, table, atom, parent, w, &mut env)? {
                Ok(version) => epoch = epoch.max(version),
                Err(reason) => return Ok(Err(reason)),
            }
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
