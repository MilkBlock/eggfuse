#[path = "named_snapshot.rs"]
mod snapshot;
use crate::{
    cell::{Instance, QueryFacts},
    graph::Dependency,
    program::{Call, Result, Rule},
    slots::Slots,
};
use serde::Deserialize;
pub(crate) use snapshot::Snapshot;
use std::collections::BTreeMap;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Packet {
    run: usize,
    rule: usize,
    // Table atoms in source order, including functional point queries.
    parents: Vec<(Dependency, u64)>,
}

#[derive(Default)]
pub struct Inbox {
    packets: BTreeMap<(usize, usize), Vec<Packet>>,
    pub accepted: usize,
    pub rejected: usize,
    pub reads: usize,
}
impl Inbox {
    pub fn submit(&mut self, packet: Packet) {
        self.packets
            .entry((packet.run, packet.rule))
            .or_default()
            .push(packet);
    }
    pub fn unused(&self) -> usize {
        self.packets.values().map(Vec::len).sum()
    }
    pub(crate) fn verify(
        &mut self,
        g: Snapshot,
        rule: &Rule,
        run: usize,
        rid: usize,
        wm: u64,
    ) -> Result<Vec<Instance>> {
        let atoms = &rule.query;
        let mut output = Vec::new();
        let Some(packets) = self.packets.remove(&(run, rid)) else {
            return Ok(output);
        };
        let arity = atoms
            .iter()
            .filter(|a| matches!(a.call, Call::Table(_)))
            .count();
        'packet: for packet in packets {
            self.rejected += 1;
            if packet.parents.len() != arity {
                continue;
            }
            let mut frame = BTreeMap::new();
            let mut receipts = vec![None; atoms.len()];
            let mut epoch = 0;
            let mut parents = packet.parents.into_iter();
            for (i, atom) in atoms.iter().enumerate() {
                let Call::Table(table) = atom.call else {
                    continue;
                };
                let (address, version) = parents.next().expect("schema arity checked");
                self.reads += 1;
                let Some(row) = g.row(address)? else {
                    continue 'packet;
                };
                if row.hidden
                    || row.table != table
                    || row.witness != address
                    || row.epoch != version
                    || row.values.len() != atom.args.len()
                    || !atom
                        .args
                        .iter()
                        .zip(row.values.iter())
                        .all(|(a, v)| g.bind(a, v, &mut frame))
                {
                    continue 'packet;
                }
                epoch = epoch.max(version);
                receipts[i] = Some(address);
            }
            if rule.seminaive && epoch < wm {
                continue;
            }
            for atom in atoms.iter() {
                let Call::Primitive(op, ty) = &atom.call else {
                    continue;
                };
                let (dest, args) = atom.args.split_last().ok_or("invalid primitive atom")?;
                let Some(values) = args
                    .iter()
                    .map(|a| g.operand(a, &frame))
                    .collect::<Option<Vec<_>>>()
                else {
                    continue 'packet;
                };
                let Some(value) = g.primitive(op, &values, ty)? else {
                    continue 'packet;
                };
                if !g.bind(dest, &value, &mut frame) {
                    continue 'packet;
                }
            }
            let mut inputs = Slots::default();
            for &slot in rule.inputs.iter() {
                let Some(v) = frame.get(&slot) else {
                    continue 'packet;
                };
                inputs.insert(slot, v.clone());
            }
            output.push(Instance::matched(
                inputs,
                QueryFacts::Ports(receipts),
                epoch,
            ));
            self.rejected -= 1;
            self.accepted += 1;
        }
        Ok(output)
    }
}
