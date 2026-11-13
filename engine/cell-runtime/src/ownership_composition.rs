//! Checked Entry substitutions compose immutable port programs. Runtime frame
//! locations are instance parameters, never part of a shared shape's identity.
use super::*;
#[path = "ownership_conditions.rs"]
pub mod conditions;
#[path = "ownership_effects.rs"]
pub mod effects;
#[path = "ownership_queries.rs"]
pub mod queries;
#[path = "ownership_saturation.rs"]
mod saturation;
#[path = "ownership_witness_plan.rs"]
mod witness_plan;
#[path = "ownership_join_trace.rs"]
mod join_trace;

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub struct Source {
    pub symbol: usize,
    pub entry: usize,
    pub column: usize,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq, Hash)]
pub struct Shape {
    pub programs: Vec<usize>,
    pub ports: Vec<Arc<Vec<usize>>>,
    pub signals: Vec<Arc<Vec<Instruction>>>,
    /// First introduction of each shared symbol. Appending preserves origins.
    #[serde(skip)]
    pub origins: Vec<(usize, usize)>,
    pub last_substitutions: usize,
}
#[derive(Clone, Debug, Serialize, PartialEq, Eq, Hash)]
pub struct Instruction {
    pub frame: usize,
    pub op: u32,
}
impl Shape {
    /// Project the authoritative static wiring instead of owning another copy
    /// of every instruction's field incidences. Enumeration preserves order.
    pub fn columns<'a>(&'a self, programs: &'a [Arc<PortProgram>], symbol: usize, step: &Instruction)
        -> impl Iterator<Item = usize> + 'a
    {
        let ports = &self.ports[step.frame];
        programs[self.programs[step.frame]].fields[step.op as usize].iter().enumerate()
            .filter_map(move |(column, local)| local.is_some_and(|local| ports[local] == symbol).then_some(column))
    }
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
        shape.last_substitutions = substitutions.len();
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
                    shape.signals.push(Arc::new(Vec::new()));
                    shape.origins.push((frame, local));
                    new
                };
            ports.push(symbol);
            if !touched.contains(&symbol) {
                touched.push(symbol);
                copied_steps += shape.signals[symbol].len();
            }
            copied_steps += steps.len();
            Arc::make_mut(&mut shape.signals[symbol]).extend(steps.iter().map(|s| Instruction {
                frame,
                op: s.op,
            }));
        }
        // Several checked inputs may substitute to one symbol. Keep one site;
        // its columns are already encoded by the program fields and port map.
        // Only modified slices copy handles; untouched slices and all previous
        // frame port maps retain their existing allocations.
        for symbol in touched {
            let steps = Arc::make_mut(&mut shape.signals[symbol]);
            let prefix = steps.partition_point(|s| s.frame < frame);
            steps[prefix..].sort_unstable_by_key(|s| s.op);
            steps.dedup_by_key(|step| (step.frame, step.op));
        }
        shape.ports.push(Arc::new(ports));
        (shape, copied_steps)
    }
}

