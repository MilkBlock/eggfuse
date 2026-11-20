//! A sealed, two-level forest. Roots are empty-LHS source rules; children cite one
//! specific published root effect. The native graph remains authoritative.
use crate::{
    graph::Dependency,
    program::{Arg, Call, Op, Program, Result},
};
use serde::Deserialize;
use serde_json::{Value as Json, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Deserialize)]
pub(crate) struct Packet {
    pub(crate) schema: String,
    pub(crate) program_sha256: String,
    pub(crate) roots: Vec<usize>,
    pub(crate) catalog: Vec<[usize; 4]>,
    #[serde(default)]
    pub(crate) children: Vec<[i64; 6]>,
}

/// Immutable certificate slot layout cached beside a loaded source program.
pub struct SealedLayout(Packet);

impl SealedLayout {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        serde_json::from_slice(bytes)
            .map(Self)
            .map_err(|e| e.to_string())
    }
    pub(crate) fn unpack(&self, words: &[u8]) -> Result<Packet> {
        if words.len()
            != self
                .0
                .catalog
                .len()
                .checked_mul(24)
                .ok_or("certificate too large")?
        {
            return Err("wrong sealed forest word count".into());
        }
        let mut packet = self.0.clone();
        packet.children = words
            .chunks_exact(24)
            .map(|row| {
                std::array::from_fn(|i| {
                    i32::from_le_bytes(row[4 * i..4 * i + 4].try_into().unwrap()) as i64
                })
            })
            .collect();
        Ok(packet)
    }
}

pub(crate) struct Forest {
    pub(crate) residual: bool,
    roots: BTreeMap<usize, usize>,
    // parent source rule, output effect, consumer rule, consumer entry.
    by_port: BTreeMap<(usize, usize, usize, usize), usize>,
    pub(crate) by_rule: BTreeMap<usize, Vec<(usize, usize, usize, usize)>>,
    pub(crate) published: BTreeMap<(usize, usize), Dependency>,
    pub(crate) direct: Vec<bool>,
    used: BTreeSet<usize>,
    sending_root: BTreeSet<usize>,
    pub(crate) ordinal: usize,
    root_events: Vec<(usize, u64, usize)>,
    child_events: Vec<(usize, usize, usize, u64, usize, usize)>,
    pub(crate) attempts: u64,
    pub(crate) point_reads: u64,
    rejected: usize,
}

