// Every span refers to disjoint, freshly initialized records of a single Run.
// A donor's template never becomes the recipient's authorization.
#[derive(Default)]
struct Pool {
    shared: bool,
    fault: bool,
    records: Vec<Donor>,
    buckets: [Vec<usize>; 4],
    counts: PoolCounts,
}
struct Donor {
    rid: usize,
    template: usize,
    class: usize,
    start: usize,
    grant: usize,
    issued: usize,
    taken: usize,
}
#[derive(Default, serde::Serialize)]
struct PoolCounts {
    own: usize,
    borrowed: usize,
    switched_templates: usize,
    from_inactive_donors: usize,
    into_zero_grants: usize,
    rejected_layout: usize,
    rule_bound: usize,
    layout_bound: usize,
    run_bound: usize,
    offered_layout_bound: usize,
    offered_run_bound: usize,
}
impl Pool {
    fn add(&mut self, rid: usize, rec: &RuleRecord, width: usize) {
        let index = self.records.len();
        if rec.span.len > 0 {
            self.buckets[width - 1].push(index);
        }
        self.records.push(Donor {
            rid,
            template: rec.template,
            class: width - 1,
            start: rec.span.start,
            grant: rec.span.len,
            issued: 0,
            taken: 0,
        });
    }
    fn available(&mut self, own: usize) -> Option<usize> {
        let d = &self.records[own];
        if d.taken < d.grant {
            return Some(own);
        }
        if !self.shared {
            return None;
        }
        let bin = &mut self.buckets[d.class];
        while let Some(&id) = bin.last() {
            let src = &self.records[id];
            if src.taken < src.grant {
                return Some(id);
            }
            bin.pop();
        }
        None
    }
    fn reserve(&mut self, owner: usize, donor: usize) -> usize {
        let dst = &self.records[owner];
        let src = &self.records[donor];
        assert_eq!(src.class, dst.class);
        if owner == donor {
            self.counts.own += 1
        } else {
            self.counts.borrowed += 1;
            self.counts.switched_templates += usize::from(src.template != dst.template);
            self.counts.from_inactive_donors += usize::from(src.issued == 0);
            self.counts.into_zero_grants += usize::from(dst.grant == 0);
        }
        let d = &mut self.records[donor];
        let index = d.start + d.taken;
        d.taken += 1;
        index
    }
    fn finish(&mut self, rules: &std::collections::HashMap<usize, RuleRecord>) {
        let mut all = [(0, 0, 0); 4];
        for donor in self.records.drain(..) {
            let rec = &rules[&donor.rid];
            let demand = rec.now.fresh;
            self.counts.rule_bound += donor.grant.min(demand);
            let entry = &mut all[donor.class];
            entry.0 += donor.grant;
            entry.1 += demand;
            if donor.issued > 0 {
                entry.2 += donor.grant;
            }
        }
        let mut totals = (0, 0, 0);
        for (g, d, offered) in all {
            self.counts.layout_bound += g.min(d);
            self.counts.offered_layout_bound += offered.min(d);
            totals.0 += g;
            totals.1 += d;
            totals.2 += offered;
        }
        self.counts.run_bound += totals.0.min(totals.1);
        self.counts.offered_run_bound += totals.2.min(totals.1);
        for b in &mut self.buckets {
            b.clear();
        }
    }
}
fn pristine(frame: &Cell, src: &Donor, class: usize, epoch: u64) -> bool {
    src.class == class
        && frame.template == src.template
        && frame.started_epoch == epoch
        && frame.facts.is_empty()
        && frame.facts.stage_bytes() == (1 + class) * std::mem::size_of::<(u32, FactState)>()
        && frame.values.is_empty()
        && frame.parent.is_none()
        && !frame.completed
        && frame.completed_prefix == 0
        && frame.recipe_depth == 0
}
