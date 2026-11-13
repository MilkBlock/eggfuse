//! Return an exhausted suffix to an already compiled, address-identical prefix.
use super::*;

impl composition::Plan {
    pub(super) fn bake_retired_prefixes(&mut self) {
        let normalize = |shape: &composition::Shape| {
            let mut shape = shape.clone();
            shape.last_substitutions = 0;
            shape
        };
        let mut known = HashMap::default();
        for (id, shape) in self.shapes.iter().enumerate() {
            known.entry(normalize(shape)).or_insert(id);
        }
        let mut routes = Vec::new();
        for (id, shape) in self.shapes.iter().enumerate() {
            for frames in 1..shape.programs.len() {
                let symbols = shape.ports[..frames]
                    .iter()
                    .flat_map(|p| p.iter().copied())
                    .collect::<BTreeSet<_>>();
                if symbols.iter().copied().ne(0..symbols.len()) {
                    continue;
                }
                let width = symbols.len();
                let mut prefix = normalize(shape);
                prefix.programs.truncate(frames);
                prefix.ports.truncate(frames);
                prefix.origins.truncate(width);
                prefix.signals.truncate(width);
                for steps in &mut prefix.signals {
                    Arc::make_mut(steps).retain(|step| step.frame < frames);
                }
                if let Some(&target) = known.get(&prefix) {
                    if self.prefix_keeps_suffixes(id, target, frames) {
                        routes.push((id, target));
                    }
                }
            }
        }
        self.retired_prefixes = Arc::new(routes);
    }

