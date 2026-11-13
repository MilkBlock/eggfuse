//! One authoritative functional row, shared with query results. Updating it
//! replaces the shared row; already published readers keep their old version.
//! Canonicality is invalidated by the existing union notification, not by a
//! second decoded-field directory. Unit projections keep their ordinary owner.
use super::*;
use serde::ser::SerializeStruct;

impl Function {
    pub fn key(&self) -> &[Value] {
        if self.projected {
            &[]
        } else {
            &self.fields[..self.fields.len() - 1]
        }
    }
    pub fn value(&self) -> &Value {
        self.fields.last().expect("functional row has a result")
    }
    pub(super) fn set_fields(&mut self, fields: RowFields) {
        self.fields = fields;
        self.canonical = true;
    }
    pub(super) fn set_value(&mut self, value: Value) {
        let mut fields = self.fields.to_vec();
        *fields.last_mut().unwrap() = value;
        self.fields = row_fields(fields);
        self.canonical = false;
    }
}

// Keep the checkpoint/trace contract unchanged: runtime sharing and
// canonicality are not serialized evidence.
impl Serialize for Function {
    fn serialize<S: serde::Serializer>(
        &self,
        serializer: S,
    ) -> std::result::Result<S::Ok, S::Error> {
        let mut s = serializer.serialize_struct("Function", 6)?;
        s.serialize_field("table", &self.table)?;
        s.serialize_field("key", self.key())?;
        s.serialize_field("value", self.value())?;
        s.serialize_field("epoch", &self.epoch)?;
        s.serialize_field("live", &self.live)?;
        s.serialize_field("origin", &self.origin)?;
        s.end()
    }
}
impl<'de> Deserialize<'de> for Function {
    fn deserialize<D: serde::Deserializer<'de>>(
        deserializer: D,
    ) -> std::result::Result<Self, D::Error> {
        #[derive(Deserialize)]
        struct Record {
            table: usize,
            key: Vec<Value>,
            value: Value,
            epoch: u64,
            live: bool,
            #[serde(default)]
            origin: Option<FactRef>,
        }
        let r = Record::deserialize(deserializer)?;
        Ok(Self {
            #[cfg(feature = "sparse-cells")]
            writer: None,
            #[cfg(feature = "receipt-slots")]
            port_slot: 0,
            table: r.table,
            fields: Graph::shared_fields(&r.key, &r.value),
            canonical: false,
            projected: false,
            epoch: r.epoch,
            live: r.live,
            origin: r.origin,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(feature = "sparse-cells")]
    #[test]
    fn row_versions_replace_forward_footprints_across_union_merge_and_delete() {
        let eq = json!({"kind":"eq","name":"E"});
        let tables = [
            eq.clone(),
            json!({"kind":"set","name":"SetE"}),
            json!({"kind":"i64","name":"i64"}),
        ]
        .into_iter()
        .enumerate()
        .map(|(i, output)| {
            json!({"name":format!("f{i}"),
                "schema":[eq,output],"constructor":false,"virtual_fact":false,
                "internal":false,"merge":{"var":"new"}})
        })
        .collect::<Vec<_>>();
        let program = serde_json::from_value(json!({"tables":tables,"templates":[],"rules":[],
            "sets":{},"control":[],"initial":[],"table_templates":[],"artifact":{},
            "multi_stage":crate::multistage::MultiStage::default(),
            "entry_schedule":crate::entry_schedule::Plan::default()}))
        .unwrap();
        let mut g = Graph::new(program).unwrap();
        g.merge_programs_enabled = false;
        fn check(g: &Graph) {
            fn refs(v: &Value, out: &mut BTreeSet<u64>) {
                match v {
                    Value::Eq(id) => {
                        out.insert(*id);
                    }
                    Value::Set(xs) => {
                        for v in xs.iter() {
                            refs(v, out);
                        }
                    }
                    _ => (),
                }
            }
            let mut expected = BTreeMap::<u64, BTreeSet<Dependency>>::new();
            for i in 0..g.functions.len() {
                if let Some(row) = g.function(i) {
                    let mut ids = BTreeSet::new();
                    for v in row.values.iter() {
                        refs(v, &mut ids);
                    }
                    for id in ids {
                        expected.entry(id).or_default().insert(row.witness);
                    }
                }
            }
            let actual = g
                .uses
                .iter()
                .filter(|(_, set)| !set.is_empty())
                .map(|(&id, set)| (id, set.iter().copied().collect::<BTreeSet<_>>()))
                .collect::<BTreeMap<_, _>>();
            assert_eq!(actual, expected);
            assert_eq!(
                g.forward_dependency_size(),
                (0, 0),
                "no second persistent function footprint"
            );
            g.maintenance_report();
        }
        g.set_function(0, vec![Value::Eq(1)], Value::Eq(4)).unwrap();
        g.set_function(0, vec![Value::Eq(2)], Value::Eq(5)).unwrap();
        g.set_function(
            1,
            vec![Value::Eq(1)],
            Value::Set(vec![Value::Eq(3), Value::Eq(4), Value::Eq(3)].into()),
        )
        .unwrap();
        g.set_function(2, vec![Value::Eq(1)], Value::Int(10))
            .unwrap();
        check(&g);
        g.set_function(0, vec![Value::Eq(1)], Value::Eq(6)).unwrap();
        g.set_function(2, vec![Value::Eq(1)], Value::Int(11))
            .unwrap();
        check(&g);
        g.enqueue_union(Value::Eq(3), Value::Eq(4)).unwrap();
        g.enqueue_union(Value::Eq(1), Value::Eq(2)).unwrap();
        g.repair().unwrap();
        check(&g);
        g.set_function(1, vec![Value::Eq(1)], Value::Set(vec![Value::Eq(6)].into()))
            .unwrap();
        check(&g);
        for table in 0..3 {
            g.hide(table, &[Value::Eq(1)], true).unwrap();
            check(&g);
        }
    }
    #[test]
    fn published_row_survives_updates_and_checkpoint_rebuilds_only_one_owner() {
        let wire = json!({"table":0,"key":[Value::Eq(7),Value::Int(4)],
            "value":Value::Int(9),"epoch":3,"live":true,"origin":null});
        let mut f: Function = serde_json::from_value(wire.clone()).unwrap();
        assert!(!f.canonical, "a checkpoint is not proof of canonicality");
        f.set_fields(f.fields.clone());
        let published = f.fields.clone();
        f.set_value(Value::Int(12));
        assert_eq!(published.last(), Some(&Value::Int(9)));
        assert_eq!(f.value(), &Value::Int(12));
        assert_eq!(f.key(), &[Value::Eq(7), Value::Int(4)]);
        assert!(!f.canonical);
        let mut expected = wire;
        expected["value"] = json!(Value::Int(12));
        assert_eq!(serde_json::to_value(&f).unwrap(), expected);
        let restored: Function = serde_json::from_value(expected).unwrap();
        assert_eq!(restored.key(), f.key());
        assert_eq!(restored.value(), f.value());
    }
}
