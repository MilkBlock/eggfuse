// Membership is set by actual subscribe/unsubscribe events; a predicted owner supplies no bit.
#[derive(Default, serde::Serialize)]
struct ReverseWork {
    elisions: u64,
    inline_stores: u64,
    promotions: u64,
    demotions: u64,
    masked_displacements: u64,
    inline_displacements: u64,
    masked_survivors: u64,
    wake_visits: u64,
    domain_audits: u64,
    derived_registrations: u64,
    derived_removals: u64,
    derived_displacements: u64,
    derived_survivors: u64,
    derived_solo_displacements: u64,
    derived_mixed_displacements: u64,
    audited_owner_known: u64,
    audited_owner_absent: u64,
    audited_owner_only: u64,
    audited_owner_with_readers: u64,
    audited_other_readers: u64,
    max_masks: usize,
}
struct MaskPage {
    words: [u64; 256],
    count: usize,
}
#[derive(Default)]
struct OwnerDirectory {
    mode: u8,
    masks: HashMap<u32, Box<MaskPage>>,
    masked: usize,
    singles: HashMap<u64, Dependency>,
    work: ReverseWork,
    shadow: Option<HashMap<u64, BTreeSet<Dependency>>>,
}
impl OwnerDirectory {
    fn coords(id: u64) -> Option<(u32, usize, u64)> {
        let slot = (id as u32).checked_sub(1)?;
        let cell = (id >> 32) as u32;
        (slot < 64).then(|| (cell >> 8, (cell & 255) as usize, 1u64 << slot))
    }
    fn bit(&self, id: u64) -> bool {
        Self::coords(id)
            .is_some_and(|(p, c, b)| self.masks.get(&p).is_some_and(|m| m.words[c] & b != 0))
    }
    fn set_bit(&mut self, id: u64) {
        let (p, c, b) = Self::coords(id).unwrap();
        let m = self.masks.entry(p).or_insert_with(|| {
            Box::new(MaskPage {
                words: [0; 256],
                count: 0,
            })
        });
        debug_assert_eq!(m.words[c] & b, 0);
        m.words[c] |= b;
        m.count += 1;
        self.masked += 1;
        self.work.max_masks = self.work.max_masks.max(self.masked);
    }
    fn clear_bit(&mut self, id: u64) {
        let (p, c, b) = Self::coords(id).unwrap();
        let m = self.masks.get_mut(&p).unwrap();
        debug_assert_ne!(m.words[c] & b, 0);
        m.words[c] &= !b;
        m.count -= 1;
        self.masked -= 1;
        if m.count == 0 {
            self.masks.remove(&p);
        }
    }
    fn compact(&self, id: u64) -> bool {
        self.mode != 0 && (self.bit(id) || self.singles.contains_key(&id))
    }
}

