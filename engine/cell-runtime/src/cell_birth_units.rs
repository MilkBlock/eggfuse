//! A constructor Cell's terminal Unit rows are materialized by its worker.
//! Exact source-order interning adopts the winning row allocation and drops
//! duplicate candidates. It never replays a Set or recomputes its operands.
use super::*;

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Site {
    pub operation: usize,
    pub table: usize,
    pub keys: Vec<Arg>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) struct Tail {
    pub sites: Vec<Site>,
    start: usize,
    end: usize,
    skipped: u64,
}
#[derive(Debug)]
pub(crate) struct Row {
    pub function: Function,
    pub fields: RowFields,
    pub(super) registered: Option<(usize, bool, bool, bool)>,
}
impl Row {
    pub(crate) fn prepared(table: usize, key: &[Value]) -> Self {
        let fields = Graph::shared_fields(key, &Value::Int(0));
        Self { fields:fields.clone(), registered: None, function: Function { writer: None,
            #[cfg(feature="receipt-slots")] port_slot: 0,
            table, fields, canonical:true, projected:false, epoch: 0, live: true, origin: None } }
    }
}
impl Tail {
    pub(super) fn starts_at(&self,position:usize)->bool {self.start==position}
    pub(super) fn ends_at(&self,position:usize)->bool {self.end==position}
    pub fn derive(p: &Program, rule: usize, last: usize) -> Option<Self> {
        let cell = Definition::new(p, rule).ok()?;
        // An earlier union could enable compact view projection at the source
        // boundary. Keep that storage policy on its existing path.
        if cell
            .template
            .ops
            .iter()
            .any(|op| matches!(op, Op::Union(..)))
        {
            return None;
        }
        let mut sites = Vec::new();
        let mut skipped = 0;
        for (operation, op) in cell.template.ops.iter().enumerate().skip(last + 1) {
            if p.known_results.static_skip[rule][operation] {
                skipped += 1;
                continue;
            }
            if matches!(op, Op::Copy(..)) {
                continue;
            }
            let Op::Set(table, keys, value) = op else {
                return None;
            };
            let t = &p.tables[*table];
            if t.virtual_fact
                || t.schema.last()?["kind"] != "Unit"
                || !matches!(t.merge["var"].as_str(), Some("old" | "new"))
                || cell.value(value) != Arg::Literal(Value::Int(0))
            {
                return None;
            }
            sites.push(Site {
                operation,
                table: *table,
                keys: keys.iter().map(|a| cell.value(a)).collect(),
            });
        }
        (!sites.is_empty()).then_some(Self {
            sites,
            start: last + 1,
            end: cell.template.ops.len(),
            skipped,
        })
    }
    pub fn storage_bytes(&self) -> usize {
        self.sites.capacity() * std::mem::size_of::<Site>()
            + self
                .sites
                .iter()
                .map(|s| s.keys.capacity() * std::mem::size_of::<Arg>())
                .sum::<usize>()
    }
}
impl Plan {
    pub(super) fn prepare_units(
        &self,
        cell: u32,
        epoch: u64,
        frame: &impl Frame,
        first: usize,
        parents: Read<'_>,
        piece: &mut Piece,
        counts: &mut Counts,
    ) {
        let tail = self.units.as_ref().unwrap();
        if piece.end != tail.start {
            return;
        }
        let mut rows = Vec::with_capacity(tail.sites.len());
        for site in &tail.sites {
            let Some(key) = site
                .keys
                .iter()
                .map(|a| {
                    operand(
                        frame,
                        &self.definitions,
                        &piece.rows,
                        first,
                        site.operation,
                        a,
                        parents,
                    )
                })
                .collect::<Option<Vec<_>>>()
            else {
                return;
            };
            let fields = Graph::shared_fields(&key, &Value::Int(0));
            rows.push(Row {
                registered: None,
                function: Function {
                    writer: None,
                    #[cfg(feature = "receipt-slots")]
                    port_slot: 0,
                    table: site.table,
                    fields:fields.clone(), canonical:true, projected:false,
                    epoch,
                    live: true,
                    origin: Some(FactRef {
                        cell,
                        op: site.operation as u32,
                    }),
                },
                fields,
            });
        }
        counts.unit_candidates += rows.len() as u64;
        if rayon::current_thread_index().is_some() {
            counts.unit_worker_rows += rows.len() as u64;
        }
        counts.unit_bytes += (rows.capacity() * std::mem::size_of::<Row>()
            + rows
                .iter()
                .map(|r| {
                    r.fields.len() * std::mem::size_of::<Value>()
                })
                .sum::<usize>()) as u64;
        piece.units = rows;
        piece.end = tail.end;
        piece.aliases += tail.skipped;
    }
}
impl Graph {
    // Only the typed Unit preparation plan creates these witnesses, against
    // the current Run's immutable inputs. Function indices are not recycled;
    // keys change only through union repair, which expires this generation.
    // This is not a general replacement for looking up an arbitrary receipt.
    pub(crate) fn apply_prepared_unit(&mut self, unit: crate::cell::unit_prepare::Unit,
        origin: Option<FactRef>, keep_key: bool) -> Result<Option<(usize, bool, Option<Vec<Value>>)>> {
        use crate::cell::unit_prepare::Unit;
        let table = unit.table();
        if !self.accept_prepared_unit(table) { self.stats.unit_prepared_stale += 1; return Ok(None); }
        match unit {
            Unit::Row(mut row) => {
                row.function.origin = origin;
                row.function.epoch = self.epoch;
                let key = keep_key.then(||row.function.key().to_vec());
                let (index, inserted) = self.commit_unit_row(row)?;
                self.stats.unit_prepared_consumed += 1;
                self.stats.unit_prepared_invalidated += u64::from(!inserted);
                Ok(Some((index, inserted, key)))
            }
            Unit::Existing(w) => {
                let Some(row) = self.functions.get(w.index).filter(|f| f.live && f.table == table
                    && f.epoch == w.epoch && f.canonical && !f.projected && f.value() == &Value::Int(0)) else {
                    self.stats.unit_prepared_witness_rejected += 1;
                    self.stats.unit_prepared_stale += 1;
                    return Ok(None);
                };
                let key = keep_key.then(||row.key().to_vec());
                // Keep ordinary merge accounting, but neither build a duplicate
                // row nor rehash its key. Unit old/new merge is total and exact.
                self.merge_value(table, Value::Int(0), Value::Int(0))?;
                self.stats.unit_prepared_existing += 1;
                Ok(Some((w.index, false, key)))
            }
        }
    }
    pub(crate) fn prepares_unit_storage(&self, table: usize) -> bool { !self.units.owned[table] }
    pub(crate) fn accept_prepared_unit(&mut self, table: usize) -> bool {
        if self.units.owned[table] { self.stats.unit_prepared_storage_fallback += 1; return false; }
        let valid = self.sealed_generation == Some(self.stats.unions) && self.pending_unions.is_empty();
        self.stats.unit_prepared_generation_fallback += u64::from(!valid);
        valid
    }
    pub(crate) fn commit_unit_row(&mut self, row: Row) -> Result<(usize, bool)> {
        let Row {
            mut function,
            fields,
            registered,
        } = row;
        let table = function.table;
        if let Some(index) = registered.filter(|(_,new,_,_)|!*new).map(|(i,_,_,_)|i)
            .or_else(||registered.is_none().then(||self.function_index(table, function.key())).flatten()) {
            // The typed old/new Unit merge preserves the first source witness.
            // The losing candidate is invalidated by dropping its actual row.
            self.merge_value(table, Value::Int(0), Value::Int(0))?;
            return Ok((index, false));
        }
        let index = registered.map_or_else(||self.functions.len(),|(index,new,_,_)| {
            assert!(new && !self.functions[index].live,"unpublished Unit reservation");index
        });
        #[cfg(feature = "slot-transfer-audit")]
        crate::transfer_audit::effective(
            self.epoch,
            table,
            index,
            function.key(),
            None,
            function.value(),
        )?;
        if registered.is_none() { self.function_keys[table].insert(function.key(), index); }
        let origin = function.origin.take();
        if registered.is_some() {
            self.functions[index]=function;
        } else {
            self.functions.push(function);
        }
        if origin.is_some_and(|o| self.active_rhs.as_ref().is_some_and(|(id, _)| *id == o.cell)) {
            self.active_origin = Some(index);
        }
        self.function_origin(index, origin);
        if registered.is_none() { self.members[table].insert(index as u64); }
        self.changed = true;
        self.stats.function_updates += 1;
        if registered.is_none() {
            self.changes.touch(table, Dependency::Function(index));
            self.subscribe_rows(table, Dependency::Function(index), &[], &fields);
        } else {
            if registered.unwrap().2 { self.changes.activate_new_table(table); }
            // A fresh Unit result needs no reverse-edge read before the Run
            // fence. Its existing registration owner installs those edges.
            if !registered.unwrap().3 {self.replace_row_edges(Dependency::Function(index), &[], &fields);}
            else {self.stats.unit_registry_deferred_subscriptions+=1;}
        }
        Ok((index, true))
    }
}

