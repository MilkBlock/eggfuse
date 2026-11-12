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
