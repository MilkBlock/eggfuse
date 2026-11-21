// A proof of the immediately preceding RHS. Only a successful original
// commit can attach it to a cursor. Its serial distinguishes sibling branches.
pub(crate) type Edge = [usize; 4];
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) struct Link {
    root: u64,
    serial: u64,
    rule: usize,
    run: usize,
    depth: u32,
    first: Edge,
}
impl Link {
    pub(crate) fn authorizes(self, root: u64, producer: usize, depth: u32, run: usize) -> bool {
        self.root == root
            && self.rule == producer
            && self.depth == depth
            && self.run < run
            && self.serial != 0
    }
}
#[derive(Default)]
pub(crate) struct Chain {
    pub(crate) depth: u32,
    explore_second: bool,
    bad_parent: bool,
    library: Option<std::collections::BTreeSet<Vec<Edge>>>,
    evidence: BTreeMap<Vec<Edge>, [u64; 3]>, // admitted port, bound offer, committed
    current: Option<Link>,
    last_route: Option<(u64, Option<u64>, Vec<Edge>)>,
    different_owner: u64,
    first_internal: std::collections::BTreeSet<u64>,
    second_after_internal: u64,
    second_after_external: u64,
    suppressed: BTreeMap<Vec<Edge>, u64>,
    offers_by_depth: [u64; 2],
    winners_by_depth: [u64; 2],
    pub(crate) missing_parent: u64,
    not_in_library: u64,
}
impl Chain {
    fn key(prior: Option<Link>, edge: Edge) -> Vec<Edge> {
        match prior {
            Some(p) => vec![p.first, edge],
            None => vec![edge],
        }
    }
    pub(crate) fn admits(&mut self, prior: Option<Link>, edge: Edge) -> bool {
        let key = Self::key(prior, edge);
        if !(self.explore_second && key.len() == 2)
            && self.library.as_ref().is_some_and(|lib| !lib.contains(&key))
        {
            self.not_in_library += 1;
            return false;
        }
        self.evidence.entry(key).or_default()[0] += 1;
        true
    }
    fn report(&self) -> J {
        json!({"limit":self.depth,"missing_parent":self.missing_parent,"not_in_library":self.not_in_library,
               "different_owner":self.different_owner,"second_after_internal":self.second_after_internal,"second_after_external":self.second_after_external,"suppressed":self.suppressed.iter().map(|(k,v)|(k,v)).collect::<Vec<_>>(),"offers":self.offers_by_depth,"commits":self.winners_by_depth,
               "routes":self.evidence.iter().map(|(k,v)|(k,v)).collect::<Vec<_>>()})
    }
}
pub fn configure_chain(spec: &J) -> Result<()> {
    let depth = spec["depth"].as_u64().unwrap_or(1);
    if !(1..=2).contains(&depth) {
        return Err("chain supports one or two integral transitions".into());
    }
    let library = if let Some(raw) = spec.get("library") {
        let paths: Vec<Vec<Edge>> =
            serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
        let set: std::collections::BTreeSet<_> = paths.into_iter().collect();
        if set.iter().any(|k| {
            k.is_empty()
                || k.len() > depth as usize
                || (k.len() == 2 && (k[0][2] != k[1][0] || !set.contains(&vec![k[0]])))
        }) {
            return Err("invalid or disconnected integral route library".into());
        }
        Some(set)
    } else {
        None
    };
    STORE.with_borrow_mut(|s| {
        if let Some(s) = s {
            s.chain = Chain {
                depth: depth as u32,
                library,
                bad_parent: spec["wrong_parent"] == true,
                explore_second: spec["explore_second"] == true,
                ..Default::default()
            };
        }
    });
    Ok(())
}
pub(crate) fn take_link() -> Option<Link> {
    with(|s| s.chain.current.take())
}

pub(crate) fn confirmed_suppression(serial: u64, proof: (u64, Option<u64>, Vec<Edge>)) {
    with(|s| {
        if s.chain.last_route.as_ref() == Some(&proof) {
            if let Some(prior) = proof.1 {
                if s.chain.first_internal.contains(&prior) {
                    s.chain.second_after_internal += 1
                } else {
                    s.chain.second_after_external += 1
                }
            } else {
                assert!(s.chain.first_internal.insert(serial));
            }
            *s.chain.suppressed.entry(proof.2).or_default() += 1;
        } else {
            s.chain.different_owner += 1;
        }
    });
}
