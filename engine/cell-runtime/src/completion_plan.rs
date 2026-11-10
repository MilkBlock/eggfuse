//! Conservative compiler proof of completion dependencies. A source table's
//! congruence can union its result sort, which can change any table containing
//! that sort. Transitive reachability includes arbitrarily long repair chains.
//! Checked merge reads and constructor births are separate obligations.
use crate::program::{Arg, Call, Op, Program, Result};
use crate::value::Value;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
#[path = "completion_access.rs"]
mod access;
#[path = "completion_effects.rs"]
mod effects;

#[derive(Clone, Debug, Serialize)]
pub struct Scope {
    source: String,
    tables: std::rc::Rc<[usize]>,
    pub(crate) predecessors: crate::table_mask::Mask,
}
impl Scope {
    pub fn tables(&self) -> &[usize] {
        &self.tables
    }
}
#[derive(Clone, Debug, Serialize)]
pub struct Plan {
    source: String,
    #[serde(skip)]
    affects: Box<[std::rc::Rc<[u64]>]>,
    #[serde(skip)]
    waits: Box<[std::rc::Rc<[u64]>]>,
    /// Tables that completion may read, including merges reached by its effects.
    pub completion_reads: Box<[std::rc::Rc<[usize]>]>,
    pub merges: Vec<effects::Merge>,
    #[serde(skip)]
    global_effects: Vec<bool>,
    pub opaque_tables: Vec<usize>,
    /// Only pure constructor completion may cross source Run boundaries.
    /// Mutable merges can allocate nodes or have source-ordered effects.
    pub deferrable: Vec<bool>,
    pub rulesets: BTreeMap<String, Scope>,
    /// Mandatory source snapshot reads, before any RHS can run.
    pub query_demands: BTreeMap<String, std::rc::Rc<[usize]>>,
    /// Separate source reads, RHS accesses, and conservative union effects.
    pub rule_demands: Vec<access::Rule>,
}
fn eq_sorts(schema: &[serde_json::Value]) -> (BTreeSet<String>, bool) {
    let mut names = BTreeSet::new();
    let mut unknown = false;
    for sort in schema {
        match sort["kind"].as_str() {
            Some("eq") => match sort["name"].as_str() {
                Some(name) => {
                    names.insert(name.to_owned());
                }
                None => unknown = true,
            },
            Some("i64" | "f64" | "String" | "bool" | "Unit" | "structural_key") => (),
            Some("set") => {
                let (elements, opaque) = eq_sorts(std::slice::from_ref(&sort["element"]));
                names.extend(elements);
                unknown |= opaque;
            }
            _ => unknown = true,
        }
    }
    (names, unknown)
}
impl Plan {
    pub fn derive(p: &Program) -> Result<Self> {
        let source = p.artifact["sha256"]
            .as_str()
            .ok_or("completion source checksum")?
            .to_owned();
        let n = p.tables.len();
        let sorts = p
            .tables
            .iter()
            .map(|t| eq_sorts(&t.schema))
            .collect::<Vec<_>>();
        let merges = (0..n)
            .map(|t| effects::Merge::derive(p, t))
            .collect::<Vec<_>>();
        let opaque_tables = p
            .tables
            .iter()
            .enumerate()
            .filter_map(|(i, _)| (sorts[i].1 || merges[i].opaque).then_some(i))
            .collect::<Vec<_>>();
        let mut affects = vec![vec![0u64; n.div_ceil(64)]; n];
        for (i, t) in p.tables.iter().enumerate() {
            affects[i][i / 64] |= 1 << (i % 64);
            if opaque_tables.contains(&i) {
                fill_all_tables(&mut affects[i], n);
                continue;
            }
            if t.constructor
                && let Some(sort) = t.schema.last()
                && sort["kind"] == "eq"
            {
                let name = sort["name"].as_str().ok_or("constructor result sort")?;
                for (j, (names, unknown)) in sorts.iter().enumerate() {
                    if *unknown || names.contains(name) { affects[i][j / 64] |= 1 << (j % 64); }
                }
            }
            // An opaque merge's reads are a barrier only when that merge is
            // actually pending. Its mere presence must not connect unrelated
            // sorts; the runtime switches to ordered full completion then.
        }
        transitive(&mut affects);
        // Closing an existing constructor key can publish an equality. A merge
        // constructing a previously absent key only publishes that table's new
        // fact; its fresh result is not a union of existing classes. Add birth
        // writes after equality-task closure so they do not invent that union.
        let completion_reads = affects
            .iter()
            .map(|row| {
                let mut reads = BTreeSet::new();
                for (t, merge) in merges.iter().enumerate() {
                    if row[t / 64] & (1 << (t % 64)) != 0 {
                        reads.extend(merge.reads.iter().copied());
                    }
                }
                reads.into_iter().collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        {
            // A birth must not activate another merge in this same pass.
            // Snapshot only the current closed row and reuse that buffer.
            let mut task_effects=vec![0u64;n.div_ceil(64)];
            for row in &mut affects {
                task_effects.copy_from_slice(row);
                for (t, merge) in merges.iter().enumerate() {
                    if task_effects[t / 64] & (1 << (t % 64)) != 0 {
                        for &birth in &merge.births {
                            row[birth / 64] |= 1 << (birth % 64);
                        }
                    }
                }
            }
        }
        // A selected merge must retain the original ordering with every task
        // that can alter its reads. These edges constrain waiting; reading a
        // table does not itself mutate that table or enqueue its consumers.
        let mut read_dependencies = vec![vec![0u64; n.div_ceil(64)]; n];
        for (from, row) in affects.iter().enumerate() {
            read_dependencies[from][from / 64] |= 1 << (from % 64);
            for (to, reads) in completion_reads.iter().enumerate() {
                if reads.iter().any(|&r| row[r / 64] & (1 << (r % 64)) != 0) {
                    read_dependencies[from][to / 64] |= 1 << (to % 64);
                }
            }
        }
        transitive(&mut read_dependencies);
        let mut waits = vec![vec![0u64; n.div_ceil(64)]; n];
        for (from, dependencies) in read_dependencies.iter().enumerate() {
            for (to, effects) in affects.iter().enumerate() {
                if dependencies[to / 64] & (1 << (to % 64)) != 0 {
                    for (word, &bits) in waits[from].iter_mut().zip(effects) {
                        *word |= bits;
                    }
                }
            }
        }
        let global_effects=affects.iter().map(|row|
            row.iter().map(|word|word.count_ones() as usize).sum::<usize>()==n).collect();
        // Closure construction remains mutable. Only the final exact rows are
        // interned, sharing equal influence and wait masks across both matrices.
        let mut rows=BTreeSet::new();
        let affects=share_rows(affects,&mut rows);
        let waits=share_rows(waits,&mut rows);
        // One compile-local pool covers the same typed table obligations in
        // completion, per-rule accesses and scheduled scopes. Runtime owners
        // keep direct immutable slices; the interning index is discarded.
        let mut sets = BTreeSet::<std::rc::Rc<[usize]>>::new();
        let completion_reads = completion_reads.into_iter()
            .map(|list| share_tables(list, &mut sets)).collect::<Vec<_>>().into_boxed_slice();
        let mut plan = Self {
            source,
            global_effects,
            affects,
            waits,
            completion_reads,
            merges,
            opaque_tables,
            deferrable: p
                .tables
                .iter()
                .enumerate()
                .map(|(i, t)| t.constructor && t.virtual_fact && !sorts[i].1)
                .collect(),
            rulesets: BTreeMap::new(),
            query_demands: BTreeMap::new(),
            rule_demands: Vec::new(),
        };
        // If completion can reach an ordered mutable effect, retain its source
        // barrier. Deferring only the first constructor would hide that effect.
        for i in 0..n {
            plan.deferrable[i] &= (0..n).all(|j| {
                !plan.affects(i, j)
                    || (p.tables[j].constructor && p.tables[j].virtual_fact && !sorts[j].1)
            });
        }
        plan.rule_demands = (0..p.rules.len())
            .map(|rid| access::Rule::derive(p, &plan, rid, &sorts))
            .collect();
        // Identical conservative obligations share immutable storage across
        // rules and stages. Equality is exact, never inferred from a digest.
        for demand in &mut plan.rule_demands {
            for list in [&mut demand.query, &mut demand.rhs, &mut demand.accesses] {
                if let Some(shared) = sets.get(list.as_ref()) { *list = shared.clone(); }
                else { sets.insert(list.clone()); }
            }
        }
        for (name, rules) in &p.sets {
            let mut tables = BTreeSet::new();
            let mut queries = BTreeSet::new();
            for &rid in rules {
                let demand = &plan.rule_demands[rid];
                queries.extend(demand.query.iter().copied());
                tables.extend(demand.query.iter().chain(demand.rhs.iter()).copied());
                let template = &p.templates[p.rules[rid].template];
                let (reads, unknown) = eq_sorts(&template.sorts);
                for (t, (names, opaque)) in sorts.iter().enumerate() {
                    if unknown || *opaque || !reads.is_disjoint(names) {
                        tables.insert(t);
                    }
                }
            }
            let mut scope = plan.scope(&tables.into_iter().collect::<Vec<_>>())?;
            if let Some(shared) = sets.get(scope.tables.as_ref()) { scope.tables = shared.clone(); }
            else { sets.insert(scope.tables.clone()); }
            plan.rulesets.insert(name.clone(), scope);
            plan.query_demands.insert(name.clone(), share_tables(queries.into_iter().collect(), &mut sets));
        }
        Ok(plan)
    }
    /// Logical capacity census, excluding allocator rounding and temporary interning.
    pub fn matrix_storage(&self)->serde_json::Value {
        let mut seen=BTreeSet::new();
        let mut payload=0;
        for row in self.affects.iter().chain(self.waits.iter()) {
            if seen.insert(row.as_ptr() as usize) {payload+=std::mem::size_of_val(row.as_ref())+2*std::mem::size_of::<usize>();}
        }
        let count=self.affects.len()+self.waits.len();
        serde_json::json!({"rows":count,"unique_rows":seen.len(),
            "dense_payload_bytes":count*self.affects.len().div_ceil(64)*std::mem::size_of::<u64>(),
            "shared_payload_and_rc_bytes":payload,
            "directory_bytes":(self.affects.len()+self.waits.len())*std::mem::size_of::<std::rc::Rc<[u64]>>()})
    }
    pub fn demand_storage(&self) -> serde_json::Value {
        let mut seen=BTreeSet::new();
        let mut shared=0usize;
        let mut unshared=0usize;
        for demand in &self.rule_demands {
            for list in [&demand.query,&demand.rhs,&demand.accesses] {
                unshared += std::mem::size_of_val(list.as_ref());
                if seen.insert(list.as_ptr() as usize) {
                    shared += std::mem::size_of_val(list.as_ref())+2*std::mem::size_of::<usize>();
                }
            }
        }
        serde_json::json!({"lists":self.rule_demands.len()*3,"unique_lists":seen.len(),
            "unshared_payload_bytes":unshared,"shared_payload_and_rc_bytes":shared,
            "shared_handles_bytes":self.rule_demands.len()*3*std::mem::size_of::<std::rc::Rc<[usize]>>()})
    }
    /// Retained table-list storage across all shared obligation owners. This
    /// excludes container headers, allocator rounding and the temporary pool.
    pub fn table_list_storage(&self) -> serde_json::Value {
        let mut seen = BTreeSet::new();
        let mut shared = 0;
        let mut lists = 0;
        let mut values = 0;
        for list in self.rule_demands.iter().flat_map(|d| [&d.query, &d.rhs, &d.accesses])
            .chain(self.completion_reads.iter()).chain(self.query_demands.values())
            .chain(self.rulesets.values().map(|s| &s.tables)) {
            lists += 1;
            values += list.len();
            if seen.insert(list.as_ptr() as usize) {
                shared += std::mem::size_of_val(list.as_ref()) + 2*std::mem::size_of::<usize>();
            }
        }
        serde_json::json!({"lists":lists,"logical_values":values,"unique_lists":seen.len(),
            "shared_payload_and_rc_bytes":shared,
            "handles_bytes":lists*std::mem::size_of::<std::rc::Rc<[usize]>>()})
    }
    pub fn scope_mask_storage(&self) -> serde_json::Value {
        serde_json::json!({"scopes":self.rulesets.len(),
            "old_boolean_payload_bytes":self.rulesets.values().map(|s|s.predecessors.len()).sum::<usize>(),
            "packed_payload_bytes":self.rulesets.values().map(|s|s.predecessors.payload_bytes()).sum::<usize>(),
            "descriptor_bytes":self.rulesets.len()*std::mem::size_of::<crate::table_mask::Mask>()})
    }
    /// Compile once per template when the optional bound-effect path is enabled.
    /// Ordinary scoped execution does not allocate or retain this code.
    pub(crate) fn prepare_pure_rhs(&mut self, p: &Program) {
        let mut templates = BTreeMap::new();
        for (rid, demand) in self.rule_demands.iter_mut().enumerate() {
            let template = p.rules[rid].template;
            demand.pure = templates
                .entry(template)
                .or_insert_with(|| {
                    crate::cell::BoundRhs::derive(p, &p.templates[template]).map(std::rc::Rc::new)
                })
                .clone();
        }
    }
    pub fn scope(&self, tables: &[usize]) -> Result<Scope> {
        if tables.iter().any(|&t| t >= self.affects.len()) {
            return Err("completion table out of bounds".into());
        }
        Ok(Scope {
            source: self.source.clone(),
            tables: tables.into(),
            predecessors: self
                .waits
                .iter()
                .map(|row| tables.iter().any(|&t| row[t / 64] & (1 << (t % 64)) != 0))
                .collect(),
        })
    }
    pub(crate) fn validate(&self, scope: &Scope) -> Result<()> {
        if scope.source != self.source || scope.predecessors.len() != self.affects.len() {
            return Err("completion scope belongs to a different program".into());
        }
        Ok(())
    }
    pub fn affects(&self, from: usize, to: usize) -> bool {
        self.affects[from][to / 64] & (1 << (to % 64)) != 0
    }
    pub(crate) fn global_effects(&self, table: usize) -> bool {
        self.global_effects[table]
    }
    pub fn report(&self) -> serde_json::Value {
        let mut seen = BTreeSet::new();
        let pure = self
            .rule_demands
            .iter()
            .filter_map(|r| r.pure.as_ref())
            .filter(|p| seen.insert(std::rc::Rc::as_ptr(p)))
            .collect::<Vec<_>>();
        serde_json::json!({"tables":self.affects.len(), "opaque_tables":self.opaque_tables,
            "pure_rhs_templates":pure.len(),
            "pure_rhs_expressions":pure.iter().map(|p|p.values.len()).sum::<usize>(),
            "pure_rhs_effects":pure.iter().map(|p|p.effects.len()).sum::<usize>(),
            "pure_rhs_copies_elided":pure.iter().map(|p|p.copies_elided).sum::<usize>(),
            "dependency_edges":self.affects.iter().flat_map(|row|row.iter()).map(|word|word.count_ones() as usize).sum::<usize>(),
            "wait_edges":self.waits.iter().flat_map(|row|row.iter()).map(|word|word.count_ones() as usize).sum::<usize>(),
            "merge_read_edges":self.merges.iter().map(|m|m.reads.len()).sum::<usize>(),
            "merge_birth_edges":self.merges.iter().map(|m|m.births.len()).sum::<usize>(),
            "merges":self.merges.iter().enumerate().filter(|(_,m)|m.opaque||!m.reads.is_empty()).map(|(table,m)|serde_json::json!({"table":table,"reads":m.reads,"births":m.births,"opaque":m.opaque})).collect::<Vec<_>>(),
            "deferrable_tables":self.deferrable.iter().filter(|&&v|v).count(),
            "scope":"typed conservative completion dependencies; same-sort regions may be coarser than Cell wiring"})
    }
}

fn opaque_literal(a: &Arg) -> bool {
    matches!(a, Arg::Literal(Value::Eq(_) | Value::Set(_)))
}
fn fill_all_tables(row:&mut [u64], tables:usize) {
    row.fill(u64::MAX);
    // Keep padding zero: global-effect classification counts set bits.
    if tables % 64 != 0 {
        if let Some(last)=row.last_mut() { *last=(1u64<<(tables%64))-1; }
    }
}
fn transitive(rows: &mut [Vec<u64>]) {
    let mut via=vec![0;rows.first().map_or(0,Vec::len)];
    for k in 0..rows.len() {
        via.copy_from_slice(&rows[k]);
        for row in &mut *rows {
            if row[k / 64] & (1 << (k % 64)) != 0 {
                for (word, &other) in row.iter_mut().zip(&via) {
                    *word |= other;
                }
            }
        }
    }
}

fn share_tables(list: Vec<usize>, pool: &mut BTreeSet<std::rc::Rc<[usize]>>) -> std::rc::Rc<[usize]> {
    if let Some(shared) = pool.get(list.as_slice()) { return shared.clone(); }
    let shared: std::rc::Rc<[usize]> = list.into();
    pool.insert(shared.clone());
    shared
}

fn share_rows(rows:Vec<Vec<u64>>, pool:&mut BTreeSet<std::rc::Rc<[u64]>>)->Box<[std::rc::Rc<[u64]>]> {
    rows.into_iter().map(|row| {
        if let Some(existing)=pool.get(row.as_slice()) {return existing.clone()}
        let shared:std::rc::Rc<[u64]>=row.into();
        pool.insert(shared.clone());shared
    }).collect::<Vec<_>>().into_boxed_slice()
}

#[cfg(test)]
mod shared_rows_tests {
    use super::*;
    #[test]
    fn opaque_masks_include_all_tables_but_never_padding() {
        for n in [0usize,1,63,64,65,127,128,129,401] {
            let mut row=vec![0;n.div_ceil(64)];
            fill_all_tables(&mut row,n);
            assert_eq!(row.iter().map(|word|word.count_ones() as usize).sum::<usize>(),n);
            assert!((0..n).all(|i|row[i/64] & (1<<(i%64)) != 0));
        }
    }
    #[test]
    fn exact_rows_share_across_matrices_without_losing_high_bits() {
        let mut pool=BTreeSet::new();
        let influence=share_rows(vec![vec![1,1<<63],vec![0,0],vec![1,1<<63]],&mut pool);
        let waits=share_rows(vec![vec![1,1<<63],vec![1,0]],&mut pool);
        assert!(std::rc::Rc::ptr_eq(&influence[0],&influence[2]));
        assert!(std::rc::Rc::ptr_eq(&influence[0],&waits[0]));
        assert!(!std::rc::Rc::ptr_eq(&influence[0],&waits[1]));
        drop(pool);drop(influence);
        assert_eq!(waits[0].as_ref(),&[1,1<<63]);
    }
}