#[cfg(test)]
mod witness_tests {
    use super::*;
    use crate::cell::unit_prepare::Unit;

    #[test]
    fn exact_unit_witness_is_checked_at_its_source_effect() {
        for change in ["same", "delete", "recreate", "pending", "union", "epoch", "noncanonical"] {
            let p=serde_json::from_value(serde_json::json!({
                "tables":[{"name":"Ticket","schema":[{"kind":"eq","name":"E"},{"kind":"Unit","name":"Unit"}],
                    "constructor":false,"virtual_fact":false,"internal":false,"merge":{"var":"old"}}],
                "templates":[],"rules":[],"sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{},
                "multi_stage":crate::multistage::MultiStage::default(),
                "entry_schedule":crate::entry_schedule::Plan::default()
            })).unwrap();
            let mut g=Graph::new(p).unwrap();
            g.merge_programs_enabled=false;
            g.set_function(0,vec![Value::Eq(9)],Value::Int(0)).unwrap();
            g.set_function(0,vec![Value::Eq(10)],Value::Int(0)).unwrap();
            g.repair().unwrap();g.changes.clear();
            let reads=g.query_reads(&[],&mut 0).unwrap();
            let witness=reads.unit_witness(0,&[Value::Eq(9)]).unwrap();
            assert_ne!(witness.index,reads.unit_witness(0,&[Value::Eq(10)]).unwrap().index);
            assert!(reads.unit_witness(0,&[Value::Eq(11)]).is_none());
            drop(reads);
            g.sealed_generation=Some(g.stats.unions);g.epoch+=1;
            match change {
                "delete" | "recreate" => {
                    assert!(g.hide(0,&[Value::Eq(9)],true).unwrap());
                    if change=="recreate" {g.set_function(0,vec![Value::Eq(9)],Value::Int(0)).unwrap();}
                }
                "pending" | "union" => {
                    g.enqueue_union(Value::Eq(9),Value::Eq(7)).unwrap();
                    if change=="union" {g.repair().unwrap();}
                }
                "epoch" => g.functions[witness.index].epoch+=1,
                "noncanonical" => g.functions[witness.index].canonical=false,
                _ => (),
            }
            let before=(g.functions.len(),g.key_lookup_calls.get(),g.stats.function_updates,g.stats.merge_calls);
            let result=g.apply_prepared_unit(Unit::Existing(witness),None,true).unwrap();
            assert_eq!((g.functions.len(),g.key_lookup_calls.get(),g.stats.function_updates),(before.0,before.1,before.2));
            if change=="same" {
                assert_eq!(result,Some((witness.index,false,Some(vec![Value::Eq(9)]))));
                assert_eq!(g.stats.merge_calls,before.3+1);
                assert_eq!(g.stats.unit_prepared_existing,1);
            } else {
                assert!(result.is_none(),"{change}");
                assert_eq!(g.stats.merge_calls,before.3);
                assert_eq!(g.stats.unit_prepared_stale,1);
            }
        }
    }
}
