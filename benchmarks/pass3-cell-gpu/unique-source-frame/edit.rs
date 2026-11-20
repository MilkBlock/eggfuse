#[derive(Default, Serialize)]
struct FrameEdits {
    mode: usize,
    hold_control: bool,
    copy_fallback: u64,
    updates: u64,
    replacements: u64,
    insertions: u64,
    removals: u64,
    ignored_absent: u64,
    retained_without_clone: u64,
    moved_to_new_buffer: u64,
    in_place: u64,
    shifted_slots: u64,
    buffer_growth_needed: u64,
    max_scans: u64,
    checked_source_rows: u64,
}
pub fn enable_frame_edits(v: Json) -> Result<()> {
    let mode = v["mode"].as_u64().ok_or("missing frame update mode")? as usize;
    if !(1..=2).contains(&mode) {
        return Err("invalid source frame update mode".into());
    }
    STORE.with_borrow_mut(|c| {
        let s = c.as_mut().ok_or("missing source proposer")?;
        if !s.frame_delta {
            return Err("frame edits need ChangeBatch input".into());
        }
        s.frame_edits.mode = mode;
        s.frame_edits.hold_control = v["hold_control"].as_bool().unwrap_or(false);
        Ok(())
    })
}
struct Edit {
    index: usize,
    existed: bool,
    new: Option<Row>,
}
impl Store {
    fn edit_unique_frame(
        &mut self,
        g: &Graph,
        t: usize,
        generation: u64,
        changed: &std::collections::BTreeSet<Dependency>,
    ) -> Result<Option<Rc<Frame>>> {
        // Read all fallible source facts before taking exclusive ownership of the previous snapshot.
        let old = self.frames.get(&t).ok_or("lost source frame")?;
        let n = old.rows.len();
        let previous_max = old.max_epoch;
        let mut edits = Vec::with_capacity(changed.len());
        let mut added = 0;
        let mut replaced = 0;
        let mut deleted = 0;
        let mut cost = 0usize;
        let mut lost_high = false;
        let mut greatest = 0u64;
        for &w in changed {
            let pos = old.rows.binary_search_by_key(&w, |row| row.witness);
            let new = g.row(w)?.filter(|r| !r.hidden && r.table == t);
            if new.as_ref().is_some_and(|row| row.witness != w) {
                return Err("source frame delta returned a different witness".into());
            }
            let age = new.as_ref().map_or(0, |r| r.epoch);
            greatest = greatest.max(age);
            let (index, existed) = match pos {
                Ok(i) => {
                    if old.rows[i].epoch == previous_max && age < previous_max {
                        lost_high = true;
                    }
                    if new.is_some() {
                        replaced += 1;
                    } else {
                        deleted += 1;
                        cost = cost.saturating_add(n - i - 1);
                    }
                    (i, true)
                }
                Err(i) => {
                    if new.is_none() {
                        self.frame_edits.ignored_absent += 1;
                        continue;
                    }
                    added += 1;
                    cost = cost.saturating_add(n - i);
                    (i, false)
                }
            };
            edits.push(Edit {
                index,
                existed,
                new,
            });
        }
        let ptr = self.frames.remove(&t).unwrap();
        let mut frame = Rc::try_unwrap(ptr).map_err(|_| "shared source frame cannot be edited")?;
        let inherited = n - replaced - deleted;
        self.frame_edits.updates += 1;
        self.frame_edits.replacements += replaced as u64;
        self.frame_edits.removals += deleted as u64;
        self.frame_edits.insertions += added as u64;
        self.frame_edits.retained_without_clone += inherited as u64;
        self.delta_stats.inherited_rows += inherited as u64;
        self.delta_stats.decoded_rows += (replaced + added) as u64;
        self.delta_stats.removed_rows += (changed.len() - replaced - added) as u64;
        if self.frame_edits.mode == 2 && cost <= n / 4 {
            // Replacements and appends dominate many real table versions. Only allow
            // interior shifts here when bounded by a fraction of one linear merge.
            self.frame_edits.in_place += 1;
            self.frame_edits.shifted_slots += cost as u64;
            self.frame_edits.buffer_growth_needed += u64::from(frame.rows.capacity() < n + added);
            frame.rows.reserve(added);
            let mut inserted = 0;
            let mut removed = 0;
            for e in edits {
                let at = e.index + inserted - removed;
                match (e.existed, e.new) {
                    (true, Some(row)) => frame.rows[at] = row,
                    (true, None) => {
                        frame.rows.remove(at);
                        removed += 1;
                    }
                    (false, Some(row)) => {
                        frame.rows.insert(at, row);
                        inserted += 1;
                    }
                    (false, None) => unreachable!(),
                }
            }
        } else {
            self.frame_edits.moved_to_new_buffer += inherited as u64;
            let mut old = std::mem::take(&mut frame.rows)
                .into_iter()
                .enumerate()
                .peekable();
            let mut rows = Vec::with_capacity(n + added - deleted);
            for e in edits {
                while old.peek().is_some_and(|(i, _)| *i < e.index) {
                    rows.push(old.next().unwrap().1);
                }
                if e.existed {
                    old.next();
                }
                if let Some(row) = e.new {
                    rows.push(row);
                }
            }
            rows.extend(old.map(|(_, r)| r));
            frame.rows = rows;
        }
        frame.generation = generation;
        frame.born_at_union = g.stats.unions;
        frame.max_epoch = if lost_high && greatest < previous_max {
            self.frame_edits.max_scans += frame.rows.len() as u64;
            frame.rows.iter().map(|r| r.epoch).max().unwrap_or(0)
        } else {
            greatest.max(previous_max)
        };
        if self.detailed {
            let mut i = 0;
            let mut high = 0;
            for address in g.witnesses(t) {
                if let Some(real) = g.row(address)?.filter(|r| !r.hidden) {
                    let current = frame
                        .rows
                        .get(i)
                        .ok_or("edited source snapshot missed a row")?;
                    if current.witness != real.witness
                        || current.epoch != real.epoch
                        || current.values != real.values
                    {
                        return Err("edited source snapshot differs from repaired source".into());
                    }
                    high = high.max(real.epoch);
                    i += 1;
                }
            }
            if frame.rows.len() != i || high != frame.max_epoch {
                return Err("invalid edited source watermark or size".into());
            }
            self.frame_edits.checked_source_rows += i as u64;
        }
        self.delta_stats.applied += 1;
        let frame = Rc::new(frame);
        self.frames.insert(t, frame.clone());
        Ok(Some(frame))
    }
}