    // A smaller representation must retain every existing append that can
    // still be reached through a surviving source, including later stages.
    // Match existing compiled targets; do not invent an unobserved rule path.
    fn prefix_keeps_suffixes(&self, source: usize, target: usize, frames: usize) -> bool {
        let mut pending = vec![(source, target, (0..frames).collect::<Vec<_>>())];
        let mut seen = BTreeSet::new();
        while let Some((old, new, kept)) = pending.pop() {
            if !seen.insert((old, new, kept.clone())) {
                continue;
            }
            let a = &self.shapes[old];
            let b = &self.shapes[new];
            if kept.len() != b.programs.len() {
                return false;
            }
            let mut forward = BTreeMap::new();
            let mut reverse = BTreeMap::new();
            for (new_frame, &old_frame) in kept.iter().enumerate() {
                if a.programs[old_frame] != b.programs[new_frame]
                    || a.ports[old_frame].len() != b.ports[new_frame].len()
                {
                    return false;
                }
                for (&x, &y) in a.ports[old_frame].iter().zip(b.ports[new_frame].iter()) {
                    if forward.insert(x, y).is_some_and(|v| v != y)
                        || reverse.insert(y, x).is_some_and(|v| v != x)
                    {
                        return false;
                    }
                }
            }
            for (key, next) in self.transitions.iter().filter(|(key, _)| key.shape == old) {
                let next = *next;
                let Some(frame) = kept.iter().position(|&f| f == key.hop.source_frame) else {
                    continue;
                };
                let mut hop = key.hop.clone();
                hop.source_frame = frame;
                let Some(other) = self.transition(&composition::Key { shape: new, hop }) else {
                    return false;
                };
                if self.shapes[next].programs.len() != a.programs.len() + 1
                    || self.shapes[other].programs.len() != b.programs.len() + 1
                {
                    return false;
                }
                let mut extended = kept.clone();
                extended.push(a.programs.len());
                pending.push((next, other, extended));
            }
        }
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn prefix_rejects_losing_a_later_stage_append() {
        let shape = |programs: Vec<usize>| {
            Arc::new(composition::Shape {
                ports: vec![Arc::new(vec![]); programs.len()],
                programs,
                ..Default::default()
            })
        };
        let hop = composition::Hop {
            source_frame: 0,
            rule: 7,
            entry: 0,
            op: 0,
        };
        let mut p = composition::Plan::default();
        p.shapes = Arc::new(vec![
            shape(vec![0, 1]),
            shape(vec![0]),
            shape(vec![0, 1, 2]),
            shape(vec![0, 2]),
            shape(vec![0, 1, 2, 3]),
            shape(vec![0, 2, 3]),
        ]);
        p.transitions = vec![(
            composition::Key {
                shape: 0,
                hop: hop.clone(),
            },
            2,
        )];
        assert!(!p.prefix_keeps_suffixes(0, 1, 1));
        p.transitions.push((
            composition::Key {
                shape: 1,
                hop: hop.clone(),
            },
            3,
        ));
        assert!(p.prefix_keeps_suffixes(0, 1, 1));
        p.transitions.push((
            composition::Key {
                shape: 2,
                hop: hop.clone(),
            },
            4,
        ));
        assert!(
            !p.prefix_keeps_suffixes(0, 1, 1),
            "the whole suffix language matters"
        );
        p.transitions.push((composition::Key { shape: 3, hop }, 5));
        assert!(p.prefix_keeps_suffixes(0, 1, 1));
        p.bake_retired_prefixes();
        assert!(p.retired_prefixes.contains(&(0, 1)));
    }
}

impl Graph {
    pub(in crate::graph) fn record_retired_prefix_source(&mut self, cell: u32) {
        // Resolve the component later: a join can move a retired source.
        if let Some(m) = self.ownership.as_mut() {
            if let Some(pending) = m.composition.retired_prefix_sources.as_mut() {
                if m.composition.frames.get(&self.cells, &cell).is_some() {
                    pending.push(cell);
                    m.stats.retired_prefix_events += 1;
                }
            }
        }
    }
    /// Opt-in Run-boundary takeover. Bootstrap once, then consume actual source
    /// retirement events. No per-producer consumer list is maintained.
    pub fn compact_retired_prefixes(&mut self) -> Result<usize> {
        #[cfg(feature="sparse-cells")]
        if self.active_rhs.is_some() {
            return Err("retired prefix takeover requires a settled boundary".into());
        }
        if !self.pending_unions.is_empty()
            || !self.dirty.is_empty()
            || !self.dirty_markers.is_empty()
        {
            return Err("retired prefix takeover requires a settled boundary".into());
        }
        let Some(m) = self.ownership.as_ref() else {
            return Ok(0);
        };
        if !m.pending.is_empty()
            || !m.composition.heap.is_empty()
            || m.composition.entry.is_some()
            || m.composition.components.is_frozen()
            // Training can extend shapes; passive catalog tracing cannot. The
            // compiled prefix proof remains authoritative while observing it.
            || m.composition.training.is_some()
        {
            return Err("retired prefix takeover requires idle compiled ownership".into());
        }
        let routes = self
            .program
            .cell_ownership
            .composition
            .retired_prefixes
            .clone();
        if routes.is_empty() {
            return Ok(0);
        }
        let m = self.ownership.as_mut().unwrap();
        let mut candidates = match m.composition.retired_prefix_sources.take() {
            Some(mut sources) => {
                // A join may have changed the component since retirement;
                // source identities remain stable. Removed frames need no work.
                sources.retain_mut(|source| {
                    if let Some(frame) = m.composition.frames.get(&self.cells, source) {
                        *source = frame.component;
                        true
                    } else {
                        false
                    }
                });
                sources.sort_unstable();
                sources.dedup();
                sources
            }
            None => {
                m.stats.retired_prefix_bootstrap_scans += m.composition.components.len() as u64;
                (0..m.composition.components.len())
                    .map(|id| id as u32)
                    .collect()
            }
        };
        let mut retries = 0;
        let mut removed = 0;
        for index in 0..candidates.len() {
            let id = candidates[index] as usize;
            let m = self.ownership.as_mut().unwrap();
            m.stats.retired_prefix_scans += 1;
            let Some(c) = m.composition.components[id].as_ref() else {
                continue;
            };
            let start = routes.partition_point(|&(shape, _)| shape < c.shape);
            let choices = routes[start..]
                .iter()
                .take_while(|&&(shape, _)| shape == c.shape);
            let live = c
                .frames
                .iter()
                .rposition(|f| self.cells.cell_metadata(*f).is_some())
                .map_or(0, |i| i + 1);
            if live == 0 {
                continue;
            }
            let Some(target) = choices
                .map(|&(_, target)| target)
                .find(|&target| m.composition.shapes[target].programs.len() >= live)
            else {
                continue;
            };
            let shape = &m.composition.shapes[target];
            let frames = shape.programs.len();
            let symbols = shape.signals.len();
            // Do not remove the native address of a symbol the prefix retains.
            // The conservative guard also covers aliases whose origin differs.
            if c.signals[..symbols].iter().flatten().any(|value| {
                c.frames[frames..].contains(&((root(&self.parents, *value) >> 32) as u32))
            }) {
                m.stats.retired_prefix_native_guards += 1;
                // A later union can clear this guard without another deletion.
                // Retain the stable retired source, not a reusable component ID.
                candidates[retries] = *c.frames.last().unwrap();
                retries += 1;
                continue;
            }
            for (symbol, value) in c.signals.iter().enumerate().skip(symbols) {
                let Some(value) = value else {
                    continue;
                };
                let value = m.stats.signal_root(&self.parents, *value);
                let signal = m
                    .composition
                    .signal(&self.program.cell_ownership, &self.cells, id as u32, symbol);
                if let Some(set) = m.boundaries.get_mut(&value) {
                    if set.remove(&signal) {
                        m.stats.boundary_live -= 1;
                        m.stats.boundary_edges_removed += 1;
                    }
                    if set.is_empty() {
                        m.boundaries.remove(&value);
                    }
                }
                m.stats.signal_bindings_live -= 1;
                m.stats.signal_bindings_retired += 1;
            }
            let dead = c.frames.len() - frames;
            for source in &c.frames[frames..] {
                m.composition.frames.remove(&mut self.cells, source);
            }
            m.stats.retired_prefix_takeovers += 1;
            m.stats.retired_prefix_frames += dead as u64;
            m.stats.retired_prefix_symbols += (c.signals.len() - symbols) as u64;
            let c = m.composition.components.local_mut(id).as_mut().unwrap();
            c.shape = target;
            c.frames.truncate(frames);
            c.frames.shrink_to_fit();
            c.signals.truncate(symbols);
            c.signals.shrink_to_fit();
            removed += dead;
        }
        candidates.truncate(retries);
        // Bootstrap can be large; keep only storage for outstanding retries.
        candidates.shrink_to_fit();
        self.ownership
            .as_mut()
            .unwrap()
            .composition
            .retired_prefix_sources = Some(candidates);
        Ok(removed)
    }
}
