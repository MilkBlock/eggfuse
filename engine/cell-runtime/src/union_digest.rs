//! Experimental relational congruence: equality deltas update correlated key
//! packets and join them by (operator, ordered arguments). No digest collision
//! authorizes an equality without a full-key comparison.
//!
//! Raw e-class numbers are bindings, never learned rule selectors. The only
//! rule is F(xs, u), F(ys, v), xs == ys -> u == v. The ordinary graph still owns
//! row publication, interning, receipts and the source Run barriers.
use crate::{
    graph::FactRef,
    program::{Op, Program, Result},
    value::Value,
};
use rustc_hash::FxHashMap as HashMap;
use serde::Serialize;
use std::{
    collections::BTreeSet,
    hash::{Hash, Hasher},
};

#[derive(Default, Debug, Serialize)]
pub struct Stats {
    pub equality_events: u64,
    pub changed_argument_positions: u64,
    pub key_packets_updated: u64,
    pub full_key_checks: u64,
    pub congruence_matches: u64,
    pub output_union_requests: u64,
    pub publication_visits: u64,
    pub duplicate_rows_retired: u64,
    pub peak_packets: usize,
}

#[derive(Clone)]
struct Packet {
    table: usize,
    key: Vec<Value>,
    result: u64,
    hash: u64,
}

pub struct Matcher {
    packets: HashMap<FactRef, Packet>,
    // Correlated keys remain in packets. The reverse relation records exact
    // argument positions, including repeated occurrences of one variable.
    arguments: HashMap<u64, BTreeSet<(FactRef, usize)>>,
    buckets: HashMap<u64, BTreeSet<FactRef>>,
    duplicates: BTreeSet<FactRef>,
    pub stats: Stats,
    hash_bits: u32,
}

impl Matcher {
    pub fn validate(p: &Program) -> Result<()> {
        if !p.marker_tables.is_empty() {
            return Err("union digest does not yet support marker tables".into());
        }
        for t in &p.tables {
            if !t.constructor || !t.virtual_fact {
                return Err(format!(
                    "union digest requires immutable constructor tables; unsupported table {}",
                    t.name
                ));
            }
            if t.schema.iter().any(|s| {
                !matches!(
                    s["kind"].as_str(),
                    Some("eq" | "i64" | "f64" | "String" | "bool" | "Unit")
                )
            }) {
                return Err(format!(
                    "union digest requires scalar fields; unsupported table {}",
                    t.name
                ));
            }
        }
        if p.templates
            .iter()
            .any(|t| t.ops.iter().any(|op| matches!(op, Op::Hide(..))))
            || p.initial.iter().any(|r| r["subsumed"] == true)
        {
            return Err("union digest does not support deletion or subsumption".into());
        }
        Ok(())
    }

    pub fn new(hash_bits: u32) -> Result<Self> {
        if hash_bits > 64 {
            return Err("union digest hash bits must be in 0..=64".into());
        }
        Ok(Self {
            packets: HashMap::default(),
            arguments: HashMap::default(),
            buckets: HashMap::default(),
            duplicates: BTreeSet::new(),
            stats: Stats::default(),
            hash_bits,
        })
    }

    fn hash(&self, table: usize, key: &[Value]) -> u64 {
        let mut h = rustc_hash::FxHasher::default();
        table.hash(&mut h);
        key.hash(&mut h);
        let word = h.finish();
        if self.hash_bits == 64 {
            word
        } else {
            word & ((1u64 << self.hash_bits) - 1)
        }
    }

    fn unindex(&mut self, f: FactRef, hash: u64) {
        if let Some(bucket) = self.buckets.get_mut(&hash) {
            bucket.remove(&f);
            if bucket.is_empty() {
                self.buckets.remove(&hash);
            }
        }
    }

    /// Join a changed packet with an existing exact key. Tracking the whole
    /// tuple prevents combining individually true columns of different rows.
    fn join(&mut self, f: FactRef, out: &mut Vec<(u64, u64)>) {
        let p = &self.packets[&f];
        let mut equal = None;
        for &g in self.buckets.get(&p.hash).into_iter().flatten() {
            if f == g {
                continue;
            }
            self.stats.full_key_checks += 1;
            let q = &self.packets[&g];
            if p.table == q.table && p.key == q.key {
                equal = Some((g, q.result));
                break;
            }
        }
        if let Some((g, result)) = equal {
            self.stats.congruence_matches += 1;
            self.stats.output_union_requests += 1;
            out.push((p.result, result));
            self.duplicates.insert(f);
            self.duplicates.insert(g);
        }
        self.buckets.entry(p.hash).or_default().insert(f);
    }