enum LogicalBucket {
    Empty,
    Single(Dependency),
    Tree(UseSet),
}
impl LogicalBucket {
    fn len(&self) -> usize {
        match self {
            Self::Empty => 0,
            Self::Single(_) => 1,
            Self::Tree(s) => s.len(),
        }
    }
    fn iter(&self) -> impl Iterator<Item = Dependency> + '_ {
        let (one, tree) = match self {
            Self::Empty => (None, None),
            Self::Single(d) => (Some(*d), None),
            Self::Tree(s) => (None, Some(s)),
        };
        one.into_iter()
            .chain(tree.into_iter().flat_map(|s| s.iter().copied()))
    }
    fn merge(mut self, mut other: Self) -> (Self, usize) {
        if self.len() < other.len() {
            std::mem::swap(&mut self, &mut other)
        }
        let insertions = other.len();
        match self {
            Self::Tree(mut tree) => {
                for d in other.iter() {
                    tree.insert(d);
                }
                (Self::Tree(tree), insertions)
            }
            Self::Single(d) => {
                if let Some(x) = other.iter().next()
                    && x != d
                {
                    let mut s = UseSet::default();
                    s.insert(d);
                    s.insert(x);
                    return (Self::Tree(s), insertions);
                }
                (Self::Single(d), insertions)
            }
            Self::Empty => (Self::Empty, 0),
        }
    }
}
impl Graph {
    fn owner_address(&self, id: u64) -> Option<Dependency> {
        let cell = (id >> 32) as u32;
        let slot = (id as u32).checked_sub(1)? as usize;
        if slot >= 64 {
            return None;
        }
        let t = &self.program.templates[self.cells.get(&cell)?.template];
        let op = *t.defs.get(&slot)?;
        match t.ops.get(op)? {
            Op::Let(dst, Call::Table(table), _)
                if *dst == slot && self.program.tables[*table].constructor =>
            {
                Some(Dependency::Fact(FactRef {
                    cell,
                    op: u32::try_from(op).ok()?,
                }))
            }
            _ => None,
        }
    }
    fn reverse_single(&self, id: u64) -> Option<Dependency> {
        let x = &self.owner_directory;
        if x.mode == 0 {
            return None;
        }
        if x.bit(id) {
            return Some(
                self.owner_address(id)
                    .expect("marked constructor must have its template"),
            );
        }
        x.singles.get(&id).copied()
    }
    // This is the existing forward subscription header. The class id and the
    // template select a physical address, but do not alone establish membership.
    fn derived_member(&self, id: u64) -> Option<Dependency> {
        if self.owner_directory.mode != 6 || root(&self.parents, id) != id {
            return None;
        }
        let d = self.owner_address(id)?;
        self.dependencies
            .get(&d)?
            .iter()
            .any(|x| root(&self.parents, *x) == id)
            .then_some(d)
    }
    fn derived_census(&self) -> (usize, usize) {
        if self.owner_directory.mode != 6 {
            return (0, 0);
        }
        let mut total = 0;
        let mut solo = 0;
        for (&d, _) in &self.dependencies {
            let Dependency::Fact(f) = d else { continue };
            let Some(c) = self.cells.get(&f.cell) else {
                continue;
            };
            let Some(Op::Let(slot, Call::Table(_), _)) =
                self.program.templates[c.template].ops.get(f.op as usize)
            else {
                continue;
            };
            if *slot >= 64 {
                continue;
            }
            let id = (u64::from(f.cell) << 32) | (*slot as u64 + 1);
            if self.derived_member(id) == Some(d) {
                total += 1;
                solo += usize::from(self.uses.get(&id).is_none_or(|s| s.is_empty()))
            }
        }
        (total, solo)
    }
    fn reverse_len(&self, id: u64) -> usize {
        usize::from(self.derived_member(id).is_some() || self.owner_directory.compact(id))
            + self.uses.get(&id).map_or(0, UseSet::len)
    }
    fn reverse_members(&self, id: u64) -> impl Iterator<Item = Dependency> + '_ {
        let mut owner = self.derived_member(id).or_else(|| self.reverse_single(id));
        let mut base = self
            .uses
            .get(&id)
            .into_iter()
            .flat_map(|s| s.iter().copied())
            .peekable();
        std::iter::from_fn(move || {
            if owner.is_some_and(|x| base.peek().is_none_or(|d| x < *d)) {
                owner.take()
            } else {
                base.next()
            }
        })
    }
    // Explicit and implicit controls use identical canonical set differences.
    fn subscribe_by_difference(&mut self, d: Dependency, values: &[Value]) {
        self.maintenance.subscription_calls += 1;
        let mut refs = BTreeSet::new();
        for v in values {
            Self::refs(
                v,
                &mut refs,
                &mut self.maintenance.subscription_value_visits,
            );
        }
        let refs = refs
            .into_iter()
            .map(|id| root(&self.parents, id))
            .collect::<BTreeSet<_>>();
        if self
            .dependencies
            .get(&d)
            .is_some_and(|set| set.iter().copied().eq(refs.iter().copied()))
        {
            return;
        }
        let old = self
            .dependencies
            .remove(&d)
            .unwrap_or_default()
            .into_iter()
            .map(|id| root(&self.parents, id))
            .collect::<BTreeSet<_>>();
        for &id in old.difference(&refs) {
            if self.owner_directory.mode == 6 && self.owner_address(id) == Some(d) {
                if let Some(m) = self.owner_directory.shadow.as_mut() {
                    assert!(m.get_mut(&id).unwrap().remove(&d));
                }
                self.maintenance.reverse_remove_attempts += 1;
                self.maintenance.reverse_edges_removed += 1;
                self.maintenance.live_reverse_edges -= 1;
                self.owner_directory.work.derived_removals += 1;
            } else {
                self.reverse_remove(id, d);
            }
        }
        for &id in refs.difference(&old) {
            if self.owner_directory.mode == 6 && self.owner_address(id) == Some(d) {
                if let Some(m) = self.owner_directory.shadow.as_mut() {
                    assert!(m.entry(id).or_default().insert(d));
                }
                self.maintenance.reverse_insert_attempts += 1;
                self.maintenance.reverse_edges_created += 1;
                self.maintenance.live_reverse_edges += 1;
                self.maintenance.peak_reverse_edges = self
                    .maintenance
                    .peak_reverse_edges
                    .max(self.maintenance.live_reverse_edges);
                self.owner_directory.work.derived_registrations += 1;
            } else {
                self.reverse_insert(id, d);
            }
        }
        self.dependencies.insert(d, refs.into_iter().collect());
    }
    fn forget_single(&mut self, id: u64) {
        if self.owner_directory.bit(id) {
            self.owner_directory.clear_bit(id)
        } else {
            self.owner_directory.singles.remove(&id);
        }
    }
    fn encode_single(&mut self, id: u64, d: Dependency) -> bool {
        let mode = self.owner_directory.mode;
        if matches!(mode, 3 | 5)
            && matches!(d,Dependency::Fact(f) if u64::from(f.cell)==id>>32)
            && self.owner_address(id) == Some(d)
        {
            self.owner_directory.set_bit(id);
            self.owner_directory.work.elisions += 1;
            return true;
        }
        if matches!(mode, 4 | 5) {
            self.owner_directory.singles.insert(id, d);
            self.owner_directory.work.inline_stores += 1;
            return true;
        }
        false
    }
    fn take_bucket(&mut self, id: u64) -> LogicalBucket {
        if let Some(d) = self.reverse_single(id) {
            self.forget_single(id);
            LogicalBucket::Single(d)
        } else {
            self.uses
                .remove(&id)
                .map_or(LogicalBucket::Empty, LogicalBucket::Tree)
        }
    }
    fn store_bucket(&mut self, id: u64, mut value: LogicalBucket) {
        if let Some(d) = self.derived_member(id) {
            match &mut value {
                LogicalBucket::Tree(s) => {
                    s.remove(&d);
                }
                LogicalBucket::Single(item) if *item == d => value = LogicalBucket::Empty,
                _ => (),
            }
        }
        if value.len() == 0 && self.owner_directory.mode >= 2 {
            return;
        }
        if value.len() == 1 && self.encode_single(id, value.iter().next().unwrap()) {
            return;
        }
        let tree = match value {
            LogicalBucket::Tree(s) => s,
            LogicalBucket::Empty => UseSet::default(),
            LogicalBucket::Single(d) => {
                let mut tree = UseSet::default();
                tree.insert(d);
                tree
            }
        };
        self.uses.insert(id, tree);
    }
    fn reverse_insert(&mut self, id: u64, d: Dependency) {
        if let Some(m) = self.owner_directory.shadow.as_mut() {
            m.entry(id).or_default().insert(d);
        }
        if let Some(old) = self.reverse_single(id) {
            if old == d {
                self.maintenance.reverse_insert_attempts += 1;
                return;
            }
            self.forget_single(id);
            self.uses.entry(id).or_default().insert(old);
            self.owner_directory.work.promotions += 1;
        } else if self.uses.get(&id).is_none_or(|s| s.is_empty()) && self.encode_single(id, d) {
            self.uses.remove(&id);
            self.maintenance.reverse_insert_attempts += 1;
            self.maintenance.reverse_edges_created += 1;
            self.maintenance.live_reverse_edges += 1;
            self.maintenance.peak_reverse_edges = self
                .maintenance
                .peak_reverse_edges
                .max(self.maintenance.live_reverse_edges);
            return;
        }
        maintenance::insert(&mut self.uses, &mut self.maintenance, id, d);
    }
    fn reverse_remove(&mut self, id: u64, d: Dependency) {
        if let Some(m) = self.owner_directory.shadow.as_mut()
            && let Some(s) = m.get_mut(&id)
        {
            s.remove(&d);
        }
        if let Some(old) = self.reverse_single(id) {
            self.maintenance.reverse_remove_attempts += 1;
            if old == d {
                self.forget_single(id);
                self.maintenance.live_reverse_edges -= 1;
                self.maintenance.reverse_edges_removed += 1;
            }
            return;
        }
        if let Some(s) = self.uses.get_mut(&id) {
            maintenance::remove(s, &mut self.maintenance, d);
            match s.len() {
                0 if self.owner_directory.mode >= 2 => {
                    self.uses.remove(&id);
                }
                1 if self.owner_directory.mode >= 3 => {
                    let d = *s.iter().next().unwrap();
                    if self.encode_single(id, d) {
                        self.uses.remove(&id);
                        self.owner_directory.work.demotions += 1;
                    }
                }
                _ => (),
            }
        }
    }
    fn reverse_union(
        &mut self,
        hi: u64,
        lo: u64,
        derived: (Option<Dependency>, Option<Dependency>),
    ) {
        self.owner_directory.work.masked_displacements += u64::from(self.owner_directory.bit(hi));
        self.owner_directory.work.inline_displacements +=
            u64::from(self.owner_directory.singles.contains_key(&hi));
        self.owner_directory.work.masked_survivors += u64::from(self.owner_directory.bit(lo));
        let mut displaced = self.take_bucket(hi);
        if let Some(owner) = derived.0 {
            self.owner_directory.work.derived_displacements += 1;
            self.owner_directory.work.derived_solo_displacements += u64::from(displaced.len() == 0);
            self.owner_directory.work.derived_mixed_displacements +=
                u64::from(displaced.len() != 0);
            displaced = displaced.merge(LogicalBucket::Single(owner)).0;
        }
        if self.owner_directory.shadow.is_some()
            && let Some(owner) = self.owner_address(hi)
        {
            self.owner_directory.work.audited_owner_known += 1;
            if displaced.iter().any(|d| d == owner) {
                if displaced.len() == 1 {
                    self.owner_directory.work.audited_owner_only += 1;
                } else {
                    self.owner_directory.work.audited_owner_with_readers += 1;
                    self.owner_directory.work.audited_other_readers += (displaced.len() - 1) as u64;
                }
            } else {
                self.owner_directory.work.audited_owner_absent += 1;
            }
        }
        if let Some(m) = self.owner_directory.shadow.as_mut() {
            let reference = m.remove(&hi).unwrap_or_default();
            assert!(
                displaced.iter().eq(reference.iter().copied()),
                "decoded displaced domain must be complete and ordered"
            );
            m.entry(lo).or_default().extend(reference);
            self.owner_directory.work.domain_audits += 1;
        }
        let n = displaced.len();
        self.maintenance.union_wake_visits += n as u64;
        self.maintenance.union_redirected_edges += n as u64;
        self.owner_directory.work.wake_visits += n as u64;
        self.mark_displaced_members(displaced.iter(), hi, lo);
        let mut left = self.take_bucket(lo);
        if let Some(owner) = derived.1 {
            self.owner_directory.work.derived_survivors += 1;
            left = left.merge(LogicalBucket::Single(owner)).0;
        }
        let old = left.len() + n;
        let (union, inserts) = left.merge(displaced);
        let shared = (old - union.len()) as u64;
        self.maintenance.reverse_merge_inserts += inserts as u64;
        self.maintenance.reverse_edges_coalesced += shared;
        self.maintenance.live_reverse_edges -= shared;
        self.store_bucket(lo, union);
        if let Some(m) = self.owner_directory.shadow.as_ref() {
            assert!(
                self.reverse_members(lo).eq(m[&lo].iter().copied()),
                "surviving domain must be complete"
            );
        }
    }
    pub fn configure_owner_directory(&mut self, mode: u64, audit: bool) -> Result<()> {
        if mode > 7
            || cfg!(feature = "sparse-cells")
            || self.union_digest.is_some()
            || self.stable_ports.is_some()
            || self.local_unions.is_some()
            || self.ownership.is_some()
        {
            return Err("requires ordinary source graph storage".into());
        }
        self.owner_directory.mode = mode as u8;
        if mode != 0 {
            if audit {
                self.owner_directory.shadow = Some(
                    self.uses
                        .iter()
                        .map(|(&id, s)| (id, s.iter().copied().collect()))
                        .collect(),
                );
            }
            for (id, s) in std::mem::take(&mut self.uses) {
                self.store_bucket(id, LogicalBucket::Tree(s))
            }
        }
        Ok(())
    }
    pub fn owner_directory_report(&self) -> J {
        let dir = &self.owner_directory;
        let mut physical = 0;
        let mut native_one = 0;
        let mut native_many = 0;
        for s in self.uses.values() {
            physical += s.len();
            native_one += usize::from(s.len() == 1);
            native_many += usize::from(s.len() > 1);
        }
        let (derived, sole) = self.derived_census();
        let logical = physical + dir.masked + dir.singles.len() + derived;
        assert_eq!(logical as u64, self.maintenance.live_reverse_edges);
        if let Some(shadow) = &dir.shadow {
            let mut total = 0;
            for (&id, rows) in shadow {
                assert!(self.reverse_members(id).eq(rows.iter().copied()));
                total += rows.len()
            }
            assert_eq!(total, logical);
        }
        json!({"mode":dir.mode,"logical_edges":logical,"tree_edges":physical,"forward_derived":derived,"forward_derived_solo":sole,"tree_headers":self.uses.len(),
              "tree_singletons":native_one,"tree_many":native_many,"implicit_self":dir.masked,"inline_single":dir.singles.len(),
              "pages":dir.masks.len(),"work":dir.work,"unions":self.stats.unions,"repairs":self.stats.repaired_dependencies,
              "maintenance":self.maintenance_report()})
    }
    pub fn release_reverse_part(&mut self, part: usize) {
        match part {
            0 => drop(std::mem::take(&mut self.uses)),
            1 => drop(std::mem::take(&mut self.owner_directory.masks)),
            2 => drop(std::mem::take(&mut self.owner_directory.singles)),
            _ => unreachable!(),
        }
    }
}