impl Forest {
    pub(crate) fn load(p: &Program, packet: Packet, digest: &str, residual: bool) -> Result<Self> {
        if packet.schema != "eggfuse.sealed-forest/v1"
            || packet.program_sha256 != digest
            || packet.children.len() != packet.catalog.len()
        {
            return Err("incompatible sealed forest".into());
        }
        let mut roots = BTreeMap::new();
        for &rid in &packet.roots {
            let r = p.rules.get(rid).ok_or("unknown forest root")?;
            if !r.query.is_empty() || !r.inputs.is_empty() || roots.insert(rid, 0).is_some() {
                return Err("invalid empty-LHS root".into());
            }
        }
        let mut by_port = BTreeMap::new();
        let mut by_rule: BTreeMap<_, Vec<_>> = BTreeMap::new();
        let mut direct = vec![false; packet.children.len()];
        let mut rejected = 0;
        for (id, (&[source, effect, rid, pivot], token)) in
            packet.catalog.iter().zip(&packet.children).enumerate()
        {
            if token[0] == 0 {
                continue;
            }
            let parent = *packet.roots.get(source).ok_or("bad forest parent")?;
            let r = p.rules.get(rid).ok_or("unknown forest consumer")?;
            let lhs = r.query.get(pivot).ok_or("invalid forest pivot")?;
            let op = p.templates[p.rules[parent].template]
                .ops
                .get(effect)
                .ok_or("invalid root output port")?;
            let table = match op {
                Op::Let(_, Call::Table(t), _) | Op::Set(t, ..) => *t,
                _ => return Err("unpublished effect in forest".into()),
            };
            if !matches!(&lhs.call,Call::Table(t) if *t==table)
                || p.cell_queries.get(rid, pivot).is_none()
            {
                return Err("no exhaustive compiled continuation for forest entry".into());
            }
            if token[1..5] != [source as i64, effect as i64, rid as i64, pivot as i64]
                || token[5] < 0
            {
                rejected += 1;
                continue;
            }
            if token[5] > 1 {
                return Err("unknown forest proof".into());
            }
            if token[5] == 1 {
                let slots: BTreeSet<_> = lhs
                    .args
                    .iter()
                    .filter_map(|a| match a {
                        Arg::Slot(s) => Some(*s),
                        _ => None,
                    })
                    .collect();
                if r.query.len() != 1
                    || slots.len() != lhs.args.len()
                    || !r.inputs.iter().all(|s| slots.contains(s))
                {
                    return Err("invalid universal projection".into());
                }
                direct[id] = true;
            }
            if by_port.insert((parent, effect, rid, pivot), id).is_some() {
                return Err("duplicate compiled forest address".into());
            }
            by_rule
                .entry(rid)
                .or_default()
                .push((parent, effect, pivot, id));
        }
        Ok(Self {
            residual,
            roots,
            by_port,
            by_rule,
            published: BTreeMap::new(),
            direct,
            used: BTreeSet::new(),
            sending_root: BTreeSet::new(),
            ordinal: 0,
            root_events: Vec::new(),
            child_events: Vec::new(),
            attempts: 0,
            point_reads: 0,
            rejected,
        })
    }
    pub(crate) fn propose_root(&mut self, rid: usize) -> bool {
        if self.roots.get(&rid) != Some(&0) {
            return false;
        }
        self.sending_root.insert(rid);
        true
    }
    pub(crate) fn issue_root(&mut self, rid: usize, epoch: u64) {
        self.ordinal += 1;
        if self.sending_root.remove(&rid) {
            *self.roots.get_mut(&rid).unwrap() = self.ordinal;
            self.root_events.push((rid, epoch, self.ordinal));
        }
    }
    pub(crate) fn root_live(&self, rid: usize) -> bool {
        self.roots.get(&rid).copied().unwrap_or(0) > 0
    }
    pub(crate) fn claim(
        &self,
        parent: usize,
        effect: usize,
        rid: usize,
        pivot: usize,
    ) -> Option<usize> {
        self.by_port
            .get(&(parent, effect, rid, pivot))
            .copied()
            .filter(|id| !self.used.contains(id) && self.root_live(parent))
    }
    pub(crate) fn commit(&mut self, id: usize, parent: usize, rid: usize, epoch: u64) {
        assert!(
            self.used.insert(id),
            "duplicate committed forest obligation"
        );
        self.child_events
            .push((id, parent, rid, epoch, self.ordinal, self.roots[&parent]));
    }
    pub(crate) fn report(&self) -> Json {
        json!({"rhs":self.ordinal,"static":self.root_events,"children":self.child_events,"rejected":self.rejected,
               "assisted":self.residual,"attempts":self.attempts,"point_reads":self.point_reads})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wire_keeps_signed_proof_tags_and_refuses_a_truncated_token() {
        let layout = SealedLayout::parse(br#"{"schema":"eggfuse.sealed-forest/v1","program_sha256":"unit","roots":[2],"catalog":[[0,1,3,0]]}"#).unwrap();
        let original = [1i32, 0, 1, 3, 0, -1];
        let words = original
            .into_iter()
            .flat_map(i32::to_le_bytes)
            .collect::<Vec<_>>();
        assert_eq!(
            layout.unpack(&words).unwrap().children,
            vec![original.map(i64::from)]
        );
        assert!(layout.unpack(&words[..23]).is_err());
    }
}
