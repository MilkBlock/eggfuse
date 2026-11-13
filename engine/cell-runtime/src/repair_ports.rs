//! A checked key footprint lets an equality update just a constructor's result
//! port. Key-changing and ambiguous-bucket events keep ordinary ordered repair.
//!
//! A decoded fact is canonical until mark_affected invalidates it. We may keep
//! that cache only when the displaced equality root occurs solely at its result
//! port. Containers are excluded because their key incidences are recursive.
//! The existing union queue and Run publication barrier remain authoritative.
use super::*;

#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub(crate) struct Plan {
    pub key_eq_columns: Vec<Option<Vec<usize>>>,
}
impl Plan {
    pub fn derive(p: &Program) -> Self {
        Self {
            key_eq_columns: p
                .tables
                .iter()
                .map(|t| {
                    if !t.constructor || !t.virtual_fact || t.schema.last()?["kind"] != "eq" {
                        return None;
                    }
                    let mut columns = vec![];
                    for (i, s) in t.schema[..t.schema.len() - 1].iter().enumerate() {
                        match s["kind"].as_str()? {
                            "eq" => columns.push(i),
                            "i64" | "f64" | "String" | "bool" | "Unit" | "structural_key" => (),
                            _ => return None,
                        }
                    }
                    Some(columns)
                })
                .collect(),
        }
    }
}
#[derive(Default, Serialize)]
pub(super) struct Runtime {
    attempts: u64,
    uncached: u64,
    unsupported: u64,
    key_changes: u64,
    ambiguous_bucket: u64,
    result_events: u64,
    field_copies: u64,
    port_checks: u64,
    by_table: Vec<u64>,
}
impl Runtime {
    pub fn new(tables: usize) -> Self {
        Self {
            by_table: vec![0; tables],
            ..Self::default()
        }
    }
}
impl Graph {
    pub fn new_with_repair_ports(program: Program) -> Result<Self> {
        let mut g = Self::new(program)?;
        g.repair_ports = Some(Runtime::new(g.program.tables.len()));
        Ok(g)
    }
    pub fn repair_port_report(&self) -> J {
        json!({"enabled":self.repair_ports.is_some(),"stats":self.repair_ports,
            "plan":self.program.repair_ports,
            "scope":"constructor result-port events; key changes retain ordered repair"})
    }
    pub(super) fn finish_result_port(&mut self, f: FactRef, from: u64, to: u64) -> bool {
        let stats = self.repair_ports.as_mut().unwrap();
        stats.attempts += 1;
        let Some(mut state_guard) = self
            .cells.fact_state_mut(f)
        else {
            return false;
        };
        let state = &mut *state_guard;
        let Some((table, fields)) = &mut state.decoded else {
            stats.uncached += 1;
            return false;
        };
        let Some(columns) = &self.program.repair_ports.key_eq_columns[*table] else {
            stats.unsupported += 1;
            return false;
        };
        if columns.iter().any(|&i| { stats.port_checks += 1; fields[i] == Value::Eq(from) }) {
            stats.key_changes += 1;
            return false;
        }
        // The cached body is canonical before this equality delta. A singleton
        // exact-key bucket cannot hide a collision that ordinary repair would
        // resolve earlier; ambiguous hash buckets retain that original order.
        stats.port_checks += 1;
        if fields.last() != Some(&Value::Eq(from)) {
            return false;
        }
        if !self
            .intern
            .get(&state.hash)
            .is_some_and(|b| b.len() == 1 && b.first() == Some(&f))
        {
            stats.ambiguous_bucket += 1;
            return false;
        }
        stats.field_copies += u64::from(RowFields::strong_count(fields) > 1);
        *RowFields::make_mut(fields).last_mut().unwrap() = Value::Eq(to);
        state.epoch = self.epoch;
        self.query_versions[*table] += 1;
        self.changes.touch(*table, Dependency::Fact(f));
        // union() redirects every reverse incidence from `from` to `to` after
        // this callback. Retirement reads the row's operands and canonicalizes
        // them before removing incidences; no second forward footprint is needed.
        stats.result_events += 1;
        stats.by_table[*table] += 1;
        true
    }
}
