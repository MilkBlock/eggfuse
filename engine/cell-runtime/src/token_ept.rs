//! Audit-only effective operations on settled source Run boundaries.
use crate::{
    graph::{Dependency, FactRef, Graph},
    program::Result,
};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap,VecDeque};

#[derive(Clone, Copy, Default)]
pub(crate) struct Owner {
    ordinal: u64,
    token: Option<i64>,
    group: usize, // no signed owner, external request, internal signed step
}

#[derive(Default)]
pub struct Ledger {
    owner: Owner,
    ordinal: u64,
    queue: VecDeque<((u64, u64), Owner)>,
    births: Vec<(FactRef, usize, Owner)>,
    hash: Sha256,
    internal_credit:Option<BTreeMap<i64,[u64;4]>>,
    counts: [[u64; 4]; 3],
    runs: u64,
}

impl Ledger {
    pub fn enable_step_credit(&mut self) {
        self.internal_credit = Some(BTreeMap::new());
    }
    pub(crate) fn begin(&mut self, token: Option<i64>) {
        self.ordinal += 1;
        let group = match token {
            Some(t) if (1..(1_i64 << 61)).contains(&t) => 1,
            Some(t) if ((1_i64 << 61)..i64::MAX / 2).contains(&t) => 2,
            _ => 0,
        };
        self.owner = Owner {
            ordinal: self.ordinal,
            token,
            group,
        };
    }
    pub(crate) fn end(&mut self) {
        self.owner = Owner::default();
    }
    fn event(&mut self, owner: Owner, kind: usize, identity: impl Serialize) {
        self.counts[owner.group][kind] += 1;
        if owner.group == 2 && let (Some(credit),Some(token))=(&mut self.internal_credit,owner.token) {
            credit.entry(token).or_default()[kind]+=1;
        }
        self.hash
            .update(serde_json::to_vec(&(owner.ordinal, kind, identity)).expect("event identity"));
        self.hash.update(b"\n");
    }
    pub(crate) fn birth(&mut self, f: FactRef, t: usize) {
        self.births.push((f, t, self.owner));
    }
    pub(crate) fn write(&mut self, t: usize, i: usize) {
        self.event(self.owner, 1, (t, i));
    }
    pub(crate) fn hide(&mut self, t: usize, w: Dependency) {
        self.event(self.owner, 3, (t, w));
    }
    pub(crate) fn queue(&mut self, a: u64, b: u64) {
        self.queue.push_back(((a, b), self.owner));
    }
    pub(crate) fn union(&mut self, src: (u64, u64), a: u64, b: u64) -> Result<()> {
        let (request, owner) = self
            .queue
            .pop_front()
            .ok_or("union lacks an issuing operation")?;
        if src != request {
            return Err("unexpected native union order".into());
        }
        if a != b {
            self.event(owner, 2, (a.max(b), a.min(b)));
        }
        Ok(())
    }
    pub(crate) fn boundary(&mut self, g: &Graph) -> Result<()> {
        if self.owner.ordinal != 0 || !self.queue.is_empty() || !g.settled() {
            return Err("token EPT requires settled Run boundaries".into());
        }
        for (f, t, owner) in std::mem::take(&mut self.births) {
            if g.row(Dependency::Fact(f))?
                .is_some_and(|r| !r.hidden && r.table == t)
            {
                self.event(owner, 0, (t, f));
            }
        }
        self.hash.update(b"end-run\n");
        self.runs += 1;
        Ok(())
    }
    pub fn report(&self) -> serde_json::Value {
        let mut value=serde_json::json!({"runs":self.runs,"ledger_sha256":format!("{:x}",self.hash.clone().finalize()),
            "kinds":["visible_birth","function_write","effective_union","visibility_change"],
            "uncredited":self.counts[0],"signed_external":self.counts[1],"signed_internal":self.counts[2]});
        if let Some(credit)=&self.internal_credit {value["internal_tokens"]=serde_json::json!(credit);}
        value
    }
}