    pub fn insert(
        &mut self,
        f: FactRef,
        table: usize,
        key: &[Value],
        result: &Value,
    ) -> Result<Vec<(u64, u64)>> {
        let Value::Eq(result) = result else {
            return Err("constructor digest result is not an equality value".into());
        };
        if self.packets.contains_key(&f) {
            return Err("duplicate digest witness".into());
        }
        let hash = self.hash(table, key);
        self.packets.insert(
            f,
            Packet {
                table,
                key: key.to_vec(),
                result: *result,
                hash,
            },
        );
        for (column, v) in key.iter().enumerate() {
            if let Value::Eq(id) = v {
                self.arguments.entry(*id).or_default().insert((f, column));
            }
        }
        self.stats.peak_packets = self.stats.peak_packets.max(self.packets.len());
        let mut out = vec![];
        self.join(f, &mut out);
        Ok(out)
    }

    /// The equality service supplies a displaced binding and its new binding.
    /// This is a delta join, not a scan of all parent constructor rows. Update
    /// every affected column before probing any packet in this event.
    pub fn equality(&mut self, from: u64, to: u64) -> Vec<(u64, u64)> {
        self.stats.equality_events += 1;
        let positions = self.arguments.remove(&from).unwrap_or_default();
        self.stats.changed_argument_positions += positions.len() as u64;
        let changed: BTreeSet<_> = positions.iter().map(|(f, _)| *f).collect();
        for &f in &changed {
            self.unindex(f, self.packets[&f].hash);
        }
        for &(f, column) in &positions {
            self.packets.get_mut(&f).unwrap().key[column] = Value::Eq(to);
        }
        if !positions.is_empty() {
            self.arguments.entry(to).or_default().extend(positions);
        }
        let mut out = vec![];
        for f in changed {
            let p = &self.packets[&f];
            let hash = self.hash(p.table, &p.key);
            self.packets.get_mut(&f).unwrap().hash = hash;
            self.stats.key_packets_updated += 1;
            self.join(f, &mut out);
        }
        out
    }

    pub fn take_duplicates(&mut self) -> BTreeSet<FactRef> {
        std::mem::take(&mut self.duplicates)
    }

    pub fn survivor(&self, f: FactRef) -> FactRef {
        let p = &self.packets[&f];
        self.buckets[&p.hash]
            .iter()
            .copied()
            .find(|g| {
                let q = &self.packets[g];
                p.table == q.table && p.key == q.key
            })
            .expect("indexed digest packet")
    }

    pub fn fields(&self, f: FactRef) -> (usize, Vec<Value>, u64) {
        let p = &self.packets[&f];
        (p.table, p.key.clone(), p.result)
    }

    pub fn remove(&mut self, f: FactRef) {
        let Some(p) = self.packets.remove(&f) else {
            return;
        };
        self.unindex(f, p.hash);
        for (column, v) in p.key.iter().enumerate() {
            if let Value::Eq(id) = v {
                if let Some(positions) = self.arguments.get_mut(id) {
                    positions.remove(&(f, column));
                    if positions.is_empty() {
                        self.arguments.remove(id);
                    }
                }
            }
        }
        self.duplicates.remove(&f);
    }

    pub fn report(&self) -> serde_json::Value {
        serde_json::json!({"enabled": true, "stats": self.stats,
            "live_packets": self.packets.len(),
            "live_argument_postings": self.arguments.values().map(BTreeSet::len).sum::<usize>(),
            "hash_bits": self.hash_bits,
            "scope": "constructor-only relational congruence; ordinary physical publication retained"})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn f(n: u32) -> FactRef {
        FactRef { cell: n, op: 0 }
    }
    #[test]
    fn complete_tuples_repeated_arguments_and_hash_collisions() {
        for bits in [0, 64] {
            let mut m = Matcher::new(bits).unwrap();
            for (n, xs) in [(1, [1, 2]), (2, [2, 1]), (3, [1, 3])] {
                assert!(
                    m.insert(f(n), 0, &xs.map(Value::Eq), &Value::Eq(10 + n as u64))
                        .unwrap()
                        .is_empty()
                );
            }
            assert_eq!(m.equality(2, 1).len(), 1);
            assert_eq!(m.survivor(f(2)), f(1));
            assert_eq!(m.survivor(f(3)), f(3));
            m.remove(f(2));
            assert_eq!(m.equality(3, 1).len(), 1);
            assert_eq!(m.survivor(f(3)), f(1));
        }
    }
    #[test]
    fn equal_results_do_not_authorize_equal_keys() {
        let mut m = Matcher::new(0).unwrap();
        m.insert(f(1), 0, &[Value::Eq(1)], &Value::Eq(9)).unwrap();
        assert!(
            m.insert(f(2), 0, &[Value::Eq(2)], &Value::Eq(9))
                .unwrap()
                .is_empty()
        );
        assert!(
            m.insert(f(3), 1, &[Value::Eq(1)], &Value::Eq(9))
                .unwrap()
                .is_empty()
        );
        assert_eq!(m.equality(2, 1).len(), 1);
        assert_eq!(m.survivor(f(3)), f(3));
    }
}
