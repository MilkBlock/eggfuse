type Roles = (usize, usize, usize, usize);
type Frames = (u64, u64, u64, u64);
struct RoleRows {
    frames: Frames,
    rows: Rc<Vec<usize>>,
    last_rule: usize,
}
#[derive(Default, Serialize)]
struct RoleFrontierCounts {
    root_loop_positions: usize,
    empty_calls: usize,
    empty_root_rows: usize,
    routes: usize,
    root_candidates: usize,
    admissible: usize,
    builds: usize,
    key_probes: usize,
    hits: usize,
    across_rules: usize,
    later_roles: usize,
    root_index_build_rows: usize,
    child_index_build_rows: usize,
    audit_decisions: usize,
    peak_bytes: usize,
    issuer_ms: f64,
    frontier_ms: f64,
}
#[derive(Default)]
struct Frontier {
    mode: u64,
    audit: bool,
    phase: bool,
    current: Option<Rc<Vec<usize>>>,
    cache: HashMap<Roles, RoleRows>,
    bytes: usize,
    counts: RoleFrontierCounts,
}
pub fn configure_role_frontier(mode: u64, audit: bool, phase: bool) -> Result<()> {
    STORE.with_borrow_mut(|s| {
        let st = s.as_mut().ok_or("missing proposal issuer")?;
        if mode > 3
            || !st.tier.materialize
            || !st.packed_lookup
            || st.radius != 0
            || st.mode != "learned"
            || st.prepared.mode != 0
            || st.raw_cache.enabled
        {
            return Err("reverse role frontier requires the tied compiled packed lookup".into());
        }
        st.frontier.mode = mode;
        st.frontier.audit = audit;
        st.frontier.phase = phase;
        Ok(())
    })
}
impl Store {
    fn role_frontier(&mut self, steps: &[StackStep]) -> Option<Rc<Vec<usize>>> {
        let root = &steps[0];
        let len = root.frame.rows.len();
        if self.frontier.mode < 2 || steps.len() < 3 || len < 64 {
            return None;
        }
        // A later independent parent's first lookup must use this exact published
        // slot. Other atoms may depend on the root indirectly; those are ineligible.
        let (at, child, key, root_key) = steps
            .iter()
            .enumerate()
            .skip(1)
            .filter_map(|(i, d)| {
                if d.frame.rows.len() > len / 4 {
                    return None;
                }
                let &(k, slot) = d.shared.first()?;
                let &(r, _) = root.publish.iter().find(|(_, s)| *s == slot)?;
                Some((i, d, k, r))
            })
            .min_by_key(|(i, d, _, _)| (d.frame.rows.len(), *i))?;
        let roles = (root.table, root_key, child.table, key);
        let version = (
            root.frame.generation,
            root.frame.born_at_union,
            child.frame.generation,
            child.frame.born_at_union,
        );
        let shared = self.frontier.mode == 3;
        let cached = if shared {
            self.frontier
                .cache
                .get_mut(&roles)
                .filter(|e| e.frames == version)
        } else {
            None
        };
        let result = if let Some(e) = cached {
            self.frontier.counts.hits += 1;
            self.frontier.counts.across_rules += usize::from(e.last_rule != self.rule);
            e.last_rule = self.rule;
            e.rows.clone()
        } else {
            self.frontier.counts.builds += 1;
            if self
                .indexes
                .get(&(root.table, root_key))
                .is_none_or(|v| v.generation != root.frame.generation)
            {
                self.frontier.counts.root_index_build_rows += len;
            }
            let left = self.index(root.table, root_key, &root.frame);
            if self
                .indexes
                .get(&(child.table, key))
                .is_none_or(|v| v.generation != child.frame.generation)
            {
                self.frontier.counts.child_index_build_rows += child.frame.rows.len();
            }
            let right = self.index(child.table, key, &child.frame);
            let roots = left.packed.as_ref().expect("packed root postings");
            let children = right.packed.as_ref().expect("packed descendant postings");
            let mut found = Vec::new();
            for signature in children.keys() {
                self.frontier.counts.key_probes += 1;
                if let Some(rows) = roots.get(signature) {
                    found.extend_from_slice(rows);
                }
            }
            found.sort_unstable();
            let found = Rc::new(found);
            if shared {
                if let Some(old) = self.frontier.cache.remove(&roles) {
                    self.frontier.bytes -= old.rows.capacity() * std::mem::size_of::<usize>();
                }
                let n = found.capacity() * std::mem::size_of::<usize>();
                if n <= 4 << 20 {
                    if self.frontier.bytes + n > 4 << 20 || self.frontier.cache.len() >= 1024 {
                        self.frontier.cache.clear();
                        self.frontier.bytes = 0;
                    }
                    self.frontier.bytes += n;
                    self.frontier.counts.peak_bytes =
                        self.frontier.counts.peak_bytes.max(self.frontier.bytes);
                    self.frontier.cache.insert(
                        roles,
                        RoleRows {
                            frames: version,
                            rows: found.clone(),
                            last_rule: self.rule,
                        },
                    );
                }
            }
            found
        };
        if self.frontier.audit {
            // Independent full scan uses Q on the root, K on each child; no reverse
            // posting or cached eligibility information is consulted.
            let keys = child
                .frame
                .rows
                .iter()
                .map(|r| signature(self.code(&r.values[key]), false, self.views))
                .collect::<std::collections::BTreeSet<_>>();
            let expected = root
                .frame
                .rows
                .iter()
                .enumerate()
                .filter_map(|(i, r)| {
                    let q = signature(self.code(&r.values[root_key]), true, self.views);
                    keys.contains(&q).then_some(i)
                })
                .collect::<Vec<_>>();
            assert_eq!(*result, expected, "reverse semijoin lost a learned root");
            self.frontier.counts.audit_decisions += len;
        }
        self.frontier.counts.routes += 1;
        self.frontier.counts.later_roles += usize::from(at > 1);
        self.frontier.counts.root_candidates += len;
        self.frontier.counts.admissible += result.len();
        Some(result)
    }
}
