//! Frozen, append-only binary continuations. Leaves refer to validated matching
//! entries or completed typed producers. IDs are scoped to the catalog/recipe.
use crate::program::*;
use serde::{Deserialize, Serialize};
use serde_json::{Value as J, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    rc::Rc,
};
pub type Id = usize;
// None denotes a completed producer, which is never a matching entry. Some
// serializes as the old pivot number, preserving existing catalog artifacts.
pub(crate) type Entry = (usize, Option<usize>);
#[derive(Clone, Copy, Debug, Eq, PartialEq, Ord, PartialOrd, Serialize, Deserialize)]
pub struct Join {
    pub left: Id,
    pub output: usize,
    pub right: Id,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Limits {
    pub depth: usize,
    pub nodes: usize,
    pub total: usize,
    pub per_round: usize,
    pub candidates: usize,
    pub support: u64,
}
impl Default for Limits {
    fn default() -> Self {
        Self {
            depth: 4,
            nodes: 8,
            total: 64,
            per_round: 8,
            candidates: 512,
            support: 2,
        }
    }
}
impl Limits {
    pub fn validate(self) -> Result<()> {
        if [
            self.depth,
            self.nodes,
            self.total,
            self.per_round,
            self.candidates,
        ]
        .contains(&0)
            || self.support == 0
        {
            return Err("Bake limits must be positive".into());
        }
        Ok(())
    }
}
#[derive(Clone, Debug)]
struct Unit {
    path: Box<[(Option<usize>, Entry)]>,
}
impl Unit {
    // Parsed leaves are nonempty and composition concatenates nonempty paths.
    fn first(&self) -> Entry { self.path[0].1 }
    fn last(&self) -> Entry { self.path.last().expect("nonempty Cell path").1 }
    fn terminal(&self) -> bool { self.last().1.is_some() }
}
#[derive(Clone, Debug, Default)]
pub struct Catalog {
    pub limits: Limits,
    units: Vec<Unit>,
    leaves: BTreeMap<Entry, Id>,
    jumps: BTreeMap<Join, Id>,
    switch: crate::result_handoff::Switch,
    inherited: Option<Vec<bool>>,
    track_slots: bool,
}
#[derive(Clone, Copy, Debug)]
struct Segment {
    unit: Id,
    incoming: usize,
}
#[derive(Clone, Debug, Default)]
pub(crate) struct State {
    stack: Vec<Segment>,
    pub output: usize,
    pending: Option<Join>,
    pub complete: bool,
    pub direct: bool,
    capped: bool,
    last_run: usize,
    witness: Option<crate::graph::Dependency>,
    pub(crate) history: crate::result_handoff::History,
    pc: usize,
    active: Option<Id>,
    pub(crate) collect_pairs: bool,
    samples: Option<Rc<Vec<(usize, usize, Option<crate::graph::Dependency>, Option<usize>)>>>,
}
impl State {
    pub fn fused(&self, catalog: &Catalog) -> bool {
        self.active
            .or_else(|| self.stack.last().map(|s| s.unit))
            .is_some_and(|id| id >= catalog.leaves.len())
    }
}
impl Catalog {
    /// State array and completion programs; excludes allocator overhead.
    pub fn completion_storage(&self) -> J { self.switch.completion_storage() }
    /// State array and transition storage; excludes allocator overhead.
    pub fn transition_storage(&self) -> J { self.switch.transition_storage() }
    /// State array and shared capture storage; excludes allocator overhead.
    pub fn capture_storage(&self) -> J { self.switch.capture_storage() }
    /// Retained export directory and slots; excludes allocator overhead.
    pub fn export_storage(&self) -> J { self.switch.export_storage() }
    /// Retained switch dispatch arrays; excludes allocator overhead.
    pub fn dispatch_storage(&self) -> J { self.switch.dispatch_storage() }
    /// Retained path storage only; excludes tree-node overhead and other catalog data.
    pub fn path_storage(&self) -> J {
        let item=std::mem::size_of::<(Option<usize>,Entry)>();
        json!({"units":self.units.len(),"unit_capacity":self.units.capacity(),
            "unit_record_bytes":std::mem::size_of::<Unit>(),
            "unit_array_bytes":self.units.capacity()*std::mem::size_of::<Unit>(),
            "path_payload_bytes":self.units.iter().map(|u|u.path.len()*item).sum::<usize>(),
            "lookup_key_bytes":0,"lookup_payload_bytes":0})
    }
    pub(crate) fn layout_storage(&self) -> (usize,usize) { self.switch.layout_storage() }
    pub fn seed(p: &Program, limits: Limits) -> Result<J> {
        Self::seed_with_roots(p, limits, &[])
    }
    /// Roots witness a fully executed typed rule; they do not promise that its
    /// query can be matched from one anchor. Only matching leaves can be a
    /// continuation's right operand.
    pub fn seed_with_roots(p: &Program, limits: Limits, roots: &[usize]) -> Result<J> {
        limits.validate()?;
        let seed = &p.artifact["spine_blocks"];
        let entries = seed["entries"]
            .as_array()
            .ok_or("warm start requires validated spine blocks")?;
        if entries.is_empty() || entries.len().saturating_add(roots.len()) > limits.total {
            return Err("seed size outside catalog budget".into());
        }
        if roots.iter().any(|&r| r >= p.rules.len()) || roots.windows(2).any(|w| w[0] >= w[1]) {
            return Err("producer roots must be unique, sorted typed rule indices".into());
        }
        let mut plan = json!({"schema":"eggfuse-iterative/v1","recipe":p.artifact["recipe"]["sha256"],"seed":crate::checksum::artifact_digest(seed),"limits":limits,"joins":[]});
        if !roots.is_empty() {
            plan["schema"] = "eggfuse-iterative/v2".into();
            plan["producer_roots"] = json!(roots);
        }
        Ok(plan)
    }
    pub(crate) fn parse(p: &Program, raw: &J) -> Result<Self> {
        if raw.is_null() {
            return Ok(Self::default());
        }
        let limits: Limits =
            serde_json::from_value(raw["limits"].clone()).map_err(|e| e.to_string())?;
        let roots: Vec<usize> = match raw["schema"].as_str() {
            Some("eggfuse-iterative/v1") if raw.get("producer_roots").is_none() => vec![],
            Some("eggfuse-iterative/v2") => {
                serde_json::from_value(raw["producer_roots"].clone()).map_err(|e| e.to_string())?
            }
            _ => return Err("unsupported iterative catalog policy".into()),
        };
        let seed = Self::seed_with_roots(p, limits, &roots)?;
        for k in ["schema", "recipe", "seed"] {
            if raw[k] != seed[k] {
                return Err("iterative catalog source mismatch".into());
            }
        }
        let mut s = Self {
            limits,
            ..Default::default()
        };
        // Duplicate-path validation is a construction obligation, not runtime
        // state. Drop its owned keys when the checked catalog is complete.
        let mut paths = BTreeSet::new();
        for e in array(&p.artifact["spine_blocks"]["entries"])? {
            let entry = (
                e["consumer"].as_u64().unwrap() as usize,
                Some(e["pivot"].as_u64().unwrap() as usize),
            );
            if !p.spine_blocks.contains(entry.0, entry.1.unwrap()) {
                return Err("invalid leaf entry".into());
            }
            let path = vec![(None, entry)];
            let id = s.units.len();
            s.leaves.insert(entry, id);
            paths.insert(path.clone());
            s.units.push(Unit {
                path: path.into_boxed_slice(),
            });
        }
        for rule in roots {
            let entry = (rule, None);
            let path = vec![(None, entry)];
            s.leaves.insert(entry, s.units.len());
            paths.insert(path.clone());
            s.units.push(Unit {
                path: path.into_boxed_slice(),
            });
        }
        for j in array(&raw["joins"])? {
            let join: Join = serde_json::from_value(j.clone()).map_err(|e| e.to_string())?;
            let u = s
                .combine(p, join)
                .ok_or("invalid or oversized binary continuation")?;
            if s.units.len() >= limits.total || !paths.insert(u.path.to_vec()) {
                return Err("duplicate continuation or catalog full".into());
            }
            s.jumps.insert(join, s.units.len());
            s.units.push(u);
        }
        drop(paths);
        if let Some(raw) = raw.get("rhs_handoffs") {
            let (congruence, query_ports, completion) = match raw["schema"].as_str() {
                Some("eggfuse-result-switch/v1") => (false, false, false),
                Some("eggfuse-result-switch/v2") => (true, false, false),
                Some("eggfuse-result-switch/v3") => (true, true, false),
                Some("eggfuse-result-switch/v4") => (true, true, true),
                _ => return Err("unsupported cross-Run RHS proof policy".into()),
            };
            let reuse = raw["reuse_results"]
                .as_bool()
                .ok_or("missing result switch policy")?;
            s.switch = crate::result_handoff::Switch::build(
                p,
                s.units.iter().map(|u| u.path.as_ref()),
                &s.leaves,
                reuse,
                congruence,
                query_ports,
                completion,
            );
            if *raw != s.switch.artifact() {
                return Err("invalid cross-Run RHS plan".into());
            }
            s.switch.complete_cells(p, |unit| s.units[unit].last().0);
        }
        if let Some(raw) = raw.get("state_plan") {
            let mut expected = s.state_contracts(p);
            match raw["schema"].as_str() {
                Some("eggfuse-cell-state-plan/v1") => for c in expected.as_array_mut().unwrap() {
                    c.as_object_mut().unwrap().remove("slot_layout");
                    c["can_inherit"] = serde_json::json!(c.get("exports").and_then(J::as_array).is_some_and(Vec::is_empty)
                        && c["retained_stages"].as_u64().unwrap_or(0) > 0);
                },
                Some("eggfuse-cell-state-plan/v2") => (),
                _ => return Err("unsupported Cell state plan".into()),
            }
            if raw["contracts"] != expected {
                return Err("Cell state contract mismatch".into());
            }
            let choices = raw["implementations"].as_array().ok_or("missing Cell implementations")?;
            let contracts = expected.as_array().unwrap();
            if choices.len() != contracts.len() { return Err("Cell implementation count".into()); }
            let mut inherited = Vec::new();
            for (choice, contract) in choices.iter().zip(contracts) {
                let carry = match choice.as_str() {
                    Some("materialize") => false,
                    Some("inherit") if contract["can_inherit"] == true => true,
                    _ => return Err("unproved Cell inheritance".into()),
                };
                inherited.push(carry);
            }
            s.track_slots=inherited.iter().enumerate().any(|(i,&enabled)|enabled && s.switch.layout(i).is_some());
            s.inherited = Some(inherited);
        }
        if let Some(completion)=raw.get("completion") {
            let mut contracts = s.completion_contracts(p);
            // Early v1 exports predate the compile-only transition census.
            // Executable switch and source/port proofs are still checked above.
            if completion["contracts"].get("transitions").is_none() {
                contracts.as_object_mut().unwrap().remove("transitions");
            }
            if completion["schema"]!="eggfuse-ripsat-completion/v1"
                || completion["contracts"]!=contracts {
                return Err("invalid ripsat completion structures".into());
            }
            if let Some(entries) = completion.get("entry_dispatch") {
                if *entries != s.completion_entries(p) {
                    return Err("invalid completion entry dispatch".into());
                }
            }
        }
        Ok(s)
    }
    /// Reconstruct executable state contracts from the validated Cell program.
    /// This intentionally promises no saturation under new external inputs.
    pub fn state_contracts(&self, p: &Program) -> J {
        self.switch.state_contracts(p, |u| self.units[u].last())
    }
    /// Compile-only routing information. Program IDs are existing switch PCs,
    /// not a second completion graph or an instance-side binding registry.
    pub fn completion_entries(&self, p: &Program) -> J {
        let switch = self.switch.artifact();
        let mut entries = BTreeMap::<Entry, Vec<usize>>::new();
        if let Some(states) = switch["completion_states"].as_array() {
            for (pc, program) in states.iter().enumerate().filter(|(_, p)| !p.is_null()) {
                let unit = self.switch.active(pc);
                let entry = self.units[unit].last();
                debug_assert_eq!(program["rule"].as_u64(), Some(entry.0 as u64));
                entries.entry(entry).or_default().push(pc);
            }
        }
        let programs = entries.values().map(Vec::len).sum::<usize>();
        let rows = entries.into_iter().map(|((rule, pivot), states)| {
            let leaf = self.leaves[&(rule, pivot)];
            json!({"rule":rule,"template":p.rules[rule].template,"pivot":pivot,"leaf":leaf,"states":states})
        }).collect::<Vec<_>>();
        json!({"schema":"eggfuse-completion-entry-dispatch/v1",
            "switch_sha256":crate::checksum::artifact_digest(&p.artifact["iterative_bake"]["rhs_handoffs"]),
            "entries":rows,"programs":programs,
            "default":"ordinary","program_index":"rhs_handoffs.completion_states[state]",
            "activation":"after-successful-match-before-rhs",
            "publication":"original-source-run",
            "dynamic_checks":["execution-mode","publication-layout","actual-result-projection","receipt-visibility"]})
    }
    /// Finite constructor structures and exact prefix inclusion maps. This is
    /// reconstructed during loading; runtime instances do not retain the graphs.
    pub fn completion_contracts(&self, p: &Program) -> J {
        use crate::cell_completion::{normalize, extension};
        let mut shapes = BTreeMap::new();
        let mut structures = vec![];
        let mut implementations = vec![];
        let normalized=self.units.iter().map(|u|normalize(p,&u.path)).collect::<Vec<_>>();
        for (unit,u) in self.units.iter().enumerate() {
            let Some(n) = &normalized[unit] else {
                // Retain exact ordered source contracts for unsupported
                // normalization. They may use independently checked result
                // inclusion, but do not acquire structural equivalence merely
                // because their final constructor values happen to agree.
                let class=structures.len();
                structures.push(json!({"ordered_source":u.path,"normalization":"opaque-source-contract"}));
                implementations.push(json!({"unit":unit,"class":class,"source_path":u.path,
                    "normalization":"opaque-source-contract","established":"successful-rhs",
                    "visible":"original-run-after-completion"}));
                continue;
            };
            let next=structures.len();
            let class=*shapes.entry(n.structure.clone()).or_insert_with(|| {
                structures.push(serde_json::to_value(&n.structure).unwrap()); next
            });
            let prefix = if u.path.len()>1 { normalize(p,&u.path[..u.path.len()-1]) } else { None };
            let transition = prefix.as_ref().and_then(|before| extension(before,n));
            implementations.push(json!({"unit":unit,"class":class,"ports":n.ports,
                "source_path":u.path,"extension":transition,
                "established":"successful-rhs","visible":"original-run-after-completion"}));
        }
        let transitions=self.jumps.iter().map(|(join,&target)| {
            let unit=&self.units[join.left];
            let incidence=normalized[join.left].as_ref().and_then(|n|
                n.ports.iter().find(|(stage,site,_)|*stage==unit.path.len()-1 && *site==crate::cell::Site::Effect(join.output)));
            let signature=if let Some((_,_,ports))=incidence {
                let table=crate::cell::Definition::new(p,unit.last().0).unwrap()
                    .relation(crate::cell::Site::Effect(join.output)).unwrap().table;
                json!({"table":table,"ports":ports,"entry":self.units[join.right].path})
            } else {json!({"ordered_source":unit.path,"output":join.output,"entry":self.units[join.right].path})};
            json!({"from":join.left,"to":target,"application":signature})
        }).collect::<Vec<_>>();
        json!({"schema":"eggfuse-constructor-completion-contracts/v1",
            "recipe":p.artifact["recipe"]["sha256"],"structures":structures,"implementations":implementations,
            "transitions":transitions,
            "scope":"finite positive constructor closure; not whole-program saturation"})
    }
    pub fn emit_handoffs(p: &Program, plan: &mut J) -> Result<()> {
        Self::emit_switch(p, plan, true)
    }
    pub fn emit_switch(p: &Program, plan: &mut J, reuse: bool) -> Result<()> {
        Self::emit_policy(p, plan, reuse, false, false, false, false, None)
    }
    pub fn emit_congruence_handoffs(p: &Program, plan: &mut J) -> Result<()> {
        Self::emit_policy(p, plan, true, true, false, false, false, None)
    }
    pub fn emit_query_handoffs(p: &Program, plan: &mut J) -> Result<()> {
        Self::emit_policy(p, plan, true, true, true, false, false, None)
    }
    pub fn emit_ripsat_handoffs(p: &Program, plan: &mut J) -> Result<()> {
        Self::emit_policy(p, plan, true, true, true, true, true, None)
    }
    /// Lower exactly this catalog without silently admitting equivalent routes.
    pub fn emit_existing_ripsat_handoffs(p: &Program, plan: &mut J) -> Result<()> {
        Self::emit_policy(p, plan, true, true, true, true, false, None)
    }
    /// Inferred routes must connect implementations seen in completed runtime history.
    pub fn emit_observed_ripsat_handoffs(p: &Program, plan: &mut J, observed: &ObservedCompletions) -> Result<()> {
        Self::emit_policy(p, plan, true, true, true, true, true, Some(observed))
    }
    /// Transfer a known local application to another implementation of the
    /// exact same completed Cell. Positions are matched by constructor
    /// incidence, not rule IDs or physical addresses. This is one bounded
    /// graph expansion per Bake call, not enumeration of complete histories.
    fn extend_completion_entries(p:&Program,plan:&mut J,observed:Option<&ObservedCompletions>) -> Result<()> {
        use crate::cell::{Definition,Site};
        let catalog=Self::parse(p,plan)?;
        if observed.is_some_and(|seen| seen.units.iter().any(|&id|id>=catalog.units.len())
            || seen.joins.iter().any(|j|j.left>=catalog.units.len() || j.right>=catalog.units.len())) {
            return Err("completed history references a different Cell catalog".into());
        }
        let room=catalog.limits.total.saturating_sub(catalog.units.len())
            .min(catalog.limits.per_round);
        let seeds = observed.map(|seen| seen.joins.iter().copied().collect::<Vec<_>>())
            .unwrap_or_else(||catalog.jumps.keys().copied().collect());
        if room==0 || seeds.is_empty() {
            plan["completion_search"] = json!({"scope":"compile-only; not runtime savings",
                "indexed_outputs":0,"route_probes":0,"candidate_visits":0,"proof_checks":0,"admitted":0});
            return Ok(());
        }
        let normalized=catalog.units.iter().enumerate().map(|(id,u)| {
            if observed.is_some_and(|seen| !seen.units.contains(&id)) { return None; }
            crate::cell_completion::normalize(p,&u.path)
        }).collect::<Vec<_>>();
        // Build the final-stage output incidence index once. Borrow canonical
        // structures/ports; no graph clones or runtime producer subscriptions.
        // Reverse operation order preserves the old last-output preference.
        let mut outputs = BTreeMap::new();
        let mut indexed_outputs = 0;
        for (left, alternative) in normalized.iter().enumerate() {
            let Some(alternative) = alternative else { continue };
            if observed.is_some_and(|seen| !seen.units.contains(&left)) { continue; }
            let unit = &catalog.units[left];
            let cell = Definition::new(p, unit.last().0)?;
            let mut seen = BTreeSet::new();
            for (stage, site, columns) in alternative.ports.iter().rev() {
                let Site::Effect(op) = *site else { continue };
                if *stage != unit.path.len()-1 { continue; }
                let Some(relation) = cell.relation(*site) else { continue };
                if !seen.insert((relation.table, columns)) { continue; }
                outputs.entry((&alternative.structure, relation.table, columns))
                    .or_insert_with(Vec::new).push((left, op));
                indexed_outputs += 1;
            }
        }
        let (mut route_probes, mut candidate_visits, mut proof_checks) = (0, 0, 0);
        let mut paths=catalog.units.iter().map(|u|u.path.to_vec()).collect::<BTreeSet<_>>();
        let mut extensions=vec![];
        let mut additions=vec![];
        'joins: for join in seeds {
            if observed.is_some_and(|seen| !seen.units.contains(&join.left)) { continue; }
            let Some(source)=&normalized[join.left] else{continue};
            let original=&catalog.units[join.left];
            let stage=original.path.len()-1;
            let Some((_,_,columns))=source.ports.iter().find(|(s,site,_)|*s==stage && *site==Site::Effect(join.output)) else{continue};
            let table=Definition::new(p,original.last().0)?.relation(Site::Effect(join.output)).ok_or("missing completion output")?.table;
            route_probes += 1;
            let Some(candidates) = outputs.get(&(&source.structure, table, columns)) else { continue };
            for &(left, output) in candidates {
                candidate_visits += 1;
                let candidate=Join{left,output,right:join.right};
                if catalog.jumps.contains_key(&candidate) {continue;}
                let Some(combined)=catalog.combine(p,candidate) else{continue};
                if paths.contains(combined.path.as_ref()) {continue;}
                proof_checks += 1;
                let proof=crate::result_handoff::terminal(p,&combined.path,true,true);
                if !proof.complete || proof.reuse.is_empty() {continue;}
                paths.insert(combined.path.to_vec());
                additions.push(json!(candidate));
                extensions.push(json!({"from":join,"to":candidate,
                    "structure":crate::checksum::artifact_digest(&serde_json::to_value(&source.structure).unwrap()),
                    "output_ports":columns,"proof":"exact normalized structure and output incidence",
                    "origin":if observed.is_some() {"completed-runtime-history"} else {"checked-catalog"},
                    "observed_application":observed.is_some_and(|seen|seen.joins.contains(&candidate)),
                    "new_observation":false}));
                if additions.len()==room {break 'joins;}
            }
        }
        plan["completion_search"] = json!({"scope":"compile-only; not runtime savings",
            "indexed_outputs":indexed_outputs,"route_probes":route_probes,
            "candidate_visits":candidate_visits,"proof_checks":proof_checks,"admitted":additions.len()});
        if !additions.is_empty() {
            plan["joins"].as_array_mut().ok_or("missing completion joins")?.extend(additions);
            let object=plan.as_object_mut().unwrap();
            object.entry("completion_extensions").or_insert_with(||json!([]))
                .as_array_mut().ok_or("invalid completion provenance")?.extend(extensions);
        }
        Ok(())
    }
    fn emit_policy(
        p: &Program,
        plan: &mut J,
        reuse: bool,
        congruence: bool,
        query_ports: bool,
        completion: bool,
        expand: bool,
        observed: Option<&ObservedCompletions>,
    ) -> Result<()> {
        plan.as_object_mut().ok_or("missing iterative catalog")?.remove("state_plan");
        plan.as_object_mut().unwrap().remove("completion");
        plan.as_object_mut()
            .ok_or("missing iterative catalog")?
            .remove("rhs_handoffs");
        if expand {Self::extend_completion_entries(p,plan,observed)?;}
        else if !completion {
            plan.as_object_mut().unwrap().remove("completion_extensions");
            plan.as_object_mut().unwrap().remove("completion_search");
        }
        let cat = Self::parse(p, plan)?;
        plan["rhs_handoffs"] = crate::result_handoff::Switch::build(
            p,
            cat.units.iter().map(|u| u.path.as_ref()),
            &cat.leaves,
            reuse,
            congruence,
            query_ports,
            completion,
        )
        .artifact();
        Ok(())
    }
    pub(crate) fn tracks_slots(&self) -> bool { self.track_slots }
    pub(crate) fn direct_completion(&self,s:&State) -> Option<&Rc<crate::cell::CompletedPlan>> {
        self.switch.direct(s.pc)
    }
    pub(crate) fn completion_enabled(&self) -> bool { self.switch.completion_enabled() }
    pub(crate) fn exports(&self, rid: usize) -> &[crate::cell::Site] {
        self.switch.exports(rid)
    }
    pub(crate) fn result_port(&self, rid: usize, site: crate::cell::Site) -> Option<crate::cell::ResultPort> {
        self.exports(rid).binary_search(&site).ok().map(|slot| crate::cell::ResultPort::new(rid, slot))
    }
    pub(crate) fn capture(&self, s: &State) -> (&[crate::cell::Capture], usize, bool, Option<&Rc<crate::cell::SlotLayout>>) {
        let (sources, depth, layout) = self.switch.capture(s.pc);
        (sources, depth, self.inherited.as_ref().is_none_or(|v| v.get(s.pc).copied().unwrap_or(false)),
            if self.track_slots { layout } else { None })
    }
    /// A fully executed rule seeds its producer node, or a unique legacy leaf.
    /// Keep this restricted to v2 receipts a compiled continuation demands.
    /// Training also observes unspecialized roots, so their first continuation
    /// can enter the candidate set before any catalog demands those receipts.
    pub(crate) fn root_state(&self, rule: usize, run: usize, collect_pairs: bool) -> Option<State> {
        if !self.switch.congruence {
            return None;
        }
        let pc = self.switch.unique_root(rule, !collect_pairs)?;
        let unit = self.switch.active(pc);
        Some(State {
            pc,
            active: Some(unit),
            stack: if collect_pairs {
                vec![Segment { unit, incoming: 0 }]
            } else {
                vec![]
            },
            last_run: run,
            collect_pairs,
            ..Default::default()
        })
    }
    pub(crate) fn program(&self, s: &State) -> &[crate::result_handoff::Reuse] {
        self.switch
            .program(s.pc)
            .map_or(&[], |t| t.reuse.as_slice())
    }
    pub(crate) fn closed(&self, s: &State) -> bool {
        self.switch.program(s.pc).is_some_and(|p| p.complete)
    }
    pub(crate) fn query_receipt(
        &self,
        s: &State,
        atom: usize,
    ) -> Option<&crate::result_handoff::QueryReuse> {
        if !self.switch.query_ports {
            return None;
        }
        self.switch
            .program(s.pc)?
            .queries
            .iter()
            .find(|r| r.atom == atom)
    }
    fn combine(&self, p: &Program, j: Join) -> Option<Unit> {
        let (l, r) = (self.units.get(j.left)?, self.units.get(j.right)?);
        let size = l.path.len().checked_add(r.path.len())?;
        if size > self.limits.depth.min(self.limits.nodes) {
            return None;
        }
        let table = match p.templates[p.rules[l.last().0].template].ops.get(j.output)? {
            Op::Let(_, Call::Table(t), _) | Op::Set(t, _, _) => *t,
            _ => return None,
        };
        let pivot = r.first().1?;
        if !matches!(p.rules[r.first().0].query[pivot].call,Call::Table(t) if t==table) {
            return None;
        }
        let mut path = l.path.to_vec();
        let mut tail = r.path.to_vec();
        tail[0].0 = Some(j.output);
        path.extend(tail);
        Some(Unit {
            path: path.into_boxed_slice(),
        })
    }
    pub(crate) fn enabled(&self) -> bool {
        !self.units.is_empty()
    }
    // Executed only on an originally scheduled and checked anchor. Reductions
    // consume adjacent, non-overlapping segments of this particular cursor.
    // A reset transfers the previous history to the current query. It may use
    // the producer's existing witnesses, but cannot carry that history into a
    // future consumer that the catalog did not admit.
    pub(crate) fn dispatch(
        &self,
        state: &mut State,
        rule: usize,
        pivot: usize,
        complete: bool,
        witness: crate::graph::Dependency,
    ) -> (bool, crate::result_handoff::History) {
        if self.switch.enabled() {
            let Some(leaf) = self.switch.leaf(rule, pivot) else {
                return (false, std::mem::take(state).history);
            };
            state.pc = self.switch.advance(state.pc, state.output, leaf);
            let unit = self.switch.active(state.pc);
            state.active = Some(unit);
            state.direct = complete;
            state.complete = complete;
            state.pending = None;
            state.capped = false;
            state.witness = Some(witness);
            if state.collect_pairs {
                let size = self.units[unit].path.len();
                let mut overlap = size - 1;
                let mut incoming = state.output;
                while overlap != 0 {
                    let Some(segment) = state.stack.pop() else {
                        break;
                    };
                    let span = self.units[segment.unit].path.len();
                    incoming = segment.incoming;
                    if span > overlap {
                        state.stack.clear();
                        break;
                    }
                    overlap -= span;
                }
                if let Some(left) = state.stack.last() {
                    let j = Join {
                        left: left.unit,
                        output: incoming,
                        right: unit,
                    };
                    if self.units[left.unit].path.len() + size
                        <= self.limits.depth.min(self.limits.nodes)
                    {
                        state.pending = Some(j);
                    } else {
                        state.capped = true;
                    }
                }
                state.stack.push(Segment { unit, incoming });
                let mut expanded = 0;
                let keep = state
                    .stack
                    .iter()
                    .rev()
                    .take_while(|s| {
                        expanded += self.units[s.unit].path.len();
                        expanded <= self.limits.depth.min(self.limits.nodes)
                    })
                    .count();
                state.stack.drain(..state.stack.len() - keep);
            }
            return (self.units[unit].terminal(), Default::default());
        }
        let Some(&id) = self.leaves.get(&(rule, Some(pivot))) else {
            return (false, std::mem::take(state).history);
        };
        let mut right = Segment {
            unit: id,
            incoming: state.output,
        };
        state.pending = None;
        state.capped = false;
        state.witness = Some(witness);
        state.complete = complete;
        while let Some(left) = state.stack.last() {
            let join = Join {
                left: left.unit,
                output: right.incoming,
                right: right.unit,
            };
            if let Some(&unit) = self.jumps.get(&join) {
                right = Segment {
                    unit,
                    incoming: left.incoming,
                };
                state.stack.pop();
            } else {
                if self.units[left.unit].path.len() + self.units[right.unit].path.len()
                    <= self.limits.depth.min(self.limits.nodes)
                {
                    state.pending = Some(join);
                } else {
                    state.capped = true;
                }
                break;
            }
        }
        state.direct = complete && right.unit >= self.leaves.len();
        state.stack.push(right);
        // A future reduction cannot reach past D primitive applications.
        let mut size = 0;
        let keep = state
            .stack
            .iter()
            .rev()
            .take_while(|s| {
                size += self.units[s.unit].path.len();
                size <= self.limits.depth.min(self.limits.nodes)
            })
            .count();
        state.stack.drain(..state.stack.len() - keep);
        (self.units[right.unit].terminal(), Default::default())
    }
    pub fn entries(&self) -> Vec<J> {
        self.units
            .iter()
            .enumerate()
            .map(|(id, u)| {
                let mut entry =
                    json!({"id":id,"expanded":u.path,"depth":u.path.len(),"nodes":u.path.len()});
                if self.switch.enabled() {
                    entry["terminal"] = json!(self.switch.program(self.switch.replay(&u.path)));
                }
                entry
            })
            .collect()
    }
    pub fn select(&self, p: &Program, profile: &Training) -> Vec<(Join, Evidence)> {
        // Offline selection borrows existing immutable keys. Neither copies
        // of their contents nor a persistent runtime index are necessary.
        let existing:BTreeSet<_>=self.units.iter().map(|u|u.path.as_ref()).collect();
        let mut choices = vec![];
        let mut bridge_paths = BTreeMap::new();
        for (&join, e) in &profile.pairs {
            if e.visits < self.limits.support {
                continue;
            }
            let Some(u) = self.combine(p, join) else {
                continue;
            };
            if existing.contains(u.path.as_ref()) {
                continue;
            }
            let mut e = e.clone();
            if self.switch.enabled() {
                let old = self.switch.program(self.switch.replay(&u.path)).unwrap();
                let proof = crate::result_handoff::terminal(
                    p,
                    &u.path,
                    self.switch.congruence,
                    self.switch.query_ports,
                );
                let additional = proof
                    .reuse
                    .iter()
                    .filter(|r| !old.reuse.iter().any(|s| s.op == r.op))
                    .count()
                    + proof
                        .queries
                        .iter()
                        .filter(|r| !old.queries.iter().any(|s| s.atom == r.atom))
                        .count();
                e.predicted_key_reads = e.visits.saturating_mul(additional as u64);
            }
            // A + B can be useful even when B itself has nothing to reuse.
            // Separate A+B and B+C observations do not establish A+B+C.
            // Require that complete path on one actual cursor ancestry before
            // asking whether its typed operations expose a donor in A.
            // This is a ranking estimate;
            // the next round must witness the joined AB actually followed by C.
            if self.switch.enabled() && e.predicted_key_reads == 0 {
                for (next, w) in profile.pairs.range(
                    Join {
                        left: join.right,
                        output: 0,
                        right: 0,
                    }..,
                ) {
                    if next.left != join.right {
                        break;
                    }
                    if w.visits < self.limits.support {
                        continue;
                    }
                    let tail = &self.units[next.right];
                    if u.path.len() + tail.path.len() > self.limits.depth.min(self.limits.nodes) {
                        continue;
                    }
                    let Some(_) = self.combine(p, *next) else {
                        continue;
                    };
                    let mut path = u.path.to_vec();
                    let mut suffix = tail.path.to_vec();
                    suffix[0].0 = Some(next.output);
                    path.extend(suffix);
                    let support = *bridge_paths.entry(path.clone())
                        .or_insert_with(|| profile.completed_path_support(&path));
                    if support < self.limits.support.max(1) { continue; }
                    let old = self.switch.program(self.switch.replay(&path)).unwrap();
                    let start_of_b = self.units[join.left].path.len();
                    let proof = crate::result_handoff::terminal(
                        p,
                        &path,
                        self.switch.congruence,
                        self.switch.query_ports,
                    );
                    if proof.reuse.iter().any(|r| {
                        path.len() - 1 - r.back < start_of_b
                            && !old.reuse.iter().any(|x| x.op == r.op)
                    }) || proof.queries.iter().any(|r| {
                        path.len() - 1 - r.back < start_of_b
                            && !old.queries.iter().any(|x| x.atom == r.atom)
                    }) {
                        e.bridge_support = e.bridge_support.max(support);
                    }
                }
            }
            if e.avoidable_origin_slots != 0 || e.predicted_key_reads != 0 || e.bridge_support != 0
            {
                choices.push((join, e, u.path));
            }
        }
        choices.sort_by_key(|(j, e, _)| {
            (
                std::cmp::Reverse(e.predicted_key_reads),
                std::cmp::Reverse(e.bridge_support),
                std::cmp::Reverse(e.avoidable_origin_slots),
                std::cmp::Reverse(e.visits),
                *j,
            )
        });
        let n = self
            .limits
            .per_round
            .min(self.limits.total.saturating_sub(self.units.len()));
        let mut paths = BTreeSet::new();
        choices
            .into_iter()
            .filter_map(|(j, e, path)| paths.insert(path).then_some((j, e)))
            .take(n)
            .collect()
    }
}
#[derive(Clone, Debug, Default, Serialize)]
pub struct Evidence {
    pub visits: u64,
    pub predicted_key_reads: u64,
    pub bridge_support: u64,
    pub avoidable_origin_slots: u64,
    pub producer_run: usize,
    pub consumer_run: usize,
    pub witness: Option<crate::graph::Dependency>,
    width: u64,
}
/// Compile-time recognition seeds derived from completed trace links.
#[derive(Default)]
pub struct ObservedCompletions {
    pub units: BTreeSet<Id>,
    pub joins: BTreeSet<Join>,
}
/// A successful logical Cell execution, not a physical constructor owner.
/// Parent is an earlier execution on this cursor, including across Runs.
#[derive(Clone, Serialize)]
struct TraceEvent {
    parent: Option<usize>,
    unit: Id,
    entry: Entry,
    output: usize,
    run: usize,
    producer_run: usize,
    witness: Option<crate::graph::Dependency>,
    truncated_parent: bool,
}
#[derive(Default)]
pub struct Training {
    trace: Vec<TraceEvent>,
    trace_dropped: u64,
    pub(crate) collect_pairs: bool,
    pairs: BTreeMap<Join, Evidence>,
    hits: BTreeMap<Id, u64>,
    evictions: u64,
    capped_events: u64,
    pub(crate) run: usize,
    pub direct_origins: u64,
    pub saved_key_slots: u64,
    pub(crate) seal_moves: u64,
}
impl Training {
    /// Count completed paths on actual cursor ancestry, never by joining
    /// marginal pair frequencies. Compile-time ranking only; missing history
    /// cannot establish support and does not invalidate direct pair evidence.
    fn completed_path_support(&self, path: &[(Option<usize>, Entry)]) -> u64 {
        if path.is_empty() { return 0; }
        self.trace.iter().enumerate().filter(|(id, _)| {
            let mut cursor = *id;
            for (offset, &(output, entry)) in path.iter().enumerate().rev() {
                let event = &self.trace[cursor];
                if event.entry != entry { return false; }
                if offset == 0 { return true; }
                if output != Some(event.output) { return false; }
                let Some(parent) = event.parent else { return false; };
                if self.trace[parent].run >= event.run { return false; }
                cursor = parent;
            }
            false
        }).count() as u64
    }
    pub(crate) fn applied(&mut self, c: &Catalog, s: &mut State, inputs: usize) {
        let parent_run = std::mem::replace(&mut s.last_run, self.run);
        self.capped_events += u64::from(s.capped);
        let Some(id) = s.active.or_else(|| s.stack.last().map(|x| x.unit)) else {
            return;
        };
        *self.hits.entry(id).or_default() += 1;
        if s.direct {
            self.direct_origins += 1;
            self.saved_key_slots += inputs as u64;
        }
        // In training only, retain a bounded witness window. With a multi-step
        // right operand its *first* Run identifies the sampled join boundary.
        self.trace_completed(c, s, id, parent_run);
        let Some(j) = s.pending else { return };
        // Once a right operand already takes the direct origin, extending its
        // left boundary earns no second credit for the same operation.
        if parent_run == 0 || parent_run >= self.run {
            return;
        }
        let sample = if s.collect_pairs && s.active.is_some() {
            let window = s.samples.as_deref().unwrap();
            let Some(i) = window.len().checked_sub(c.units[j.right].path.len()) else {
                return;
            };
            window[i]
        } else {
            (parent_run, self.run, s.witness, None)
        };
        let saves_key = s.complete && !s.fused(c) && !c.switch.enabled();
        if self.pairs.len() == c.limits.candidates && !self.pairs.contains_key(&j) {
            self.pairs.retain(|_, e| {
                e.visits -= 1;
                e.avoidable_origin_slots = e.avoidable_origin_slots.saturating_sub(e.width);
                e.visits > 0
            });
            self.evictions += 1;
            return;
        }
        let e = self.pairs.entry(j).or_insert(Evidence {
            producer_run: sample.0,
            consumer_run: sample.1,
            witness: sample.2,
            width: inputs as u64,
            ..Default::default()
        });
        e.visits += 1;
        // Keep one recent real application per retained shape, rather than
        // permanently pinning its first occurrence before raw trace cutoff.
        e.producer_run = sample.0;
        e.consumer_run = sample.1;
        e.witness = sample.2;
        if saves_key { e.avoidable_origin_slots += inputs as u64; }
    }
    pub(crate) fn trace_root(&mut self, c: &Catalog, s: &mut State) {
        if let Some(id) = s.active { self.trace_completed(c, s, id, 0); }
    }
    fn trace_completed(&mut self, c: &Catalog, s: &mut State, id: Id, parent_run: usize) {
        if s.collect_pairs {
            let parent = s.samples.as_deref().and_then(|w| w.last()).and_then(|s| s.3);
            let trace = if self.trace.len() < c.limits.candidates.saturating_mul(c.limits.depth.min(c.limits.nodes)) {
                let index = self.trace.len();
                self.trace.push(TraceEvent { parent, unit:id, entry:c.units[id].last(),
                    output:s.output, run:self.run, producer_run:parent_run, witness:s.witness,
                    truncated_parent:parent.is_none() && parent_run!=0 });
                Some(index)
            } else { self.trace_dropped += 1; None };
            let window = Rc::make_mut(s.samples.get_or_insert_with(Default::default));
            let limit = c.limits.depth.min(c.limits.nodes);
            if window.len() == limit {
                window.remove(0);
            }
            window.push((parent_run, self.run, s.witness, trace));
        }
    }
    pub fn completion_observations(&self, catalog: &Catalog) -> ObservedCompletions {
        let mut joins = BTreeSet::new();
        for event in &self.trace {
            let Some(parent) = event.parent.map(|i| &self.trace[i]) else { continue };
            if parent.run >= event.run { continue; }
            let Some(&right) = catalog.leaves.get(&event.entry) else { continue };
            joins.insert(Join {left:parent.unit, output:event.output, right});
        }
        let mut units = self.trace.iter().map(|e|e.unit).collect::<BTreeSet<_>>();
        // Existing bounded pair samples survive raw-event truncation. They are
        // successful applications, not synthetic event ancestry.
        for (join, evidence) in &self.pairs {
            if evidence.visits == 0 { continue; }
            units.extend([join.left,join.right]);
            joins.insert(*join);
        }
        ObservedCompletions { units, joins }
    }
    /// Materialize compile-time history from completed cursor executions only.
    /// Paths are bounded suffixes; the event links retain their actual ancestry.
    pub fn completion_history(&self, p: &Program) -> J {
        fn intern(path: &[(Option<usize>, Entry)], catalog: &mut Catalog,
            units: &mut BTreeMap<Vec<(Option<usize>, Entry)>,usize>) -> usize {
            let next = catalog.units.len();
            *units.entry(path.to_vec()).or_insert_with(|| {
                catalog.units.push(Unit {path:path.into()}); next
            })
        }
        let mut catalog = Catalog::default();
        let mut units = BTreeMap::new();
        let mut event_units: Vec<usize> = Vec::new();
        let limit = p.iterative.limits.depth.min(p.iterative.limits.nodes);
        for event in &self.trace {
            let mut path = event.parent.map(|parent| {
                catalog.units[event_units[parent]].path.to_vec()
            }).unwrap_or_default();
            path.push(((!path.is_empty()).then_some(event.output), event.entry));
            if path.len() > limit { path.remove(0); path[0].0 = None; }
            let unit = intern(&path, &mut catalog, &mut units);
            event_units.push(unit);
            // A native transition references only the exact observed prefix.
            if let Some(parent) = event.parent {
                let left = event_units[parent];
                if catalog.units[left].path.len()+1 == path.len() {
                    let leaf = vec![(None,event.entry)];
                    let right = intern(&leaf, &mut catalog, &mut units);
                    catalog.jumps.insert(Join {left,output:event.output,right}, unit);
                }
            }
        }
        let mut applications = Vec::new();
        for (join, evidence) in &self.pairs {
            if evidence.visits == 0 { continue; }
            let Some(combined) = p.iterative.combine(p,*join) else { continue };
            let left = intern(&p.iterative.units[join.left].path, &mut catalog, &mut units);
            let right = intern(&p.iterative.units[join.right].path, &mut catalog, &mut units);
            let target = intern(&combined.path, &mut catalog, &mut units);
            catalog.jumps.insert(Join {left,output:join.output,right},target);
            applications.push(json!({"join":join,"from":left,"consumer":right,"to":target,
                "retained_support":evidence.visits,"producer_run":evidence.producer_run,
                "consumer_run":evidence.consumer_run,"witness":evidence.witness,
                "origin":"bounded-completed-pair-sample","sample_policy":"latest-retained-application"}));
        }
        json!({"schema":"eggfuse-cell-runtime-history/v1",
            "sampled_applications":applications,"pair_counter_prunes":self.evictions,
            "program_sha256":p.artifact["sha256"],"events":self.trace,
            "event_units":event_units,"dropped_events":self.trace_dropped,
            "contracts":catalog.completion_contracts(p),
            "scope":"bounded completed cursor lineage; not all matches or committed mutations"})
    }
    pub fn report(&self) -> J {
        json!({"applied_units":self.hits,"trace_events":self.trace.len(),"trace_dropped":self.trace_dropped,"candidate_shapes":self.pairs.len(),"counter_prunes":self.evictions,"oversized_applied_pairs":self.capped_events,"direct_origins":self.direct_origins,"saved_origin_key_slots":self.saved_key_slots,"saved_answer_slot_copies":self.seal_moves})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::graph::Dependency;
    #[test]
    fn two_reduced_operands_can_join_without_repeating_the_prefix() {
        let mut c = Catalog::default();
        for i in 0..4 {
            c.leaves.insert((i, Some(0)), i);
            c.units.push(Unit {
                path: vec![(None, (i, Some(0)))].into_boxed_slice(),
            });
        }
        for (l, r) in [(0, 1), (2, 3), (4, 5)] {
            let mut path = c.units[l].path.to_vec();
            let mut right = c.units[r].path.to_vec();
            right[0].0 = Some(0);
            path.extend(right);
            let unit = Unit {
                path: path.into_boxed_slice(),
            };
            c.jumps.insert(
                Join {
                    left: l,
                    right: r,
                    output: 0,
                },
                c.units.len(),
            );
            c.units.push(unit);
        }
        let mut state = State::default();
        for i in 0..4 {
            assert!(c.dispatch(&mut state, i, 0, true, Dependency::Function(0)).0);
        }
        assert_eq!(state.stack.len(), 1);
        assert_eq!(state.stack[0].unit, 6);
        assert!(state.direct);
        let port = crate::cell::ResultPort::new(0, 0);
        state.history.capture(1, 0, &[crate::cell::Capture { site: crate::cell::Site::Effect(0), port }],
            |_| None, |_| Some(Dependency::Function(7)));
        let (selected, previous) = c.dispatch(&mut state, 99, 0, true, Dependency::Function(0));
        assert!(!selected);
        assert_eq!(previous.get(1, port), Some(Dependency::Function(7)));
        assert!(state.history.current().is_none());
        assert!(state.stack.is_empty() && !state.direct);
    }
    #[test]
    fn bridge_support_requires_one_completed_cross_stage_ancestry() {
        let event = |rule, parent, run| TraceEvent {
            parent, unit:rule, entry:(rule,Some(0)), output:0, run,
            producer_run:0, witness:None, truncated_parent:false,
        };
        let mut training = Training::default();
        // A->B and a separate B->C cannot establish A->B->C.
        training.trace = vec![event(0,None,1),event(1,Some(0),2),
            event(1,None,3),event(2,Some(2),4)];
        let path = [(None,(0,Some(0))),(Some(0),(1,Some(0))),(Some(0),(2,Some(0)))];
        assert_eq!(training.completed_path_support(&path),0);
        training.trace.push(event(2,Some(1),5));
        assert_eq!(training.completed_path_support(&path),1);
        training.trace.push(event(2,Some(1),6));
        assert_eq!(training.completed_path_support(&path),2);
        // Wrong output, missing parent and same-Run execution add no support.
        let mut wrong = event(2,Some(1),7); wrong.output=1;
        training.trace.extend([wrong,event(2,None,8),event(2,Some(1),2)]);
        assert_eq!(training.completed_path_support(&path),2);
    }

    #[test]
    fn completed_trace_keeps_fork_ancestry_and_reports_capacity_loss() {
        let mut c = Catalog::default();
        for rule in 0..3 {
            c.leaves.insert((rule,Some(0)),rule);
            c.units.push(Unit {path:vec![(None,(rule,Some(0)))].into_boxed_slice()});
        }
        let mut training = Training {run:1,..Default::default()};
        let mut source = State {active:Some(0),collect_pairs:true,..Default::default()};
        training.applied(&c,&mut source,1);
        let mut left = source.clone();
        left.active=Some(1); training.run=2; training.applied(&c,&mut left,1);
        source.active=Some(2); training.run=3; training.applied(&c,&mut source,1);
        assert_eq!(training.trace.len(),3);
        assert_eq!(training.trace[1].parent,Some(0));
        assert_eq!(training.trace[2].parent,Some(0));
        assert_eq!(training.trace[2].producer_run,1);
        assert_eq!(training.completion_observations(&c).joins, [
            Join {left:0,output:0,right:1}, Join {left:0,output:0,right:2}
        ].into_iter().collect());
        c.limits.candidates=1; c.limits.depth=2;
        let late = Join {left:2,output:0,right:1};
        source.active=Some(1); source.pending=Some(late);
        training.run=4; training.applied(&c,&mut source,1);
        assert_eq!(training.trace.len(),3);
        assert_eq!(training.trace_dropped,1);
        assert!(training.completion_observations(&c).joins.contains(&late),
            "successful pair evidence must survive a full raw-event archive");
        assert_eq!(training.pairs[&late].consumer_run,4);
        assert_eq!(source.samples.as_ref().unwrap().last().unwrap().3,None);
        let mut ordinary = State {active:Some(0),..Default::default()};
        training.applied(&c,&mut ordinary,1);
        assert!(ordinary.samples.is_none());
        assert_eq!(training.trace_dropped,1);
    }
    #[test]
    fn tail_counters_remain_bounded_and_credit_only_complete_entries() {
        let mut c = Catalog::default();
        c.limits.candidates = 1;
        c.leaves.insert((0, Some(0)), 0);
        let mut s = State {
            stack: vec![Segment {
                unit: 0,
                incoming: 0,
            }],
            last_run: 1,
            ..Default::default()
        };
        let mut training = Training {
            run: 2,
            ..Default::default()
        };
        s.pending = Some(Join {
            left: 0,
            output: 1,
            right: 0,
        });
        training.applied(&c, &mut s, 3);
        assert_eq!(
            training.pairs[&s.pending.unwrap()].avoidable_origin_slots,
            0
        );
        training.run = 3;
        s.complete = true;
        training.applied(&c, &mut s, 3);
        let e = &training.pairs[&s.pending.unwrap()];
        assert_eq!(
            (
                e.visits,
                e.avoidable_origin_slots,
                e.producer_run,
                e.consumer_run
            ),
            (2, 3, 2, 3)
        );
        s.pending = Some(Join {
            left: 0,
            output: 2,
            right: 0,
        });
        training.run = 4;
        training.applied(&c, &mut s, 5);
        assert_eq!(training.evictions, 1);
        assert_eq!(training.pairs.len(), 1);
        assert_eq!(
            training
                .pairs
                .values()
                .next()
                .unwrap()
                .avoidable_origin_slots,
            0
        );
    }
}