/// A checked Entry route inside a bounded fragment, without instance IDs.
/// Query Entries keep their positions; a completed RHS operation uses the
/// query-Entry count plus its source operation position.
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Hop {
    pub source_frame: usize,
    pub rule: usize,
    pub entry: usize,
    pub op: u32,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct Fragment {
    pub root: usize,
    pub hops: Vec<Hop>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Key {
    pub shape: usize,
    pub hop: Hop,
}
#[derive(Clone, Debug, Default, Serialize, PartialEq, Eq)]
pub struct Plan {
    pub sources: Vec<Vec<Source>>,
    pub active_rules: Vec<bool>,
    pub result_rules: Vec<bool>,
    #[serde(skip)]
    pub shapes: Vec<Arc<Shape>>,
    /// Re-derived from checked wiring, never trusted from a profile.
    #[serde(skip)]
    pub conditions: Vec<Arc<conditions::Plan>>,
    #[serde(skip)]
    pub effects: Vec<Arc<effects::Plan>>,
    #[serde(skip)]
    pub queries: Vec<Arc<queries::Plan>>,
    pub fragments: Vec<Fragment>,
    pub transitions: Vec<(Key, usize)>,
    pub max_frames: usize,
}
/// Profiles select code; they never authorize equality. Rebinding a profile to
/// different source requires generating new checked observations.
pub fn source_digest(raw: &J) -> String {
    crate::checksum::artifact_digest_excluding_root(
        raw,
        &["sha256", "ownership_markers", "ownership_fragments", "ownership_witnesses"],
    )
}
/// A bounded training/catalog policy, never evidence for an equality.
pub fn checked_frame_limit(raw: Option<&J>) -> Result<usize> {
    let n = match raw {
        None => 4,
        Some(value) => value.as_u64().ok_or("max_frames must be an integer")?,
    };
    if !(2..=32).contains(&n) { return Err("max_frames must be in 2..=32".into()); }
    Ok(n as usize)
}
/// Rank repeated, actually used local continuations within a static code budget.
/// The score is a proposal heuristic. Whole-execution timing admits speedups.
pub fn select_profile(profile: &J) -> Result<J> {
    select_profile_with_budget(profile,256,16_384)
}
/// Resource bounds select code only; typed substitutions still prove every hop.
pub fn select_profile_with_budget(profile:&J,max_fragments:usize,instruction_handles:u64)->Result<J> {
    if !(1..=4096).contains(&max_fragments) || !(1..=1_048_576).contains(&instruction_handles) {
        return Err("ownership selection budget outside finite bounds".into());
    }
    let format = wire::Format::profile(profile)?;
    let minimum_activations=profile.get("minimum_activations")
        .map(|v|v.as_u64().ok_or("invalid minimum activations")).transpose()?.unwrap_or(2);
    if minimum_activations==0 {return Err("selection requires actual activation evidence".into());}
    let max_frames = checked_frame_limit(profile.get("max_frames"))?;
    let records = profile["records"]
        .as_array()
        .ok_or("missing fragment observations")?;
    let mut ranked = Vec::new();
    let mut code_costs = BTreeMap::new();
    for row in records {
        let obs = &row["observed"];
        let uses = obs["activations"]
            .as_u64()
            .ok_or("missing actual fragment activations")?;
        let saved = obs["binding_records_saved"]
            .as_u64()
            .ok_or("missing binding savings")?;
        let probes = obs["transition_probes"]
            .as_u64()
            .ok_or("missing transition costs")?;
        let cost = row["static_instruction_handles"]
            .as_u64()
            .ok_or("missing code cost")?;
        let net = 2 * i128::from(saved) - i128::from(probes);
        let fragment: Fragment =
            serde_json::from_value(row["fragment"].clone()).map_err(|e| e.to_string())?;
        if fragment.hops.len() >= max_frames { return Err("profile fragment exceeds max_frames".into()); }
        code_costs.insert(fragment.clone(), cost);
        if uses >= minimum_activations && net > 0 {
            ranked.push((net as f64 / (1.0 + cost as f64), fragment, cost, net));
        }
    }
    ranked.sort_by(|a, b| b.0.total_cmp(&a.0).then(a.1.cmp(&b.1)));
    let mut selected = Vec::new();
    let mut handles = 0;
    let mut net = 0;
    let mut prepared = BTreeSet::new();
    for (_, fragment, cost, credit) in ranked {
        let prefixes = (1..=fragment.hops.len())
            .map(|n| Fragment {
                root: fragment.root,
                hops: fragment.hops[..n].to_vec(),
            })
            .filter(|prefix| !prepared.contains(prefix))
            .collect::<Vec<_>>();
        let added = prefixes
            .iter()
            .map(|p| code_costs.get(p).copied().unwrap_or(cost))
            .sum::<u64>();
        if selected.len() < max_fragments && handles + added <= instruction_handles {
            prepared.extend(prefixes);
            selected.push(fragment);
            handles += added;
            net += credit;
        }
    }
    Ok(
        json!({"schema":format.fragment_schema(),"source":profile["source"],"max_frames":max_frames,"max_fragments":max_fragments,"fragments":selected,
        "ranking":{"minimum_activations":minimum_activations,"max_fragments":max_fragments,"instruction_handle_budget":instruction_handles,
            "charged_static_handles":handles,"sum_of_candidate_scores_not_global_savings":net,"alternatives_overlap":true,
            "rule":"rank actual avoided binding/boundary record operations minus transition probes per static instruction handle; include required prefixes",
            "performance_admission":"unvalidated ranking; requires whole-execution baseline comparison"}}),
    )
}
impl Plan {
    #[cfg(feature = "storage-metrics")]
    pub(crate) fn release_storage_by_field(self, live_bytes: &impl Fn() -> usize, rows: &mut Vec<(&'static str, usize)>) {
        assert!(rows.capacity() - rows.len() >= 32);
        let before = live_bytes();
        drop(self.sources);
        rows.push(("composition.sources", before - live_bytes()));
        let before = live_bytes();
        drop(self.active_rules);
        drop(self.result_rules);
        rows.push(("composition.active_rules", before - live_bytes()));
        let before = live_bytes();
        drop(self.shapes);
        rows.push(("composition.shapes", before - live_bytes()));
        let before = live_bytes();
        drop(self.conditions);
        rows.push(("composition.conditions", before - live_bytes()));
        let before = live_bytes();
        drop(self.effects);
        rows.push(("composition.effects", before - live_bytes()));
        let before = live_bytes();
        drop(self.queries);
        rows.push(("composition.queries", before - live_bytes()));
        let before = live_bytes();
        drop(self.fragments);
        rows.push(("composition.fragments", before - live_bytes()));
        let before = live_bytes();
        drop(self.transitions);
        rows.push(("composition.transitions", before - live_bytes()));
    }
    pub(super) fn derive(
        p: &Program,
        markers: &[Marker],
        programs: &[Arc<PortProgram>],
        entries: &[Vec<usize>],
        format: wire::Format,
    ) -> Result<Self> {
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
                // A completed constructor establishes the same row relation
                // as a matched Entry. Reserve an immutable Entry position per
                // source operation; runtime keeps only one actual candidate.
                for (op,instruction) in p.templates[r.template].ops.iter().enumerate() {
                    if !matches!(instruction,Op::Let(_,Call::Table(t),_) if p.tables[*t].constructor) {continue;}
                    for (column,symbol) in program.fields[op].iter().enumerate() {
                        if let Some(symbol)=symbol {
                            sources.push(Source{symbol:*symbol,entry:entries[rid].len()+op,column});
                        }
                    }
                }
                sources
            })
            .collect();
        let mut plan = Self {
            sources,
            conditions: vec![],
            effects: vec![],
            queries: vec![],
            active_rules: vec![false; p.rules.len()],
            result_rules: vec![false; p.rules.len()],
            shapes: programs
                .iter()
                .enumerate()
                .map(|(id, p)| Arc::new(Shape::initial(id, p)))
                .collect(),
            fragments: (0..programs.len())
                .map(|root| Fragment { root, hops: vec![] })
                .collect(),
            transitions: vec![],
            max_frames: checked_frame_limit(p.artifact.get("ownership_fragments").and_then(|f|f.get("max_frames")))?,
        };
        let mut transitions = BTreeMap::new();
        // Guard history selects a transition; code identity is just the local
        // programs and symbolic wiring. Equivalent prefixes share one state.
        let mut intern: HashMap<Shape, usize> = plan
            .shapes
            .iter()
            .enumerate()
            .map(|(id, s)| ((**s).clone(), id))
            .collect();
        if let Some(raw) = p.artifact.get("ownership_fragments") {
            if raw["schema"] != format.fragment_schema()
                || raw["source"] != source_digest(&p.artifact)
            {
                return Err("ownership fragments have a different source or schema".into());
            }
            let selected: Vec<Fragment> = serde_json::from_value(raw["fragments"].clone())
                .map_err(|e| format!("invalid ownership fragments: {e}"))?;
            let budget=raw.get("max_fragments").map(|v|v.as_u64().ok_or("invalid fragment budget"))
                .transpose()?.unwrap_or(256);
            if !(1..=4096).contains(&budget) || selected.len() as u64 > budget {
                return Err("ownership fragment budget exceeded".into());
            }
            for fragment in selected {
                if fragment.root >= programs.len() || fragment.hops.len() >= plan.max_frames {
                    return Err("invalid ownership fragment root or extent".into());
                }
                let mut parent = fragment.root;
                for hop in fragment.hops {
                    let key = Key {
                        shape: parent,
                        hop: hop.clone(),
                    };
                    parent = if let Some(&id) = transitions.get(&key) {
                        id
                    } else {
                        let program = p
                            .rules
                            .get(hop.rule)
                            .map(|r| markers[r.template].program_id)
                            .ok_or("ownership fragment rule out of bounds")?;
                        let subst = plan
                            .substitutions(programs, parent, &hop)
                            .ok_or("ownership fragment has no checked input substitution")?;
                        let code = plan.shapes[parent]
                            .append(program, &programs[program], &subst)
                            .0;
                        let mut prefix = plan.fragments[parent].clone();
                        prefix.hops.push(hop);
                        let id = if let Some(&id) = intern.get(&code) {
                            id
                        } else {
                            let id = plan.shapes.len();
                            intern.insert(code.clone(), id);
                            plan.shapes.push(Arc::new(code));
                            plan.fragments.push(prefix);
                            id
                        };
                        transitions.insert(key, id);
                        id
                    };
                }
            }
        }
        plan.transitions = transitions.into_iter().collect();
        for (key, _) in &plan.transitions {
            plan.active_rules[key.hop.rule] = true;
            plan.result_rules[key.hop.rule] |= key.hop.entry>=entries[key.hop.rule].len();
        }
        Ok(plan)
    }
    pub fn prepare_effects(&mut self, programs: &[Arc<PortProgram>]) {
        if self.effects.is_empty() {
            self.effects = self
                .shapes
                .iter()
                .map(|shape| Arc::new(effects::Plan::derive(shape, programs)))
                .collect();
        }
    }
    pub fn prepare_queries(&mut self, programs: &[Arc<PortProgram>]) {
        if self.queries.is_empty() {
            // The interner exists only while compiling; no runtime lookup or
            // extra maintained binding directory is introduced.
            let mut shared = std::collections::HashSet::new();
            self.queries = self.shapes.iter().map(|shape| {
                let mut plan = queries::Plan::derive(shape, programs);
                plan.share_columns(&mut shared);
                Arc::new(plan)
            }).collect();
        }
    }
    pub fn prepare_conditions(&mut self, programs: &[Arc<PortProgram>], templates: &[Template], markers: &[Marker]) {
        if self.conditions.is_empty() {
            let operators = conditions::operators(templates, markers, programs);
            let mut sites = std::collections::HashSet::new();
            let mut conditions = std::collections::HashSet::new();
            self.conditions = self.shapes.iter().map(|shape| {
                let mut plan = conditions::Plan::derive(shape, programs, &operators);
                // Full typed code equality, not observed instance equality.
                // Local site/symbol indices retain their original meaning.
                for site in &mut plan.sites {
                    if let Some(shared) = sites.get(site) {
                        *site = Arc::clone(shared);
                    } else {
                        sites.insert(site.clone());
                    }
                }
                for condition in &mut plan.conditions {
                    if let Some(shared) = conditions.get(condition) {
                        *condition = Arc::clone(shared);
                    } else {
                        conditions.insert(condition.clone());
                    }
                }
                Arc::new(plan)
            }).collect();
        }
    }
    /// Check a migrated candidate using the same typed substitutions as derive.
    /// This proves wiring availability, not observed frequency or net savings.
    pub fn supports_fragment(&self, p:&Program, fragment:&Fragment)->bool {
        let programs=&p.cell_ownership.programs;
        if fragment.root>=programs.len() || fragment.hops.len()>=self.max_frames {return false;}
        let Some(root)=self.shapes.get(fragment.root) else {return false;};
        let mut shape=(**root).clone();
        for hop in &fragment.hops {
            let Some(rule)=p.rules.get(hop.rule) else {return false;};
            let program=p.cell_ownership.markers[rule.template].program_id;
            let Some(subst)=substitutions(&self.sources,programs,&shape,hop) else {return false;};
            shape=shape.append(program,&programs[program],&subst).0;
        }
        true
    }
    /// Derivation emits this immutable directory in Key order. Production
    /// instances reuse it instead of copying it into a per-Graph hash table.
    pub fn transition(&self, key:&Key)->Option<usize> {
        let index=self.transitions.binary_search_by(|(candidate,_)|candidate.cmp(key)).ok()?;
        Some(self.transitions[index].1)
    }
    fn substitutions(
        &self,
        programs: &[Arc<PortProgram>],
        shape: usize,
        hop: &Hop,
    ) -> Option<Vec<(usize, usize)>> {
        substitutions(&self.sources, programs, self.shapes.get(shape)?, hop)
    }
}
fn substitutions(
    sources: &[Vec<Source>],
    programs: &[Arc<PortProgram>],
    shape: &Shape,
    hop: &Hop,
) -> Option<Vec<(usize, usize)>> {
    let producer = *shape.programs.get(hop.source_frame)?;
    let fields = programs[producer].fields.get(hop.op as usize)?;
    let mut subst = BTreeMap::new();
    for source in sources
        .get(hop.rule)?
        .iter()
        .filter(|s| s.entry == hop.entry)
    {
        let symbol = fields.get(source.column).copied().flatten()?;
        subst
            .entry(source.symbol)
            .or_insert(shape.ports[hop.source_frame][symbol]);
    }
    (!subst.is_empty()).then(|| subst.into_iter().collect())
}
#[derive(Clone, Debug, Default, Serialize)]
pub struct Observation {
    pub activations: u64,
    pub binding_records_saved: u64,
    pub transition_probes: u64,
}
#[derive(Default)]
pub(super) struct CatalogTrace {
    max_frames: usize,
    records: BTreeMap<Key, (Fragment, u64, u64, usize)>,
    uncovered_births: u64,
    admissions: BTreeMap<(usize, Option<usize>, &'static str), u64>,
    saturation: saturation::Trace,
    joins: join_trace::Trace,
}
#[derive(Default)]
pub(super) struct Training {
    fragments: Vec<Fragment>,
    observations: BTreeMap<usize, Observation>,
    joined: HashMap<u32, usize>,
    seen: BTreeSet<(u32, usize)>,
}
pub(super) struct Component {
    pub shape: usize,
    pub frames: smallvec::SmallVec<[u32; 4]>,
    // Instance values only. Static use lists remain in Shape; live facts are
    // already recorded by Graph. A bound slot never changes; equality is read
    // through Parents. Slots survive until the component retires.
    pub signals: Vec<Option<u64>>,
}
#[derive(Clone, Copy)]
pub(super) struct Frame {
    pub component: u32,
    pub ordinal: usize,
    /// Checked marker selecting shared native-port and operator code arrays.
    /// This occupies the former port-program ID slot, without growing a frame.
    pub code: usize,
}
/// Stable frame addresses are normally dense. Retain outlier support for
/// imported IDs without paying a hash lookup on every local port access.
#[derive(Default)]
pub(super) struct Frames {
    // Logical Cell IDs never move. Only live frame records occupy the arena;
    // the directory keeps a four-byte position instead of an entire Option.
    dense: Vec<u32>,
    records: Vec<(u32, Frame)>,
    outliers: HashMap<u32, u32>,
}
impl Frames {
    fn position(&self, id: &u32) -> Option<usize> {
        let n = self.dense.get(*id as usize).copied().unwrap_or(0);
        let n = if n != 0 { n } else { *self.outliers.get(id)? };
        Some(n as usize - 1)
    }
    pub fn get(&self, id: &u32) -> Option<&Frame> {
        Some(&self.records[self.position(id)?].1)
    }
    pub fn contains_key(&self, id: &u32) -> bool { self.position(id).is_some() }
    fn address(&mut self, id: u32, position: u32) {
        let n = id as usize;
        if n <= self.dense.len().saturating_add(65536) {
            if n >= self.dense.len() { self.dense.resize(n+1,0); }
            self.dense[n] = position;
            self.outliers.remove(&id);
        } else {
            self.outliers.insert(id,position);
        }
    }
    pub fn insert(&mut self, id: u32, frame: Frame) {
        if let Some(i) = self.position(&id) { self.records[i].1 = frame; return; }
        let position = u32::try_from(self.records.len()+1).expect("too many live composition frames");
        self.records.push((id,frame));
        self.address(id,position);
    }
    pub fn remove(&mut self, id: &u32) {
        let Some(i) = self.position(id) else { return; };
        if let Some(position) = self.dense.get_mut(*id as usize) { *position = 0; }
        self.outliers.remove(id);
        self.records.swap_remove(i);
        if let Some(&(moved,_)) = self.records.get(i) { self.address(moved, i as u32+1); }
    }
    pub fn len(&self) -> usize { self.records.len() }
}
impl std::ops::Index<&u32> for Frames {
    type Output = Frame;
    fn index(&self, id: &u32) -> &Frame {
        self.get(id).expect("missing composition frame")
    }
}
#[derive(Clone, Copy)]
pub(super) struct Cursor {
    pub signal: Signal,
    pub position: usize,
    pub fact: FactRef,
}
/// The evidence for the current source application. This moves with a suspended
/// execution; it is not a second binding or a subscription to its producers.
pub(crate) struct Entry {
    pub rule: usize,
    pub template: usize,
    pub anchors: smallvec::SmallVec<[Option<Dependency>; 4]>,
    result:Option<(usize,FactRef)>,
}
pub(super) struct Runtime {
    pub components: crate::read_epoch::Slots<Option<Component>>,
    // Coordinator-only lifetime metadata. Guards never consult these counts.
    pub live_facts: Vec<usize>,
    pub frames: Frames,
    pub shapes: Arc<Vec<Option<Arc<Shape>>>>,
    pub learned_transitions: HashMap<Key, usize>,
    pub training: Option<Training>,
    pub catalog_trace: Option<Box<CatalogTrace>>,
    pub entry: Option<Entry>,
    pub witness_selection:std::cell::Cell<Option<super::witnesses::Selection>>,
    pub heap: Vec<Cursor>,
    pub columns: Vec<usize>,
}
impl Runtime {
    #[inline]
    pub(super) fn port(&self, frame: Frame, local: usize) -> ports::PortRef {
        let shape = self.components[frame.component as usize].as_ref().unwrap().shape;
        ports::PortRef {
            component: frame.component,
            symbol: self.shapes[shape].as_ref().unwrap().ports[frame.ordinal][local],
        }
    }
    pub(super) fn signal(&self, plan: &super::Plan, component: u32, symbol: usize) -> Signal {
        let class = plan.query_classes.as_ref().map_or(0, |classes| {
            let c = self.components[component as usize].as_ref().unwrap();
            let (frame, local) = self.shapes[c.shape].as_ref().unwrap().origins[symbol];
            classes.symbols[self.frames[&c.frames[frame]].code][local]
        });
        Signal { class, component, symbol }
    }
    pub fn new(p: &Plan) -> Self {
        Self {
            components: Default::default(),
            live_facts: vec![],
            frames: Frames::default(),
            shapes: Arc::new(p.shapes.iter().cloned().map(Some).collect()),
            learned_transitions: HashMap::default(),
            training: None,
            catalog_trace: None,
            entry: None,
            witness_selection:Default::default(),
            heap: vec![],
            columns: vec![],
        }
    }
    /// Diagnostic only: count actual first cross-frame binding reuse, not
    /// potential symbolic substitutions or repeated uses of one consumer slot.
    pub fn observe_shared_binding(&mut self, cell: u32, local: usize, symbol: usize) {
        let Some(t) = &mut self.training else { return };
        let Some(&record) = t.joined.get(&cell) else {
            return;
        };
        let frame = self.frames[&cell];
        let shape = self.shapes[record].as_ref().unwrap();
        if shape.ports[..frame.ordinal]
            .iter()
            .any(|ports| ports.contains(&symbol))
            && t.seen.insert((cell, local))
        {
            t.observations
                .get_mut(&record)
                .unwrap()
                .binding_records_saved += 1;
        }
    }
}
impl Graph {
    /// Observe extensions without installing speculative shapes or changing
    /// production's frame bound. The trace is not an admitted Bake profile.
    pub fn trace_ownership_catalog(&mut self, max_frames: usize) -> Result<()> {
        let max_frames = checked_frame_limit(Some(&json!(max_frames)))?;
        let m = self.ownership.as_mut().ok_or("enable ownership before tracing")?;
        if m.stats.marker_entries != 0 || m.composition.training.is_some() || m.composition.catalog_trace.is_some() {
            return Err("start catalog tracing once, before execution and without exploratory training".into());
        }
        m.composition.catalog_trace = Some(Box::new(CatalogTrace { max_frames, ..Default::default() }));
        m.trace_barriers();
        Ok(())
    }
    pub fn ownership_catalog_trace(&self) -> Result<J> {
        let m = self.ownership.as_ref().ok_or("ownership is disabled")?;
        let trace = m.composition.catalog_trace.as_ref().ok_or("catalog tracing is disabled")?;
        let records = trace.records.iter().map(|(key, (fragment, births, inputs, handles))| json!({
            "source_shape":key.shape,"fragment":fragment,"matched_births":births,
            "available_shared_inputs":inputs,"static_instruction_handles":handles,
        })).collect::<Vec<_>>();
        Ok(json!({"schema":"eggfuse-ownership-catalog-trace/v1", "source":source_digest(&self.program.artifact),
            "catalog_sha256":self.program.artifact["sha256"], "max_frames":trace.max_frames,
            "executed_max_frames":self.program.cell_ownership.composition.max_frames,
            "seed_shapes":self.program.cell_ownership.composition.shapes.len(),
            "seed_transitions":self.program.cell_ownership.composition.transitions.len(),
            "uncovered_births":trace.uncovered_births,"alternatives_overlap":true,
            "scope":"observed unmatched owned births in installed catalog execution; proposed reuse is not saved work or committed mutations",
            "admissions":trace.admissions.iter().map(|(&(template,rule,reason),&count)|
                json!({"template":template,"rule":rule,"reason":reason,"count":count})).collect::<Vec<_>>(),
            "admission_scope":"new composition frames only; birth/join/fallback count frames, anchor reasons count attempted alternatives; not final singleton attribution",
            "records":records,"saturation":trace.saturation.report(),"multi_source":trace.joins.report()}))
    }
    pub fn train_ownership_fragments(&mut self) -> Result<()> {
        self.train_ownership_fragments_with_limit(4)
    }
    pub fn train_ownership_fragments_with_limit(&mut self, max_frames: usize) -> Result<()> {
        self.start_ownership_fragment_training(max_frames, false)
    }
    /// Learn continuations while executing the currently checked catalog.
    /// Existing shape IDs and proof programs remain authoritative.
    pub fn continue_ownership_fragment_training(&mut self, max_frames: usize) -> Result<()> {
        self.start_ownership_fragment_training(max_frames, true)
    }
    fn start_ownership_fragment_training(&mut self, max_frames: usize, extend: bool) -> Result<()> {
        let max_frames = checked_frame_limit(Some(&json!(max_frames)))?;
        let m = self
            .ownership
            .as_mut()
            .ok_or("enable ownership before profiling fragments")?;
        if m.stats.marker_entries != 0 || m.composition.catalog_trace.is_some() {
            return Err("start fragment profiling before execution and without catalog tracing".into());
        }
        if !extend && !self.program.cell_ownership.composition.transitions.is_empty() {
            return Err("profile fragments from the unbaked source catalog".into());
        }
        if self.program.cell_ownership.composition.shapes.iter().any(|s| s.programs.len() > max_frames) {
            return Err("training limit is smaller than the existing catalog".into());
        }
        self.program.cell_ownership.composition.max_frames = max_frames;
        m.composition.training = Some(Training {
            fragments: self.program.cell_ownership.composition.fragments.clone(),
            ..Training::default()
        });
        m.trace_barriers();
        Ok(())
    }
    pub fn ownership_fragment_profile(&self) -> Result<J> {
        let m = self.ownership.as_ref().ok_or("ownership is disabled")?;
        let t = m
            .composition
            .training
            .as_ref()
            .ok_or("fragment profiling is disabled")?;
        // Project the actually checked last edge to a local producer/receiver
        // pair as well. This shares the same continuation across unrelated
        // prefixes; candidate records overlap and their credit must not be added
        // as whole-execution savings.
        let mut candidates = BTreeMap::<Fragment, (Observation, usize)>::new();
        for (&id, obs) in &t.observations {
            let shape = m.composition.shapes[id].as_ref().unwrap();
            let full = t.fragments[id].clone();
            let handles = shape.signals.iter().map(|s| s.len()).sum::<usize>();
            let entry = candidates
                .entry(full.clone())
                .or_insert((Observation::default(), handles));
            entry.0.activations += obs.activations;
            entry.0.binding_records_saved += obs.binding_records_saved;
            entry.0.transition_probes += obs.transition_probes;
            if full.hops.len() > 1 {
                let last = full.hops.last().unwrap();
                let root = shape.programs[last.source_frame];
                let hop = Hop {
                    source_frame: 0,
                    ..last.clone()
                };
                let pair = Fragment {
                    root,
                    hops: vec![hop.clone()],
                };
                let base = &self.program.cell_ownership.composition.shapes[root];
                let subst = substitutions(
                    &self.program.cell_ownership.composition.sources,
                    &self.program.cell_ownership.programs,
                    base,
                    &hop,
                )
                .unwrap();
                let program = *shape.programs.last().unwrap();
                let code = base
                    .append(
                        program,
                        &self.program.cell_ownership.programs[program],
                        &subst,
                    )
                    .0;
                let handles = code.signals.iter().map(|s| s.len()).sum::<usize>();
                let entry = candidates
                    .entry(pair)
                    .or_insert((Observation::default(), handles));
                entry.0.activations += obs.activations;
                entry.0.binding_records_saved += obs.binding_records_saved;
                entry.0.transition_probes += obs.transition_probes;
            }
        }
        let records=candidates.into_iter().map(|(fragment,(obs,handles))|json!({
            "fragment":fragment,"observed":obs,"static_instruction_handles":handles,
            "net_record_operations":2 * obs.binding_records_saved as i128 - obs.transition_probes as i128,
        })).collect::<Vec<_>>();
        Ok(
            json!({"schema":self.program.cell_ownership.format.profile_schema(),"source":source_digest(&self.program.artifact),
                "max_frames":self.program.cell_ownership.composition.max_frames,
                "seed_catalog":{"shapes":self.program.cell_ownership.composition.shapes.len(),
                    "transitions":self.program.cell_ownership.composition.transitions.len()},
            "scope":"checked Entry applications with actual owned births; diagnostic training, not production latency",
            "alternatives_overlap":true,
            "credit":"one avoided binding creation plus one avoided boundary insertion per observed shared input, minus transition probes; uncalibrated ranking only",
            "records":records}),
        )
    }
    pub(super) fn composition_entry(&mut self, rid: usize, anchors: smallvec::SmallVec<[Option<Dependency>; 4]>) {
        self.observe_component_join(rid, &anchors);
        let Some(m) = &mut self.ownership else { return };
        debug_assert!(m.composition.entry.is_none());
        m.composition.entry = Some(Entry { rule: rid,
            template: self.program.rules[rid].template, anchors, result:None });
    }
    /// Actual completed RHS evidence, held only until this source finishes.
    /// No bindings, consumer lists or retained result history are added.
    #[cfg(feature="sparse-cells")]
    pub(crate) fn composition_result_entry(&mut self,cell:u32,op:usize,witness:Dependency,visible:bool) {
        if !visible {return;}
        let Some(m)=&mut self.ownership else {return;};
        let Some(entry)=m.composition.entry.as_mut() else {return;};
        m.stats.composition_entry_reads+=1;
        if !self.program.cell_ownership.composition.result_rules[entry.rule]
            && m.composition.training.is_none() && m.composition.catalog_trace.is_none() {return;}
        let Dependency::Fact(f)=witness else {return;};
        if f.cell==cell || m.composition.frames.contains_key(&cell)
            || !m.composition.frames.contains_key(&f.cell) {return;}
        let template=self.active_rhs.as_ref().filter(|(id,_)|*id==cell).map(|(_,c)|c.template)
            .or_else(||self.cells.cell_metadata(cell).map(|c|c.template));
        if template!=Some(entry.template) {return;}
        let slot=self.program.cell_ownership.entries[entry.rule].len()+op;
        let program=&self.program.cell_ownership.markers[entry.template].program;
        if !program.fields.get(op).and_then(|f|f.last()).is_some_and(Option::is_some) {return;}
        entry.result=Some((slot,f));
        m.stats.composition_result_writes+=1;
    }
    pub(super) fn ensure_composition_frame(&mut self, cell: u32) {
        let template = self.cells.cell_metadata(cell).unwrap().template;
        let program = self.program.cell_ownership.markers[template].program_id;
        let m = self.ownership.as_mut().unwrap();
        if m.composition.frames.contains_key(&cell) {
            return;
        }
        let source_rule = m.composition.entry.as_ref().map(|e| e.rule);
        // Only explicit observation retains reasons; no instance IDs, bindings,
        // or new producer/consumer dependencies are stored.
        macro_rules! observe {
            ($reason:literal) => {
                if let Some(trace) = &mut m.composition.catalog_trace {
                    *trace.admissions.entry((template, source_rule, $reason)).or_default() += 1;
                }
            };
        }
        observe!("birth");
        if m.composition.entry.is_none() { observe!("no_entry"); }
        else if m.composition.entry.as_ref().is_some_and(|e|e.template != template) {
            observe!("entry_template_mismatch");
        }
        let mut selected = None;
        let mut result_join=false;
        let mut proposals = Vec::new(); // Allocates only in explicit trace mode.
        if let Some(source) = &m.composition.entry
            && source.template == template {
            let rid = source.rule;
            // Reproduce the installed catalog's choice before exploring an
            // uncovered anchor. Otherwise training can steal a production hit.
            let prefer_catalog = m.composition.training.is_some()
                && !self.program.cell_ownership.composition.transitions.is_empty();
            'candidate: for pass in 0..=usize::from(prefer_catalog) {
                for (entry, anchor) in source.result.iter().map(|&(entry,f)|(entry,Some(Dependency::Fact(f))))
                    .chain(source.anchors.iter().copied().enumerate()) {
                    observe!("anchor_attempt");
                    m.stats.composition_entry_reads += 1;
                    let Some(Dependency::Fact(f)) = anchor else {
                        observe!("anchor_not_fact");
                        continue;
                    };
                    if !self
                        .cells.fact_state(f)
                        .is_some_and(|s| s.owned && (entry<self.program.cell_ownership.entries[rid].len() || !s.hidden))
                    {
                        observe!("anchor_not_owned");
                        m.stats.composition_missing_sources += 1;
                        continue;
                    }
                    let Some(frame) = m.composition.frames.get(&f.cell).copied() else {
                        observe!("anchor_missing_frame");
                        continue;
                    };
                    let c = m.composition.components[frame.component as usize]
                        .as_ref()
                        .unwrap();
                    if let Some(trace) = &m.composition.catalog_trace {
                        if c.frames.len() < trace.max_frames && c.frames.last().is_none_or(|&last| last < cell) {
                            proposals.push(Key { shape: c.shape, hop: Hop { source_frame: frame.ordinal, rule: rid, entry, op: f.op } });
                        }
                    }
                    if c.frames.len() >= self.program.cell_ownership.composition.max_frames {
                        observe!("frame_limit");
                        m.stats.composition_capacity_cuts += 1;
                        continue;
                    }
                    if c.frames.last().is_some_and(|&last| last >= cell) {
                        observe!("source_order");
                        continue;
                    }
                    let key = Key {
                        shape: c.shape,
                        hop: Hop {
                            source_frame: frame.ordinal,
                            rule: rid,
                            entry,
                            op: f.op,
                        },
                    };
                    let baked=self.program.cell_ownership.composition.transition(&key);
                    if prefer_catalog {
                        let installed = baked.is_some();
                        if installed != (pass == 0) { continue; }
                    }
                    m.stats.composition_transition_probes += 1;
                    let shape = if let Some(shape) = baked.or_else(||m.composition.learned_transitions.get(&key).copied()) {
                        m.stats.composition_cache_hits += 1;
                        m.stats.composition_baked_hits +=
                            u64::from(shape < self.program.cell_ownership.composition.shapes.len());
                        shape
                    } else if m.composition.training.is_some() {
                        let Some(subst) = substitutions(
                            &self.program.cell_ownership.composition.sources,
                            &self.program.cell_ownership.programs,
                            m.composition.shapes[c.shape].as_ref().unwrap(),
                            &key.hop,
                        ) else {
                            continue;
                        };
                        let (code, steps) = m.composition.shapes[c.shape].as_ref().unwrap().append(
                            program,
                            &self.program.cell_ownership.programs[program],
                            &subst,
                        );
                        let t = m.composition.training.as_mut().unwrap();
                        let mut fragment = t.fragments[c.shape].clone();
                        fragment.hops.push(key.hop.clone());
                        t.fragments.push(fragment);
                        let id = m.composition.shapes.len();
                        Arc::make_mut(&mut m.composition.shapes).push(Some(Arc::new(code)));
                        m.composition.learned_transitions.insert(key, id);
                        m.stats.composition_shape_builds += 1;
                        m.stats.composition_materializations += 1;
                        m.stats.composition_shape_steps += steps as u64;
                        id
                    } else {
                        observe!("transition_not_baked");
                        m.stats.composition_unbaked_fallbacks += 1;
                        continue;
                    };
                    result_join=entry>=self.program.cell_ownership.entries[rid].len();
                    selected = Some((
                        frame.component,
                        shape,
                        self.cells.cell_metadata(f.cell).unwrap().started_epoch != self.epoch,
                    ));
                    break 'candidate;
                }
            }
        }
        if let Some((_, _, cross_stage)) = selected {
            observe!("joined");
            if cross_stage { observe!("joined_cross_stage"); }
        } else { observe!("fallback"); }
        if selected.is_none() && let Some(trace) = &mut m.composition.catalog_trace {
            trace.uncovered_births += 1;
            let plan = &self.program.cell_ownership.composition;
            for key in proposals {
                let Some(subst) = plan.substitutions(&self.program.cell_ownership.programs, key.shape, &key.hop) else { continue; };
                let entry = trace.records.entry(key.clone()).or_insert_with(|| {
                    let mut fragment = plan.fragments[key.shape].clone();
                    fragment.hops.push(key.hop.clone());
                    let code = plan.shapes[key.shape].append(program, &self.program.cell_ownership.programs[program], &subst).0;
                    let handles = code.signals.iter().map(|s|s.len()).sum();
                    (fragment, 0, 0, handles)
                });
                entry.1 += 1;
                entry.2 += subst.len() as u64;
            }
        }
        let (component, ordinal) = if let Some((component, shape, cross_stage)) = selected {
            let c = m
                .composition
                .components
                .local_mut(component as usize)
                .as_mut()
                .unwrap();
            let ordinal = c.frames.len();
            c.frames.push(cell);
            c.shape = shape;
            c.signals.resize(
                m.composition.shapes[shape].as_ref().unwrap().signals.len(),
                None,
            );
            m.stats.composition_requests += 1;
            m.stats.composition_result_joins+=u64::from(result_join);
            m.stats.composition_substituted_ports += m.composition.shapes[shape]
                .as_ref()
                .unwrap()
                .last_substitutions as u64;
            m.stats.composition_cross_stage_joins += u64::from(cross_stage);
            // All substitutions are in the precompiled port map. No runtime
            // substitution vector or instruction materialization is required.
            if let Some(t) = &mut m.composition.training {
                t.joined.insert(cell, shape);
                let obs = t.observations.entry(shape).or_default();
                obs.activations += 1;
                obs.transition_probes += 1;
            }
            (component, ordinal)
        } else {
            let id = u32::try_from(m.composition.components.len()).expect("composition capacity");
            m.composition.components.push(Some(Component {
                shape: program,
                frames: smallvec::smallvec![cell],
                signals: vec![
                    None;
                    m.composition.shapes[program]
                        .as_ref()
                        .unwrap()
                        .signals
                        .len()
                ],
            }));
            let before = m.composition.live_facts.capacity();
            m.composition.live_facts.push(0);
            m.stats.component_lifetime_growths +=
                u64::from(before != m.composition.live_facts.capacity());
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
                code: self.program.cell_ownership.markers[template].code,
            },
        );
    }
    pub(super) fn composed_signal(&self, cell: u32, local: usize) -> Signal {
        let port = self.composed_port(cell, local);
        self.ownership.as_ref().unwrap().composition.signal(
            &self.program.cell_ownership, port.component, port.symbol)
    }
    pub(super) fn composed_port(&self, cell: u32, local: usize) -> ports::PortRef {
        let m = &self.ownership.as_ref().unwrap().composition;
        m.port(m.frames[&cell], local)
    }
    pub(super) fn composition_retire_fact(&mut self, cell: u32) {
        let m = self.ownership.as_mut().unwrap();
        let f = m.composition.frames[&cell];
        m.composition.live_facts[f.component as usize] -= 1;
        m.stats.component_lifetime_updates += 1;
        if m.composition.live_facts[f.component as usize] == 0 {
            let c = m.composition.components[f.component as usize]
                .as_ref()
                .unwrap();
            for (symbol, id) in c.signals.iter().enumerate() {
                m.stats.component_signal_retire_visits += 1;
                let Some(id) = id else { continue };
                let id = m.stats.signal_root(&self.parents, *id);
                let signal = m.composition.signal(&self.program.cell_ownership, f.component, symbol);
                m.stats.signal_bindings_live -= 1;
                m.stats.signal_bindings_retired += 1;
                if let Some(set) = m.boundaries.get_mut(&id) {
                    if set.remove(&signal) {
                        m.stats.boundary_live -= 1;
                        m.stats.boundary_edges_removed += 1;
                    }
                    if set.is_empty() {
                        m.boundaries.remove(&id);
                    }
                }
            }
            // A component may die before a source frame's external users do.
            // Restore its delegated slots before invalidating the shared owner.
            for id in &c.frames {
                #[cfg(all(feature="sparse-cells",feature="storage-metrics"))]
                if self.parent_users.get(id).copied().unwrap_or(0)>0
                    && self.cells.completed_meta(*id).is_some_and(|meta|meta.symbolic_slots) {
                    let restored=self.cells.unseal_completed(*id,crate::graph::fact_states::RestoreCause::ComponentRetirement).unwrap();
                    self.cells.insert(*id,restored);
                    self.stats.shared_owner_frames_restored+=1;
                }
                if let Some(cell) = self.cells.get_mut(id) {
                    if cell.symbolic_slots {
                        let frame = m.composition.frames[id];
                        let ports = &m.composition.shapes[c.shape].as_ref().unwrap().ports[frame.ordinal];
                        let program = &self.program.cell_ownership.markers[cell.template].program;
                        for (slot, local) in program.slots.iter().enumerate() {
                            if cell.values.contains_key(&slot) { continue; }
                            if let Some(local) = local {
                                if let Some(id) = c.signals[ports[*local]] {
                                    cell.values.insert(slot, Value::Eq(id));
                                }
                            }
                        }
                        cell.symbolic_slots = false;
                    }
                }
                m.composition.frames.remove(id);
            }
            m.composition.components.retire(f.component as usize);
            m.stats.components_live -= 1;
            m.stats.components_retired += 1;
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn retained_frame_addresses_support_sparse_imports_and_dense_reuse() {
        let mut frames = Frames::default();
        let frame = Frame {
            component: 1,
            ordinal: 2,
            code: 3,
        };
        frames.insert(u32::MAX, frame);
        frames.insert(4, frame);
        frames.insert(
            4,
            Frame {
                code: 5,
                ..frame
            },
        );
        assert_eq!(frames.len(), 2);
        assert_eq!(frames[&4].code, 5);
        frames.remove(&4);
        frames.remove(&4);
        assert_eq!(frames.len(), 1);
        assert_eq!(frames[&u32::MAX].ordinal, 2);
        assert!(frames.dense.len() < 100);
    }
    #[test]
    fn appending_a_receiver_preserves_unrelated_program_storage() {
        let producer = PortProgram {
            fields: (0..200).map(|symbol| vec![Some(symbol)]).collect(),
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
            fields: vec![vec![Some(0)]],
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
        assert!(Arc::ptr_eq(&parent.ports[0], &child.ports[0]));
        for symbol in 1..200 {
            assert!(Arc::ptr_eq(&parent.signals[symbol], &child.signals[symbol]));
        }
    }
    #[test]
    fn inherited_wiring_coalesces_alias_columns_without_a_second_column_list() {
        let producer = Arc::new(PortProgram {
            fields: vec![vec![Some(0)]],
            signals: vec![vec![slices::Step { op: 0, columns: vec![0] }]],
            ..PortProgram::default()
        });
        let receiver = Arc::new(PortProgram {
            fields: vec![vec![Some(0), Some(1), None, Some(2)]],
            signals: vec![
                vec![slices::Step { op: 0, columns: vec![0] }],
                vec![slices::Step { op: 0, columns: vec![1] }],
                vec![slices::Step { op: 0, columns: vec![3] }],
            ],
            ..PortProgram::default()
        });
        let parent = Shape::initial(0, &producer);
        let child = parent.append(1, &receiver, &[(0, 0), (1, 0)]).0;
        let programs = [producer, receiver];
        assert_eq!(child.signals[0].len(), 2, "aliased inputs name one receiver site");
        assert_eq!(child.columns(&programs, 0, &child.signals[0][1]).collect::<Vec<_>>(), vec![0, 1]);
        let output = child.ports[1][2];
        assert_eq!(child.columns(&programs, output, &child.signals[output][0]).collect::<Vec<_>>(), vec![3]);
        assert_eq!(parent.columns(&programs, 0, &parent.signals[0][0]).collect::<Vec<_>>(), vec![0]);
        let effects = effects::Plan::derive(&child, &programs);
        assert_eq!(effects.signals[0][1].output, Some(output));
        assert_eq!(effects.signals[output][0].output, None, "output-only alias is not an input guard");
    }

}
